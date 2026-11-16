"""Loopback-only BF4BR manual submission endpoint.

Launch with uvicorn bf4br.manual_report_api:app --host 127.0.0.1 --port 8794.
Never bind this unauthenticated endpoint to a public interface.
"""
import os
import psycopg
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, Field
from bf4br.manual_report import parse_report_url, submit

app = FastAPI(title='BF4BR Manual Reports', docs_url=None, redoc_url=None, openapi_url=None)

class ManualRequest(BaseModel):
    url: str = Field(min_length=1, max_length=300)

@app.post('/manual-report')
def manual_report(body: ManualRequest, request: Request):
    if request.client is None or request.client.host not in ('127.0.0.1', '::1'):
        raise HTTPException(status_code=403, detail='loopback only')
    try:
        parse_report_url(body.url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    dsn = os.environ.get('BF4BR_MANUAL_DSN')
    if not dsn:
        raise HTTPException(status_code=503, detail='not configured')
    try:
        with psycopg.connect(dsn, connect_timeout=3) as conn:
            status = submit(conn, body.url)
    except psycopg.Error:
        raise HTTPException(status_code=503, detail='database unavailable')
    return {'status': status}
