"""Opt-in BF4BR external enrichment HTTP API. Not wired to production.

Environment: BF4BR_API_KEY_SHA256 (hex digest), BF4BR_API_WORKER_ID,
BF4BR_DSN. Run only behind a trusted HTTPS reverse proxy.
"""
import hashlib
import hmac
import os
from contextlib import contextmanager
from uuid import UUID

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from bf4br.external_enrichment_selection import random_candidate
from bf4br.external_enrichment_claim import claim_player_batch
from bf4br.external_enrichment_batch import (start_batch, finish_batch, batch_item_owned, BatchBusy, CooldownActive)
from bf4br.external_enrichment_ownership import (OwnershipLost, renew_owned, save_owned, retry_owned)

app = FastAPI(title='BF4BR External Enrichment', version='0.1.0', docs_url=None, redoc_url=None, openapi_url=None)


class Submission(BaseModel):
    platform: int
    persona_id: int = Field(gt=0)
    report_id: int = Field(gt=0)
    token: UUID
    batch_id: UUID
    payload: dict


class LeaseAction(BaseModel):
    platform: int
    persona_id: int = Field(gt=0)
    report_id: int = Field(gt=0)
    token: UUID
    batch_id: UUID


class Completion(BaseModel):
    batch_id: UUID


class Failure(LeaseAction):
    reason: str = Field(min_length=1, max_length=500)
    retry_seconds: int = Field(default=1200, ge=60, le=86400)


def authenticate(authorization: str | None) -> str:
    expected = os.environ.get('BF4BR_API_KEY_SHA256', '')
    worker = os.environ.get('BF4BR_API_WORKER_ID', '')
    if len(expected) != 64 or not worker or not authorization or not authorization.startswith('Bearer '):
        raise HTTPException(status_code=401, detail='unauthorized')
    actual = hashlib.sha256(authorization[7:].encode()).hexdigest()
    if not hmac.compare_digest(actual, expected):
        raise HTTPException(status_code=401, detail='unauthorized')
    return worker


@contextmanager
def database():
    import psycopg
    dsn = os.environ.get('BF4BR_DSN')
    if not dsn:
        raise RuntimeError('BF4BR_DSN not configured')
    with psycopg.connect(dsn, autocommit=True) as conn:
        yield conn


@app.get('/api/v1/health')
def health():
    return {'service': 'bf4br-enrichment-api', 'status': 'ready'}


@app.post('/api/v1/work/claim')
def claim(authorization: str | None = Header(default=None)):
    worker = authenticate(authorization)
    with database() as conn:
        def reserve(connection):
            for _ in range(4):
                candidate = random_candidate(connection)
                if candidate is None:
                    break
                with connection.cursor() as cur:
                    cur.execute('SELECT id FROM players WHERE platform=%s AND persona_id=%s',
                                (candidate.platform, candidate.persona_id))
                    row = cur.fetchone()
                if row:
                    result = claim_player_batch(connection, row[0], worker)
                    if result:
                        return result
            return None
        try:
            result = start_batch(conn, worker, reserve)
        except (BatchBusy, CooldownActive) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail='worker disabled') from exc
        if result == ('cooldown', None):
            raise HTTPException(status_code=429, detail='worker cooldown still active')
        if result is None:
            return {'batch_id': None, 'platform': None, 'persona_id': None, 'reports': []}
        batch_id, reservation = result
        return {'batch_id': batch_id, 'platform': reservation.platform,
                'persona_id': reservation.persona_id,
                'reports': [{'report_id': rid, 'token': token}
                            for rid, token in zip(reservation.report_ids, reservation.tokens)]}


def verify_item(conn, worker, body):
    job = (body.platform, body.report_id, body.persona_id)
    if not batch_item_owned(conn, worker, body.batch_id, job, body.token):
        raise HTTPException(status_code=409, detail='item is not in an active owned batch')
    return job


@app.post('/api/v1/work/complete')
def complete(body: Completion, authorization: str | None = Header(default=None)):
    worker = authenticate(authorization)
    with database() as conn:
        try:
            finish_batch(conn, worker, body.batch_id)
        except BatchBusy as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {'completed': True, 'cooldown_seconds': 61}


@app.post('/api/v1/work/renew')
def renew(body: LeaseAction, authorization: str | None = Header(default=None)):
    worker = authenticate(authorization)
    with database() as conn, conn.transaction():
        job = verify_item(conn, worker, body)
        try:
            renew_owned(conn, job, body.token, worker, seconds=900)
        except OwnershipLost as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {'renewed': True}


@app.post('/api/v1/enrichment')
def upload(body: Submission, authorization: str | None = Header(default=None)):
    worker = authenticate(authorization)
    with database() as conn, conn.transaction():
        job = verify_item(conn, worker, body)
        try:
            save_owned(conn, job, body.token, worker, body.payload)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except (RuntimeError, OwnershipLost) as exc:
            raise HTTPException(status_code=409, detail='lease expired or ownership changed') from exc
    return {'stored': True}


@app.post('/api/v1/work/fail')
def fail(body: Failure, authorization: str | None = Header(default=None)):
    worker = authenticate(authorization)
    with database() as conn, conn.transaction():
        job = verify_item(conn, worker, body)
        try:
            retry_owned(conn, job, body.token, worker, body.reason, body.retry_seconds)
        except OwnershipLost as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
    return {'released': True}

[executed on device: reports (d4380674-2627-4f06-a351-173869e82fbe)]