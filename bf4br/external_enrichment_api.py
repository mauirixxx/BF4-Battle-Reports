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
from bf4br.detail_queue import renew_player, save_player, retry_player

app = FastAPI(title='BF4BR External Enrichment', version='0.1.0', docs_url=None, redoc_url=None, openapi_url=None)


class Submission(BaseModel):
    platform: int
    persona_id: int = Field(gt=0)
    report_id: int = Field(gt=0)
    token: UUID
    payload: dict


class LeaseAction(BaseModel):
    platform: int
    persona_id: int = Field(gt=0)
    report_id: int = Field(gt=0)
    token: UUID


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
        # Selection is advisory; the claim rechecks eligibility transactionally.
        for _ in range(4):
            candidate = random_candidate(conn)
            if candidate is None:
                break
            with conn.cursor() as cur:
                cur.execute('SELECT id FROM players WHERE platform=%s AND persona_id=%s',
                            (candidate.platform, candidate.persona_id))
                row = cur.fetchone()
            if not row:
                continue
            reservation = claim_player_batch(conn, row[0], worker)
            if reservation:
                return {'platform': reservation.platform, 'persona_id': reservation.persona_id,
                        'reports': [{'report_id': rid, 'token': token}
                                    for rid, token in zip(reservation.report_ids, reservation.tokens)]}
    return {'platform': None, 'persona_id': None, 'reports': []}


@app.post('/api/v1/work/renew')
def renew(body: LeaseAction, authorization: str | None = Header(default=None)):
    authenticate(authorization)
    job = (body.platform, body.report_id, body.persona_id)
    with database() as conn:
        ok = renew_player(conn, job, body.token, seconds=900)
    if not ok:
        raise HTTPException(status_code=409, detail='lease expired or ownership changed')
    return {'renewed': True}


@app.post('/api/v1/enrichment')
def upload(body: Submission, authorization: str | None = Header(default=None)):
    authenticate(authorization)
    job = (body.platform, body.report_id, body.persona_id)
    with database() as conn:
        try:
            save_player(conn, job, body.token, body.payload)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail='lease expired or ownership changed') from exc
    return {'stored': True}


@app.post('/api/v1/work/fail')
def fail(body: Failure, authorization: str | None = Header(default=None)):
    authenticate(authorization)
    job = (body.platform, body.report_id, body.persona_id)
    with database() as conn:
        ok = retry_player(conn, job, body.token, body.reason, body.retry_seconds)
    if not ok:
        raise HTTPException(status_code=409, detail='lease expired or ownership changed')
    return {'released': True}

[executed on device: reports (d4380674-2627-4f06-a351-173869e82fbe)]