"""
FastAPI Gateway Hub — central entry point for all channels.
Enabled when GATEWAY_ENABLED=true in .env (runs alongside v1 in parallel).
"""
from __future__ import annotations

from fastapi import FastAPI, HTTPException

from .auth import AuthError, RateLimitError, check_auth, check_rate_limit
from .normalizer import normalize
from .schemas import AgentResponseOut, MessageSpec, TaskSpec

app = FastAPI(title="SchoolAI Gateway", version="2.0.0")


@app.post("/gateway/message", response_model=AgentResponseOut)
async def receive_message(msg: MessageSpec) -> AgentResponseOut:
    """
    Channel adapters POST here.
    Normalizes → TaskSpec → Agent Runtime → AgentResponse.
    """
    try:
        check_auth(msg.user_id)
        check_rate_limit(msg.user_id)
    except AuthError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except RateLimitError as e:
        raise HTTPException(status_code=429, detail=str(e))

    task = await normalize(msg)

    from schoolai.agent.loop import run
    result = await run(task)
    return AgentResponseOut(
        session_id=task.session_id,
        text=result.text,
        domain=result.domain,
        intent=result.intent,
    )


@app.post("/gateway/classify", response_model=TaskSpec)
async def classify_only(msg: MessageSpec) -> TaskSpec:
    """Returns TaskSpec without running the agent. Useful for testing Fase 1."""
    try:
        check_auth(msg.user_id)
        check_rate_limit(msg.user_id)
    except AuthError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except RateLimitError as e:
        raise HTTPException(status_code=429, detail=str(e))

    return await normalize(msg)


@app.get("/gateway/health")
async def health() -> dict:
    return {"status": "ok", "version": "2.0.0"}
