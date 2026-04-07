"""Developer panel endpoints.

- GET  /dev/models    — lista proveedores y modelos sugeridos
- POST /dev/benchmark — SSE stream con latencias por modelo
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import AsyncIterator

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from schoolai.api.auth import get_current_user
from schoolai.skills.llm.client import get_client, parse_model
from schoolai.skills.llm.providers import PROVIDERS

router = APIRouter(prefix="/dev", tags=["Developer"])

# Modelos sugeridos por proveedor
_PROVIDER_MODELS: dict[str, list[str]] = {
    "google":     ["google/gemini-2.5-flash-lite", "google/gemini-2.5-flash"],
    "groq":       ["groq/llama-3.1-8b-instant", "groq/llama-3.3-70b-versatile"],
    "zai":        ["zai/glm-4.7-flash"],
    "zhipu":      ["zhipu/glm-4-flash"],
    "mistral":    ["mistral/mistral-small-latest"],
    "deepseek":   ["deepseek/deepseek-chat"],
    "openrouter": ["openrouter/google/gemma-3-27b-it:free"],
    "openai":     ["openai/gpt-4o-mini"],
    "nvidia":     ["nvidia/meta/llama-3.1-8b-instruct"],
    "minimax":    ["minimax/MiniMax-Text-01"],
    "moonshot":   ["moonshot/moonshot-v1-8k"],
}


@router.get("/models", summary="Proveedores y modelos disponibles")
async def list_models(_user=Depends(get_current_user)):
    """Retorna proveedores configurados y sus modelos sugeridos para el benchmark."""
    from schoolai.config import settings

    active_models = {
        settings.llm_extractor,
        settings.llm_chat,
        settings.llm_orchestrator,
    }
    # fallbacks
    if settings.llm_orchestrator_fallback:
        for m in settings.llm_orchestrator_fallback.split(","):
            active_models.add(m.strip())

    providers = []
    for key in PROVIDERS:
        api_key_attr = PROVIDERS[key]["key"]
        configured = bool(getattr(settings, api_key_attr, ""))
        providers.append(
            {
                "provider": key,
                "configured": configured,
                "models": _PROVIDER_MODELS.get(key, []),
            }
        )

    return {
        "providers": providers,
        "active_models": [m for m in active_models if m],
    }


# ── Benchmark ─────────────────────────────────────────────────────────────────


class BenchmarkRequest(BaseModel):
    models: list[str]
    prompt: str = "Responde solo con 'ok'."
    runs: int = Field(3, ge=1, le=10)


def _sse(data: dict) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


async def _run_benchmark(req: BenchmarkRequest) -> AsyncIterator[str]:
    """Genera eventos SSE: run → summary por modelo, luego done."""
    results: dict[str, list[float]] = {}

    for model_str in req.models:
        model_str = model_str.strip()
        if not model_str:
            continue

        provider, model = parse_model(model_str)
        times: list[float] = []

        try:
            client = get_client(provider)
        except ValueError as e:
            yield _sse({"type": "error", "model": model_str, "msg": str(e)})
            continue

        for run_i in range(1, req.runs + 1):
            yield _sse({"type": "running", "model": model_str, "run": run_i, "total": req.runs})

            def _call(c=client, m=model, p=req.prompt):
                return c.chat.completions.create(
                    model=m,
                    messages=[{"role": "user", "content": p}],
                    temperature=0,
                    max_tokens=10,
                )

            start = time.perf_counter()
            try:
                await asyncio.to_thread(_call)
                elapsed = round(time.perf_counter() - start, 3)
                times.append(elapsed)
                yield _sse(
                    {
                        "type": "run",
                        "model": model_str,
                        "run": run_i,
                        "latency": elapsed,
                        "status": "ok",
                    }
                )
            except Exception as e:  # noqa: BLE001
                elapsed = round(time.perf_counter() - start, 3)
                yield _sse(
                    {
                        "type": "run",
                        "model": model_str,
                        "run": run_i,
                        "latency": elapsed,
                        "status": "error",
                        "msg": str(e)[:120],
                    }
                )

        if times:
            results[model_str] = times
            yield _sse(
                {
                    "type": "summary",
                    "model": model_str,
                    "avg": round(sum(times) / len(times), 3),
                    "min": round(min(times), 3),
                    "max": round(max(times), 3),
                    "runs": len(times),
                }
            )

    yield _sse({"type": "done"})


@router.post("/benchmark", summary="Benchmark de latencia LLM (SSE stream)")
async def run_benchmark(req: BenchmarkRequest, _user=Depends(get_current_user)):
    """Ejecuta el benchmark y transmite resultados via Server-Sent Events.

    El cliente consume el stream con `fetch()` + `ReadableStream`.
    Cada evento `data:` es un JSON con campo `type`:
    - `running` — iniciando una corrida
    - `run`     — resultado de una corrida individual
    - `summary` — promedio/min/max del modelo
    - `error`   — proveedor no disponible o API error
    - `done`    — benchmark completo
    """
    return StreamingResponse(
        _run_benchmark(req),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
