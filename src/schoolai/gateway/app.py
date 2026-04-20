"""
FastAPI Gateway Hub — central entry point for all channels.
Enabled when GATEWAY_ENABLED=true in .env (runs alongside v1 in parallel).
"""
from __future__ import annotations

from fastapi import FastAPI, HTTPException

from .auth import AuthError, RateLimitError, check_auth, check_rate_limit
from .normalizer import normalize
from .schemas import MessageSpec, TaskSpec

app = FastAPI(title="SchoolAI Gateway", version="2.0.0")


@app.post("/gateway/message", response_model=TaskSpec)
async def receive_message(msg: MessageSpec) -> TaskSpec:
    """
    Channel adapters POST here. Returns a TaskSpec for the Agent Runtime.
    Agent Runtime integration is wired in Fase 2.
    """
    try:
        check_auth(msg.user_id)
        check_rate_limit(msg.user_id)
    except AuthError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except RateLimitError as e:
        raise HTTPException(status_code=429, detail=str(e))

    task = await normalize(msg)
    return task


@app.get("/gateway/health")
async def health() -> dict:
    return {"status": "ok", "version": "2.0.0"}
