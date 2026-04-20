"""
FastAPI Gateway Hub — central entry point for all channels.
Enabled when GATEWAY_ENABLED=true in .env (runs alongside v1 in parallel).
"""
from __future__ import annotations

import json

from fastapi import FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from schoolai.config import settings

from .auth import AuthError, RateLimitError, check_auth, check_rate_limit
from .normalizer import normalize
from .schemas import AgentResponseOut, MessageSpec, TaskSpec
from .session import get_session_id

app = FastAPI(title="SchoolAI Gateway", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins.split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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


@app.websocket("/gateway/ws/{user_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: str) -> None:
    """
    WebSocket para SvelteKit y CLI.
    Cliente envía: {"text": "..."}
    Servidor responde: {"text": "...", "domain": "...", "intent": "...", "session_id": "..."}
    """
    try:
        check_auth(user_id)
    except AuthError:
        await websocket.close(code=4003, reason="Unauthorized")
        return

    await websocket.accept()

    from schoolai.agent.loop import run

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                data = json.loads(raw)
                text = data.get("text", "").strip()
            except (json.JSONDecodeError, AttributeError):
                text = raw.strip()

            if not text:
                continue

            try:
                check_rate_limit(user_id)
            except RateLimitError as e:
                await websocket.send_json({"error": str(e)})
                continue

            session_id = get_session_id(user_id, "web")
            from .schemas import MessageSpec
            msg = MessageSpec(channel="web", user_id=user_id, session_id=session_id, text=text)
            task = await normalize(msg)
            result = await run(task)

            await websocket.send_json({
                "text": result.text,
                "domain": result.domain,
                "intent": result.intent,
                "session_id": session_id,
            })

    except WebSocketDisconnect:
        pass


@app.post("/gateway/telegram/{token}")
async def telegram_webhook(token: str, request: Request) -> dict:
    """Telegram webhook endpoint — reemplaza polling."""
    from .webhook import handle_telegram_webhook
    return await handle_telegram_webhook(token, request)


@app.get("/gateway/health")
async def health() -> dict:
    return {"status": "ok", "version": "2.0.0"}
