"""
SchoolAI LLM Benchmark — Phase 1: latency + TTFT across all providers.

Usage:
    uv run python scripts/benchmark_llm.py
    uv run python scripts/benchmark_llm.py --models google,groq
    uv run python scripts/benchmark_llm.py --tests simple,format --runs 2
    uv run python scripts/benchmark_llm.py --delay 600

Pools run in parallel; models within the same pool run sequentially (shared API key).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import signal
import sys
import yaml
import time
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional

import httpx
from openai import AsyncOpenAI

# ── Load .env ────────────────────────────────────────────────────────────────
_env_path = Path(__file__).parent.parent / ".env"
if _env_path.exists():
    for _line in _env_path.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip())


# ── API Keys ──────────────────────────────────────────────────────────────────
def _key(name: str) -> str:
    return os.environ.get(name, "")


GOOGLE_KEY     = _key("GOOGLE_API_KEY")
GROQ_KEY       = _key("GROQ_API_KEY")
DEEPSEEK_KEY   = _key("DEEPSEEK_API_KEY")
MISTRAL_KEY    = _key("MISTRAL_API_KEY")
OPENROUTER_KEY = _key("OPENROUTER_API_KEY")
ZAI_KEY        = _key("ZAI_API_KEY")
NVIDIA_KEY     = _key("NVIDIA_API_KEY")
MINIMAX_KEY    = _key("MINIMAX_API_KEY")
MOONSHOT_KEY   = _key("MOONSHOT_API_KEY")
ZHIPU_KEY      = _key("ZHIPU_API_KEY")
KILO_KEY          = _key("KILO_API_KEY")
HF_KEY            = _key("HF_TOKEN")
MULEROUTER_KEY    = _key("MULEROUTER_API_KEY")
OLLAMA_URL        = _key("OLLAMA_BASE_URL") or "http://127.0.0.1:11434/v1/"
OLLAMA_MODEL      = _key("OLLAMA_MODEL")


# ── ModelDef ──────────────────────────────────────────────────────────────────
@dataclass
class ModelDef:
    # Identity
    model_id: str          # API model string
    model_name: str        # human-readable
    provider: str          # display name (e.g. "Google", "Groq")
    pool: str              # same pool = same API key = sequential
    rpm_pool: str          # rate-limit group (may differ from pool for openrouter-free)

    # Connection
    base_url: str
    api_key: str

    # Role
    role: str              # "classifier" | "planner" | "synthesizer" | "vision" | "candidate" | *_fallback
    in_use: bool = False

    # Behaviour
    rpm: int = 30
    thinking_budget: int = 0          # base max_tokens for reasoning (scaled by reasoning_mode)
    strip_thinking: bool = False       # remove <think>/<thought>/<thinking> tags
    no_streaming: bool = False         # force non-streaming (some models)
    compound_mode: bool = False        # groq compound-beta: separate web-search test
    stream_usage: bool = False         # add stream_options:{include_usage:true} (Google/Gemini)
    reasoning_mode: str = "medium"     # "high" | "medium" | "low" | "off" — controls thinking depth
    reasoning_style: str = ""          # "budget_tokens" | "effort" | "qwen" | "" — how to apply mode
    web_search: bool = False           # model has built-in web search (informational flag)
    hf_provider: str = ""             # HuggingFace router: provider hint ("nscale", "cerebras", …)

    # Skip
    skip_reason: str = ""             # non-empty → skip this model

    def effective_thinking_budget(self) -> int:
        """Return thinking_budget scaled by reasoning_mode."""
        if self.thinking_budget == 0:
            return 0
        scale = {"high": 2.0, "medium": 1.0, "low": 0.4, "off": 0.0}.get(self.reasoning_mode, 1.0)
        return int(self.thinking_budget * scale)


# ── Model Catalog ─────────────────────────────────────────────────────────────
def _build_models() -> list[ModelDef]:
    """Catálogo organizado por función en SchoolAI.

    El campo pool= controla el rate-limiting (mismo pool = secuencial, pools distintos = paralelo).
    Los tests que corre cada modelo dependen de role= — ver _ROLE_SUITES.
    """
    # ── Credenciales por proveedor ─────────────────────────────────────────────
    _g_key    = GOOGLE_KEY
    _g_url    = "https://generativelanguage.googleapis.com/v1beta/openai/"
    _gr_key   = GROQ_KEY
    _gr_url   = "https://api.groq.com/openai/v1/"
    _ds_key   = DEEPSEEK_KEY
    _ds_url   = "https://api.deepseek.com/v1/"
    _ms_key   = MISTRAL_KEY
    _ms_url   = "https://api.mistral.ai/v1/"
    _or_key   = OPENROUTER_KEY
    _or_url   = "https://openrouter.ai/api/v1/"
    _zai_key  = ZAI_KEY
    _zai_url  = "https://api.z.ai/api/paas/v4/"
    _nv_key   = NVIDIA_KEY
    _nv_url   = "https://integrate.api.nvidia.com/v1/"
    _kilo_key = KILO_KEY
    _kilo_url = "https://api.kilo.ai/api/gateway/"
    _hf_key   = HF_KEY
    _hf_url   = "https://router.huggingface.co/v1/"
    _mr_key   = MULEROUTER_KEY
    _mr_url   = "https://api.mulerouter.ai/vendors/openai/v1/"
    _ol_url   = "http://localhost:11434/v1/"

    _g_skip    = "" if _g_key    else "GOOGLE_API_KEY not set"
    _gr_skip   = "" if _gr_key   else "GROQ_API_KEY not set"
    _ds_skip   = "" if _ds_key   else "DEEPSEEK_API_KEY not set"
    _ms_skip   = "" if _ms_key   else "MISTRAL_API_KEY not set"
    _or_skip   = "" if _or_key   else "OPENROUTER_API_KEY not set"
    _zai_skip  = "" if _zai_key  else "ZAI_API_KEY not set"
    _nv_skip   = "" if _nv_key   else "NVIDIA_API_KEY not set"
    _kilo_skip = "" if _kilo_key else "KILO_API_KEY not set"
    _hf_skip   = "" if _hf_key   else "HF_TOKEN not set"
    _mr_skip   = "" if _mr_key   else "MULEROUTER_API_KEY not set"

    models: list[ModelDef] = []

    # ═════════════════════════════════════════════════════════════════════════
    # 1. CLASSIFIER — llm_router (gateway/router.py)
    #    Tarea: classify {domain, intent, entities} en JSON — cada mensaje
    #    Tests: latencia + JSON (json + json_noex)
    #    En uso: Mistral Medium → GPT-OSS 120B / DeepSeek Chat (llm_router_fallback)
    # ═════════════════════════════════════════════════════════════════════════
    models += [
        # Mistral Medium — en uso como classifier (100%/100% JSON, 1992ms)
        ModelDef(
            model_id="mistral-medium-latest", model_name="Mistral Medium",
            provider="Mistral", pool="mistral", rpm_pool="mistral",
            base_url=_ms_url, api_key=_ms_key,
            role="classifier", in_use=True,
            rpm=12, skip_reason=_ms_skip,
        ),
        # Mistral Large — candidato extractor (100%/100% pero más caro)
        ModelDef(
            model_id="mistral-large-latest", model_name="Mistral Large",
            provider="Mistral", pool="mistral", rpm_pool="mistral",
            base_url=_ms_url, api_key=_ms_key,
            role="candidate",
            rpm=12, skip_reason=_ms_skip,
        ),
    ]

    # ═════════════════════════════════════════════════════════════════════════
    # 2. PLANNER — llm_orchestrator (agent/planner.py)
    #    Tarea: genera plan [{tool, params}] con response_format=json_object
    #    NO usa tool_choice=auto — es JSON planning, no native tool calling
    #    Tests: latencia + JSON (json + json_noex)
    #    En uso: Kimi K2 → DeepSeek Chat → DeepSeek Reasoner → GPT-OSS 120B
    # ═════════════════════════════════════════════════════════════════════════
    models += [
        # Kimi K2 — planner primario (llm_orchestrator en config.py)
        ModelDef(
            model_id="moonshotai/kimi-k2-instruct", model_name="Kimi K2",
            provider="OpenRouter", pool="openrouter", rpm_pool="openrouter",
            base_url=_or_url, api_key=_or_key,
            role="planner", in_use=True,
            rpm=20, skip_reason=_or_skip,
        ),
        # DeepSeek Chat — planner fallback #1
        ModelDef(
            model_id="deepseek-chat", model_name="DeepSeek V3.2 (Chat)",
            provider="DeepSeek", pool="deepseek", rpm_pool="deepseek",
            base_url=_ds_url, api_key=_ds_key,
            role="planner_fallback", in_use=True,
            rpm=60, skip_reason=_ds_skip,
        ),
        # DeepSeek Reasoner — planner fallback #2
        ModelDef(
            model_id="deepseek-reasoner", model_name="DeepSeek V3.2 Reasoner",
            provider="DeepSeek", pool="deepseek", rpm_pool="deepseek",
            base_url=_ds_url, api_key=_ds_key,
            role="planner_fallback", in_use=True,
            rpm=60, thinking_budget=4000, strip_thinking=True,
            reasoning_style="budget_tokens",
            skip_reason=_ds_skip,
        ),
        # GPT-OSS 120B (Groq) — planner fallback #3
        ModelDef(
            model_id="openai/gpt-oss-120b", model_name="GPT-OSS 120B",
            provider="Groq", pool="groq", rpm_pool="groq",
            base_url=_gr_url, api_key=_gr_key,
            role="planner_fallback", in_use=True,
            rpm=20, skip_reason=_gr_skip,
        ),
        # Qwen3 32B (Groq) — candidato planner
        ModelDef(
            model_id="qwen/qwen3-32b", model_name="Qwen3 32B",
            provider="Groq", pool="groq", rpm_pool="groq",
            base_url=_gr_url, api_key=_gr_key,
            role="candidate",
            rpm=20, thinking_budget=2000, strip_thinking=True,
            reasoning_style="",
            skip_reason=_gr_skip,
        ),
        # Llama 4 Scout 17B (Groq) — candidato planner ligero
        ModelDef(
            model_id="meta-llama/llama-4-scout-17b-16e-instruct", model_name="Llama 4 Scout 17B",
            provider="Groq", pool="groq", rpm_pool="groq",
            base_url=_gr_url, api_key=_gr_key,
            role="candidate",
            rpm=20, skip_reason=_gr_skip,
        ),
        # Llama 3.3 70B (Groq) — skipped (retirado de API 2026-04-15)
        ModelDef(
            model_id="meta-llama/llama-3.3-70b-versatile", model_name="Llama 3.3 70B (Groq)",
            provider="Groq", pool="groq", rpm_pool="groq",
            base_url=_gr_url, api_key=_gr_key,
            role="planner_fallback", in_use=True,
            rpm=20,
            skip_reason="404 — modelo retirado de Groq API (2026-04-15). Verificar ID en console.groq.com",
        ),
        # Kimi K2.5 (Ollama Cloud) — candidato planner agentic
        ModelDef(
            model_id="kimi-k2.5:cloud", model_name="Kimi K2.5 (Ollama Cloud)",
            provider="Ollama Cloud", pool="ollama", rpm_pool="ollama",
            base_url=_ol_url, api_key="ollama",
            role="candidate",
            rpm=999, thinking_budget=2000, strip_thinking=True,
            reasoning_style="budget_tokens",
        ),
        # GPT-OSS 120B (Ollama Cloud) — sweep reasoning modes
        ModelDef(
            model_id="gpt-oss:120b-cloud", model_name="GPT-OSS 120B [medium]",
            provider="Ollama Cloud", pool="ollama", rpm_pool="ollama",
            base_url=_ol_url, api_key="ollama",
            role="candidate",
            rpm=999, strip_thinking=True, reasoning_mode="medium",
        ),
        ModelDef(
            model_id="gpt-oss:120b-cloud", model_name="GPT-OSS 120B [off]",
            provider="Ollama Cloud", pool="ollama", rpm_pool="ollama",
            base_url=_ol_url, api_key="ollama",
            role="candidate",
            rpm=999, strip_thinking=True, reasoning_mode="off",
        ),
        # GPT-OSS 20B (Ollama Cloud) — candidato planner ligero
        ModelDef(
            model_id="gpt-oss:20b-cloud", model_name="GPT-OSS 20B (Ollama Cloud)",
            provider="Ollama Cloud", pool="ollama", rpm_pool="ollama",
            base_url=_ol_url, api_key="ollama",
            role="candidate",
            rpm=999,
        ),
    ]

    # ═════════════════════════════════════════════════════════════════════════
    # 3. SYNTHESIZER — llm_router (agent/synthesizer.py)
    #    Tarea: genera respuesta final en español al docente — conversacional
    #    Nota: mismo config key que classifier (llm_router sirve dos funciones)
    #    Tests: latencia únicamente (sin tool calling, sin JSON)
    #    En uso: Mistral Medium → GPT-OSS 120B / DeepSeek Chat (fallback)
    # ═════════════════════════════════════════════════════════════════════════
    models += [
        # compound-beta — síntesis con web search nativo (si se activa en synthesizer)
        ModelDef(
            model_id="compound-beta", model_name="Compound Beta (web agent)",
            provider="Groq", pool="groq", rpm_pool="groq",
            base_url=_gr_url, api_key=_gr_key,
            role="synthesizer",
            rpm=20, compound_mode=True, web_search=True,
            skip_reason=_gr_skip,
        ),
        # Mistral Small — candidato synthesizer rápido
        ModelDef(
            model_id="mistral-small-latest", model_name="Mistral Small",
            provider="Mistral", pool="mistral", rpm_pool="mistral",
            base_url=_ms_url, api_key=_ms_key,
            role="synthesizer_fallback",
            rpm=12, skip_reason=_ms_skip,
        ),
        # GPT-OSS 20B (Groq) — candidato chat rápido (694ms)
        ModelDef(
            model_id="openai/gpt-oss-20b", model_name="GPT-OSS 20B",
            provider="Groq", pool="groq", rpm_pool="groq",
            base_url=_gr_url, api_key=_gr_key,
            role="candidate",
            rpm=20, skip_reason=_gr_skip,
        ),
        # Llama 3.1 8B (Groq) — candidato chat ligero, skipped (retirado)
        ModelDef(
            model_id="meta-llama/llama-3.1-8b-instant", model_name="Llama 3.1 8B (Groq)",
            provider="Groq", pool="groq", rpm_pool="groq",
            base_url=_gr_url, api_key=_gr_key,
            role="candidate",
            rpm=20,
            skip_reason="404 — modelo retirado de Groq API (2026-04-15). Verificar ID en console.groq.com",
        ),
    ]

    # ═════════════════════════════════════════════════════════════════════════
    # 4. VISION — llm_vision + llm_vision_fallback
    #    Tarea: extracción desde imágenes (multimodal)
    #    Tests: latencia únicamente
    #    En uso: Nemotron Nano 12B VL → Gemma 4 31B (OpenRouter free)
    # ═════════════════════════════════════════════════════════════════════════
    models += [
        # Nemotron Nano 12B VL — vision en uso (128K ctx)
        ModelDef(
            model_id="nvidia/nemotron-nano-12b-v2-vl:free", model_name="Nemotron Nano 12B VL",
            provider="OpenRouter", pool="openrouter", rpm_pool="openrouter-free",
            base_url=_or_url, api_key=_or_key,
            role="vision", in_use=True,
            rpm=10, skip_reason=_or_skip,
        ),
        # Gemma 4 31B (OpenRouter free) — vision fallback
        ModelDef(
            model_id="google/gemma-4-31b-it:free", model_name="Gemma 4 31B (OpenRouter free)",
            provider="OpenRouter", pool="openrouter", rpm_pool="openrouter-free",
            base_url=_or_url, api_key=_or_key,
            role="vision_fallback", in_use=True,
            rpm=10, thinking_budget=1500, strip_thinking=True,
            skip_reason=_or_skip,
        ),
    ]

    # ═════════════════════════════════════════════════════════════════════════
    # 5. CANDIDATOS — evaluación completa (latencia + JSON + TOON + native)
    #    Sin rol asignado — benchmark completo para determinar el mejor fit.
    # ═════════════════════════════════════════════════════════════════════════

    # ── Google AI Studio (GOOGLE_API_KEY) — free tier ─────────────────────────
    # 15 RPM Gemma 4, 30 RPM Gemma 3; pool separado para no mezclar RPM
    models += [
        ModelDef(
            model_id="gemini-2.5-flash-lite", model_name="Gemini 2.5 Flash Lite",
            provider="Google", pool="google", rpm_pool="google",
            base_url=_g_url, api_key=_g_key,
            role="candidate",
            rpm=10, stream_usage=True, skip_reason=_g_skip,
        ),
        ModelDef(
            model_id="gemini-3.1-flash-lite-preview", model_name="Gemini 3.1 Flash Lite Preview",
            provider="Google", pool="google", rpm_pool="google",
            base_url=_g_url, api_key=_g_key,
            role="candidate",
            rpm=15, stream_usage=True, skip_reason=_g_skip,
        ),
        ModelDef(
            model_id="gemma-4-26b-a4b-it", model_name="Gemma 4 26B",
            provider="Google", pool="google", rpm_pool="google",
            base_url=_g_url, api_key=_g_key,
            role="candidate",
            rpm=15, stream_usage=True, skip_reason=_g_skip,
        ),
        ModelDef(
            model_id="gemma-4-31b-it", model_name="Gemma 4 31B",
            provider="Google", pool="google", rpm_pool="google",
            base_url=_g_url, api_key=_g_key,
            role="candidate",
            rpm=15, stream_usage=True, skip_reason=_g_skip,
        ),
        ModelDef(
            model_id="gemma-3-27b-it", model_name="Gemma 3 27B",
            provider="Google", pool="google", rpm_pool="google-gemma3",
            base_url=_g_url, api_key=_g_key,
            role="candidate",
            rpm=30, stream_usage=True, skip_reason=_g_skip,
        ),
        ModelDef(
            model_id="gemma-3-12b-it", model_name="Gemma 3 12B",
            provider="Google", pool="google", rpm_pool="google-gemma3",
            base_url=_g_url, api_key=_g_key,
            role="candidate",
            rpm=30, stream_usage=True, skip_reason=_g_skip,
        ),
    ]

    # ── HuggingFace Inference Providers (HF_TOKEN) ─────────────────────────────
    models += [
        ModelDef(
            model_id="Qwen/Qwen3-8B", model_name="Qwen3 8B (HF/nscale)",
            provider="HuggingFace", pool="hf", rpm_pool="hf-nscale",
            base_url=_hf_url, api_key=_hf_key,
            role="candidate", hf_provider="nscale",
            rpm=20, strip_thinking=True, skip_reason=_hf_skip,
        ),
        ModelDef(
            model_id="Qwen/Qwen3-14B", model_name="Qwen3 14B (HF/nscale)",
            provider="HuggingFace", pool="hf", rpm_pool="hf-nscale",
            base_url=_hf_url, api_key=_hf_key,
            role="candidate", hf_provider="nscale",
            rpm=20, strip_thinking=True, skip_reason=_hf_skip,
        ),
        ModelDef(
            model_id="Qwen/Qwen3-32B", model_name="Qwen3 32B (HF/nscale)",
            provider="HuggingFace", pool="hf", rpm_pool="hf-nscale",
            base_url=_hf_url, api_key=_hf_key,
            role="candidate", hf_provider="nscale",
            rpm=20, strip_thinking=True, skip_reason=_hf_skip,
        ),
        ModelDef(
            model_id="google/gemma-3-27b-it", model_name="Gemma 3 27B (HF/nscale)",
            provider="HuggingFace", pool="hf", rpm_pool="hf-nscale",
            base_url=_hf_url, api_key=_hf_key,
            role="candidate", hf_provider="nscale",
            rpm=20, skip_reason=_hf_skip,
        ),
        ModelDef(
            model_id="deepseek-ai/DeepSeek-R1-Distill-Qwen-7B",
            model_name="DeepSeek R1 Distill 7B (HF/nscale)",
            provider="HuggingFace", pool="hf", rpm_pool="hf-nscale",
            base_url=_hf_url, api_key=_hf_key,
            role="candidate", hf_provider="nscale",
            rpm=20, strip_thinking=True, skip_reason=_hf_skip,
        ),
        ModelDef(
            model_id="meta-llama/Llama-3.1-8B-Instruct",
            model_name="Llama 3.1 8B (HF/cerebras)",
            provider="HuggingFace", pool="hf", rpm_pool="hf-cerebras",
            base_url=_hf_url, api_key=_hf_key,
            role="candidate", hf_provider="cerebras",
            rpm=30, skip_reason=_hf_skip,
        ),
        ModelDef(
            model_id="meta-llama/Llama-3.3-70B-Instruct",
            model_name="Llama 3.3 70B (HF/cerebras)",
            provider="HuggingFace", pool="hf", rpm_pool="hf-cerebras",
            base_url=_hf_url, api_key=_hf_key,
            role="candidate", hf_provider="cerebras",
            rpm=30, skip_reason=_hf_skip,
        ),
        ModelDef(
            model_id="meta-llama/Llama-3.3-70B-Instruct",
            model_name="Llama 3.3 70B (HF/sambanova)",
            provider="HuggingFace", pool="hf", rpm_pool="hf-sambanova",
            base_url=_hf_url, api_key=_hf_key,
            role="candidate", hf_provider="sambanova",
            rpm=20, skip_reason=_hf_skip,
        ),
    ]

    # ── Kilo AI Gateway (KILO_API_KEY) — free tier ─────────────────────────────
    models += [
        ModelDef(
            model_id="bytedance-seed/dola-seed-2.0-pro:free",
            model_name="ByteDance Dola Seed 2.0 Pro (Kilo free)",
            provider="Kilo AI", pool="kilo", rpm_pool="kilo",
            base_url=_kilo_url, api_key=_kilo_key,
            role="candidate", rpm=20, skip_reason=_kilo_skip,
        ),
        ModelDef(
            model_id="x-ai/grok-code-fast-1:optimized:free",
            model_name="Grok Code Fast 1 (Kilo free)",
            provider="Kilo AI", pool="kilo", rpm_pool="kilo",
            base_url=_kilo_url, api_key=_kilo_key,
            role="candidate", rpm=20, skip_reason=_kilo_skip,
        ),
        ModelDef(
            model_id="nvidia/nemotron-3-super-120b-a12b:free",
            model_name="Nemotron 3 Super 120B (Kilo free)",
            provider="Kilo AI", pool="kilo", rpm_pool="kilo",
            base_url=_kilo_url, api_key=_kilo_key,
            role="candidate", rpm=20, skip_reason=_kilo_skip,
        ),
        ModelDef(
            model_id="arcee-ai/trinity-large-thinking:free",
            model_name="Arcee Trinity Large Thinking (Kilo free)",
            provider="Kilo AI", pool="kilo", rpm_pool="kilo",
            base_url=_kilo_url, api_key=_kilo_key,
            role="candidate", rpm=20, skip_reason=_kilo_skip,
        ),
    ]

    # ── NVIDIA NIM (NVIDIA_API_KEY) ─────────────────────────────────────────────
    models += [
        ModelDef(
            model_id="meta/llama-3.3-70b-instruct",
            model_name="Llama 3.3 70B (NVIDIA NIM)",
            provider="NVIDIA", pool="nvidia", rpm_pool="nvidia",
            base_url=_nv_url, api_key=_nv_key,
            role="candidate", rpm=30, skip_reason=_nv_skip,
        ),
    ]

    # ── Z.AI / GLM (ZAI_API_KEY) ────────────────────────────────────────────────
    models += [
        ModelDef(
            model_id="glm-4v-flash", model_name="GLM-4V Flash",
            provider="Z.AI", pool="zai", rpm_pool="zai",
            base_url=_zai_url, api_key=_zai_key,
            role="candidate", rpm=20, skip_reason=_zai_skip,
        ),
    ]

    # ── OpenRouter — candidatos generales ───────────────────────────────────────
    models += [
        ModelDef(
            model_id="arcee-ai/trinity-large-preview:free",
            model_name="Arcee Trinity Large (OpenRouter free)",
            provider="OpenRouter", pool="openrouter", rpm_pool="openrouter-free",
            base_url=_or_url, api_key=_or_key,
            role="candidate", rpm=10, skip_reason=_or_skip,
        ),
        ModelDef(
            model_id="meta-llama/llama-4-scout:free",
            model_name="Llama 4 Scout (OpenRouter free)",
            provider="OpenRouter", pool="openrouter", rpm_pool="openrouter-free",
            base_url=_or_url, api_key=_or_key,
            role="candidate", rpm=10,
            skip_reason="404 — ID no encontrado en OpenRouter free tier (2026-04-15). Verificar en openrouter.ai/models",
        ),
        ModelDef(
            model_id="stepfun/step-3.5-flash",
            model_name="Stepfun Step-3.5 Flash (OpenRouter)",
            provider="OpenRouter", pool="openrouter", rpm_pool="openrouter",
            base_url=_or_url, api_key=_or_key,
            role="candidate", rpm=20, skip_reason=_or_skip,
        ),
        ModelDef(
            model_id="bytedance-seed/seed-2.0-lite",
            model_name="ByteDance Seed 2.0 Lite (OpenRouter)",
            provider="OpenRouter", pool="openrouter", rpm_pool="openrouter",
            base_url=_or_url, api_key=_or_key,
            role="candidate", rpm=20, skip_reason=_or_skip,
        ),
    ]

    # ── Ollama Cloud — candidatos con sweep de reasoning modes ─────────────────
    # Modelos con sufijo :cloud se ejecutan remotamente vía `ollama signin`.
    models += [
        ModelDef(
            model_id="glm-5.1:cloud", model_name="GLM 5.1 [medium]",
            provider="Ollama Cloud", pool="ollama", rpm_pool="ollama",
            base_url=_ol_url, api_key="ollama", role="candidate",
            rpm=999, thinking_budget=2000, strip_thinking=True,
            reasoning_mode="medium", reasoning_style="budget_tokens",
        ),
        ModelDef(
            model_id="glm-5.1:cloud", model_name="GLM 5.1 [low]",
            provider="Ollama Cloud", pool="ollama", rpm_pool="ollama",
            base_url=_ol_url, api_key="ollama", role="candidate",
            rpm=999, thinking_budget=2000, strip_thinking=True,
            reasoning_mode="low", reasoning_style="budget_tokens",
        ),
        ModelDef(
            model_id="gemma4:31b-cloud", model_name="Gemma 4 31B [medium]",
            provider="Ollama Cloud", pool="ollama", rpm_pool="ollama",
            base_url=_ol_url, api_key="ollama", role="candidate",
            rpm=999, thinking_budget=1500, strip_thinking=True,
            reasoning_mode="medium", reasoning_style="budget_tokens",
        ),
        ModelDef(
            model_id="gemma4:31b-cloud", model_name="Gemma 4 31B [low]",
            provider="Ollama Cloud", pool="ollama", rpm_pool="ollama",
            base_url=_ol_url, api_key="ollama", role="candidate",
            rpm=999, thinking_budget=1500, strip_thinking=True,
            reasoning_mode="low", reasoning_style="budget_tokens",
        ),
        ModelDef(
            model_id="gemma4:31b-cloud", model_name="Gemma 4 31B [off]",
            provider="Ollama Cloud", pool="ollama", rpm_pool="ollama",
            base_url=_ol_url, api_key="ollama", role="candidate",
            rpm=999, thinking_budget=1500, strip_thinking=True,
            reasoning_mode="off", reasoning_style="budget_tokens",
        ),
        ModelDef(
            model_id="minimax-m2.7:cloud", model_name="MiniMax M2.7 (Ollama Cloud)",
            provider="Ollama Cloud", pool="ollama", rpm_pool="ollama",
            base_url=_ol_url, api_key="ollama", role="candidate",
            rpm=999, thinking_budget=2000, strip_thinking=True,
            reasoning_style="budget_tokens",
        ),
        ModelDef(
            model_id="minimax-m2.7:cloud", model_name="MiniMax M2.7 [off]",
            provider="Ollama Cloud", pool="ollama", rpm_pool="ollama",
            base_url=_ol_url, api_key="ollama", role="candidate",
            rpm=999, thinking_budget=2000, strip_thinking=True,
            reasoning_mode="off", reasoning_style="budget_tokens",
        ),
        ModelDef(
            model_id="nemotron-3-super:cloud",
            model_name="Nemotron 3 Super 120B (Ollama Cloud)",
            provider="Ollama Cloud", pool="ollama", rpm_pool="ollama",
            base_url=_ol_url, api_key="ollama", role="candidate", rpm=999,
        ),
        ModelDef(
            model_id="gemini-3-flash-preview:cloud",
            model_name="Gemini 3 Flash Preview (Ollama Cloud)",
            provider="Ollama Cloud", pool="ollama", rpm_pool="ollama",
            base_url=_ol_url, api_key="ollama", role="candidate", rpm=999,
        ),
        ModelDef(
            model_id="qwen3-coder:480b-cloud", model_name="Qwen3 Coder 480B [medium]",
            provider="Ollama Cloud", pool="ollama", rpm_pool="ollama",
            base_url=_ol_url, api_key="ollama", role="candidate",
            rpm=999, thinking_budget=2000, strip_thinking=True,
            reasoning_mode="medium", reasoning_style="budget_tokens",
        ),
        ModelDef(
            model_id="qwen3-coder:480b-cloud", model_name="Qwen3 Coder 480B [low]",
            provider="Ollama Cloud", pool="ollama", rpm_pool="ollama",
            base_url=_ol_url, api_key="ollama", role="candidate",
            rpm=999, thinking_budget=1500, strip_thinking=True,
            reasoning_mode="low", reasoning_style="budget_tokens",
        ),
        ModelDef(
            model_id="qwen3-coder:480b-cloud", model_name="Qwen3 Coder 480B [off]",
            provider="Ollama Cloud", pool="ollama", rpm_pool="ollama",
            base_url=_ol_url, api_key="ollama", role="candidate",
            rpm=999, thinking_budget=2000, strip_thinking=True,
            reasoning_mode="off", reasoning_style="budget_tokens",
        ),
    ]

    # ── MuleRouter (MULEROUTER_API_KEY) — Qwen con reasoning_effort ─────────────
    # reasoning_style="effort" → _build_extra envía reasoning_effort param.
    models += [
        ModelDef(
            model_id="qwen-flash", model_name="Qwen Flash [high]",
            provider="MuleRouter", pool="mulerouter", rpm_pool="mulerouter",
            base_url=_mr_url, api_key=_mr_key, role="candidate",
            rpm=20, reasoning_mode="high", reasoning_style="effort",
            skip_reason=_mr_skip,
        ),
        ModelDef(
            model_id="qwen-flash", model_name="Qwen Flash [medium]",
            provider="MuleRouter", pool="mulerouter", rpm_pool="mulerouter",
            base_url=_mr_url, api_key=_mr_key, role="candidate",
            rpm=20, reasoning_mode="medium", reasoning_style="effort",
            skip_reason=_mr_skip,
        ),
        ModelDef(
            model_id="qwen-flash", model_name="Qwen Flash [low]",
            provider="MuleRouter", pool="mulerouter", rpm_pool="mulerouter",
            base_url=_mr_url, api_key=_mr_key, role="candidate",
            rpm=20, reasoning_mode="low", reasoning_style="effort",
            skip_reason=_mr_skip,
        ),
        ModelDef(
            model_id="qwen-plus", model_name="Qwen Plus [medium]",
            provider="MuleRouter", pool="mulerouter", rpm_pool="mulerouter",
            base_url=_mr_url, api_key=_mr_key, role="candidate",
            rpm=20, reasoning_mode="medium", reasoning_style="effort",
            skip_reason=_mr_skip,
        ),
        ModelDef(
            model_id="qwen3-max", model_name="Qwen3 Max [high]",
            provider="MuleRouter", pool="mulerouter", rpm_pool="mulerouter",
            base_url=_mr_url, api_key=_mr_key, role="candidate",
            rpm=20, reasoning_mode="high", reasoning_style="effort",
            skip_reason=_mr_skip,
        ),
        ModelDef(
            model_id="qwen3-max", model_name="Qwen3 Max [medium]",
            provider="MuleRouter", pool="mulerouter", rpm_pool="mulerouter",
            base_url=_mr_url, api_key=_mr_key, role="candidate",
            rpm=20, reasoning_mode="medium", reasoning_style="effort",
            skip_reason=_mr_skip,
        ),
        ModelDef(
            model_id="qwen3-max", model_name="Qwen3 Max [low]",
            provider="MuleRouter", pool="mulerouter", rpm_pool="mulerouter",
            base_url=_mr_url, api_key=_mr_key, role="candidate",
            rpm=20, reasoning_mode="low", reasoning_style="effort",
            skip_reason=_mr_skip,
        ),
    ]

    # ── Sin balance / key inválida — skipped automáticamente ────────────────────
    models += [
        ModelDef(
            model_id="MiniMax-M1", model_name="MiniMax M1",
            provider="MiniMax", pool="minimax", rpm_pool="minimax",
            base_url="https://api.minimax.io/v1/", api_key=MINIMAX_KEY,
            role="candidate", rpm=30,
            skip_reason="sin saldo — 429 insufficient_balance (recargar en api.minimax.io)",
        ),
        ModelDef(
            model_id="moonshot-v1-8k", model_name="Moonshot v1 8K",
            provider="Moonshot", pool="moonshot", rpm_pool="moonshot",
            base_url="https://api.moonshot.cn/v1/", api_key=MOONSHOT_KEY,
            role="candidate", rpm=30,
            skip_reason="key inválida — regenerar en platform.moonshot.cn",
        ),
        ModelDef(
            model_id="glm-4-air", model_name="GLM-4 Air (ZhipuAI Legacy)",
            provider="ZhipuAI", pool="zhipu", rpm_pool="zhipu",
            base_url="https://open.bigmodel.cn/api/paas/v4/", api_key=ZHIPU_KEY,
            role="candidate", rpm=30,
            skip_reason="legacy endpoint China — reemplazado por ZAI",
        ),
    ]

    # ── Ollama local (OLLAMA_MODEL env var, opcional) ────────────────────────────
    if OLLAMA_MODEL and not any(m.model_id == OLLAMA_MODEL for m in models):
        models.append(ModelDef(
            model_id=OLLAMA_MODEL, model_name=f"Ollama/{OLLAMA_MODEL}",
            provider="Ollama", pool="ollama", rpm_pool="ollama",
            base_url=OLLAMA_URL, api_key="ollama",
            role="candidate", rpm=999,
        ))

    return models


# ── Rate limiter ──────────────────────────────────────────────────────────────
class RpmLimiter:
    """Per-rpm_pool rate limiter. Enforces minimum gap between consecutive calls."""

    def __init__(self) -> None:
        self._last: dict[str, float] = {}
        self._lock: dict[str, asyncio.Lock] = {}

    def _get_lock(self, pool: str) -> asyncio.Lock:
        if pool not in self._lock:
            self._lock[pool] = asyncio.Lock()
        return self._lock[pool]

    async def wait(self, rpm_pool: str, rpm: int) -> None:
        if rpm <= 0:
            return
        lock = self._get_lock(rpm_pool)
        async with lock:
            interval = 60.0 / rpm
            elapsed = time.monotonic() - self._last.get(rpm_pool, 0.0)
            if elapsed < interval:
                await asyncio.sleep(interval - elapsed)
            self._last[rpm_pool] = time.monotonic()


# ── Thinking tag stripper ─────────────────────────────────────────────────────
_THINK_RE = re.compile(
    r"<(?:think|thought|thinking)>.*?</(?:think|thought|thinking)>",
    re.DOTALL | re.IGNORECASE,
)


def strip_thinking(text: str) -> str:
    """Remove <think>/<thought>/<thinking> blocks from reasoning model output."""
    return _THINK_RE.sub("", text).strip()


# ── Incremental save + status ticker ─────────────────────────────────────────

async def _append_partial(new_results: list[BenchResult]) -> None:
    global _g_done_count
    if _g_lock is None:
        return
    async with _g_lock:
        _g_results.extend(new_results)
        _g_done_count += sum(1 for r in new_results if r.status != "skipped")
        if _g_partial_path:
            _g_partial_path.write_text(json.dumps(
                {"partial": True, "timestamp": datetime.now().isoformat(),
                 "results": [asdict(r) for r in _g_results]},
                indent=2, ensure_ascii=False,
            ))


async def _status_ticker(interval: int = 30) -> None:
    while True:
        await asyncio.sleep(interval)
        done = _g_done_count
        total = _g_total_expected
        pct = f"{done / total * 100:.0f}%" if total else "?"
        print(f"\n  ⏱  {done}/{total} ({pct}) tests completados", flush=True)


# ── Test cases ────────────────────────────────────────────────────────────────
TESTS: dict[str, dict] = {
    "simple": {
        "prompt": "What is the capital of Ecuador?",
        "expect": "quito",
    },
    "format": {
        "prompt": "Respond with only the word 'ok'. Nothing else.",
        "expect": "ok",
    },
    "multilang": {
        "prompt": (
            "Reply in English only: explain what a school attendance system does "
            "in one sentence."
        ),
        "expect": None,  # any coherent sentence
    },
    "spanish_input": {
        "prompt": "Answer in English: ¿qué es Python?",
        "expect": None,
    },
}

COMPOUND_TEST = {
    "prompt": (
        "What is today's USD/EUR exchange rate? Search for current data and mention your source."
    ),
}


# ── TOON — tool definitions ───────────────────────────────────────────────────
_TOON_TOOL_DEFS = [
    {
        "name": "mark_attendance",
        "description": "Records absences, tardiness, or justified absences for students in a course.",
        "parameters": {
            "nombres": "list[str] — last/first names of absent students. Empty list if all present.",
            "curso": "str — course abbreviation, e.g.: 3bt, 8egb, prep, 2bt",
            "fecha": "str — today | yesterday | YYYY-MM-DD (default: today)",
            "status": "str — absent | late | justified | all_present",
        },
        "required": ["nombres", "curso"],
    },
    {
        "name": "query_attendance",
        "description": "Queries the attendance record for one or more courses.",
        "parameters": {
            "cursos": "list[str] — course abbreviations, e.g.: ['3bt', '8egb']",
            "period": "str — today | yesterday | week | month | trimester_1 | trimester_2 | trimester_3",
        },
        "required": ["cursos"],
    },
    {
        "name": "mark_homework",
        "description": "Records a new homework assignment or activity for a course.",
        "parameters": {
            "descripcion": "str — full description of the assignment",
            "curso": "str — course abbreviation, e.g.: 3bt",
            "materias": "list[str] — subjects involved, e.g.: ['Math', 'Science']",
            "fecha_entrega": "str — due date YYYY-MM-DD or day name (optional)",
        },
        "required": ["descripcion", "curso"],
    },
]

_TOON_TOOLS_YAML = yaml.dump(
    {"tools": _TOON_TOOL_DEFS},
    allow_unicode=True,
    default_flow_style=False,
    sort_keys=False,
)

_TOON_SYSTEM_PROMPT = f"""\
You are a school assistant helping a teacher log attendance and homework.
When the teacher's message requires recording or querying data, respond ONLY with a TOON block.
If no tool is needed (e.g., a general question), respond directly in plain text — do NOT use a tool.

Available tools:
{_TOON_TOOLS_YAML}
To call a tool, respond with exactly this format (no extra text before or after):
```toon
tool_call:
  name: <tool_name>
  arguments:
    <key>: <value>
```"""

# ── TOON prompt sin ejemplos de formato ──────────────────────────────────────
# Mismo YAML de tool definitions — se elimina el bloque de ejemplo de formato.
# Objetivo: medir si los modelos infieren el formato TOON sin el ejemplo explícito.
# Ahorro estimado: ~60-80 tokens por llamada vs prompt completo.
_TOON_SYSTEM_PROMPT_NOEX = f"""\
You are a school assistant helping a teacher log attendance and homework.
When the teacher's message requires recording or querying data, respond ONLY with a TOON block.
If no tool is needed (e.g., a general question), respond directly in plain text — do NOT use a tool.

Available tools:
{_TOON_TOOLS_YAML}"""

# ── TOON — encoder / decoder ──────────────────────────────────────────────────
_TOON_BLOCK_RE  = re.compile(r"```toon\s*(.*?)```", re.DOTALL)
_JSON_BLOCK_RE  = re.compile(r"```(?:json|tool_call)\s*(\{.*?\})\s*```", re.DOTALL)
_TOON_NAME_RE   = re.compile(r"name:\s*(\S+)")
_TOON_ARGS_RE   = re.compile(r"arguments:\s*\n((?:\s+\S.+\n?)*)", re.MULTILINE)


def decode_toon(text: str) -> tuple[str | None, dict]:
    """Parse TOON block from model response. Returns (tool_name, args) or (None, {}).

    Handles:
      • Correct ```toon yaml block
      • JSON fallback (```json / ```tool_call blocks — e.g. Nemotron)
      • Regex fallback for partial output
    """
    # ── Try ```toon block first ───────────────────────────────────────────────
    m = _TOON_BLOCK_RE.search(text)
    if m:
        raw = m.group(1)
        try:
            parsed = yaml.safe_load(raw)
            if isinstance(parsed, dict):
                tc = parsed.get("tool_call", parsed.get("tool_calls", parsed))
                if isinstance(tc, list):
                    tc = tc[0]
                name = tc.get("name")
                args = tc.get("arguments", {})
                if name and isinstance(args, dict):
                    return str(name), args
        except Exception:
            pass
        # Regex fallback on the toon block
        name_m = _TOON_NAME_RE.search(raw)
        if name_m:
            name = name_m.group(1)
            args: dict = {}
            args_m = _TOON_ARGS_RE.search(raw)
            if args_m:
                for line in args_m.group(1).splitlines():
                    if ":" in line:
                        k, _, v = line.partition(":")
                        args[k.strip()] = v.strip()
            return name, args

    # ── Try JSON block (Nemotron and similar) ─────────────────────────────────
    jm = _JSON_BLOCK_RE.search(text)
    if jm:
        try:
            parsed = json.loads(jm.group(1))
            name = parsed.get("name")
            args = parsed.get("arguments", parsed.get("args", {}))
            if name and isinstance(args, dict):
                return str(name), args
        except Exception:
            pass

    # ── Try inline JSON anywhere in text ─────────────────────────────────────
    json_m = re.search(r'\{"name"\s*:\s*"([^"]+)".*?"arguments"\s*:\s*(\{[^}]*\})', text, re.DOTALL)
    if json_m:
        try:
            name = json_m.group(1)
            args = json.loads(json_m.group(2))
            return name, args
        except Exception:
            pass

    return None, {}


# ── TOON — test cases ─────────────────────────────────────────────────────────
# Each test: prompt (teacher message), expect_tool (None = no tool), expect_args (key checks)
TOON_TESTS: dict[str, dict] = {
    "att_absent": {
        "prompt": "Recalde missed class today, 3BT",
        "expect_tool": "mark_attendance",
        "expect_args": {"status": "absent"},
    },
    "att_late": {
        "prompt": "Tatiana arrived late today, 2nd BT",
        "expect_tool": "mark_attendance",
        "expect_args": {"status": "late"},
    },
    "att_all_present": {
        "prompt": "Everyone attended today, 8th grade EGB",
        "expect_tool": "mark_attendance",
        "expect_args": {"status": "all_present"},
    },
    "att_justified": {
        "prompt": "Juan has a justified absence today, 3BT",
        "expect_tool": "mark_attendance",
        "expect_args": {"status": "justified"},
    },
    "att_query": {
        "prompt": "Who was absent yesterday in 8th grade EGB?",
        "expect_tool": "query_attendance",
        "expect_args": {"period": "yesterday"},
    },
    "att_multi": {
        "prompt": "Recalde and Garcia were absent today, 1BT",
        "expect_tool": "mark_attendance",
        "expect_args": {"_nombres_min": 2},  # special: nombres must have >= 2 items
    },
    "hw_assign": {
        "prompt": "Math homework: exercises page 45, 3BT, due Friday",
        "expect_tool": "mark_homework",
        "expect_args": {"curso": "3bt"},
    },
    "no_tool": {
        "prompt": "How many days does November have? Answer directly.",
        "expect_tool": None,
        "expect_args": {},
    },
    "tool_choice": {
        "prompt": "Garcia was late, 2BT. Use the correct tool.",
        "expect_tool": "mark_attendance",
        "expect_args": {"status": "late"},
    },
    # Extended att_query — multiple course codes to detect truncation bugs (e.g. Gemini 3 Flash: 8egb→8eg)
    "att_query_long": {
        "prompt": "Show me who was absent this week in 8th grade EGB, prep, and 1BT.",
        "expect_tool": "query_attendance",
        "expect_args": {"period": "week"},
    },
}

# ── TOON tests sin ejemplos de formato (_noex) ────────────────────────────────
# Mismos casos que TOON_TESTS. call_toon_test detecta el sufijo _noex y usa
# _TOON_SYSTEM_PROMPT_NOEX (sin bloque de formato ejemplo).
TOON_TESTS_NOEX: dict[str, dict] = {
    f"{k}_noex": v for k, v in TOON_TESTS.items()
}

# ── JSON tool calling ─────────────────────────────────────────────────────────
_JSON_TOOLS_STR = json.dumps({"tools": _TOON_TOOL_DEFS}, indent=2, ensure_ascii=False)

_JSON_SYSTEM_PROMPT = f"""\
You are a school assistant helping a teacher log attendance and homework.
When the teacher's message requires recording or querying data, respond ONLY with a JSON object.
If no tool is needed (e.g., a general question), respond directly in plain text — do NOT use a tool.

Available tools:
{_JSON_TOOLS_STR}

To call a tool, respond with exactly this format (no extra text before or after):
{{"name": "<tool_name>", "arguments": {{<key>: <value>}}}}"""

# noex: sin bloque de ejemplo — mide si el modelo infiere {"name":...,"arguments":...} solo
_JSON_SYSTEM_PROMPT_NOEX = f"""\
You are a school assistant helping a teacher log attendance and homework.
When the teacher's message requires recording or querying data, respond ONLY with a JSON object.
If no tool is needed (e.g., a general question), respond directly in plain text — do NOT use a tool.

Available tools:
{_JSON_TOOLS_STR}"""

# JSON tests: mismos casos que TOON — sufijo _json / _json_noex
JSON_TESTS: dict[str, dict] = {f"{k}_json": v for k, v in TOON_TESTS.items()}
JSON_TESTS_NOEX: dict[str, dict] = {f"{k}_json_noex": v for k, v in TOON_TESTS.items()}

# ── Native OpenAI function calling tests (_nat) ───────────────────────────────
# Mismos casos que TOON_TESTS pero usando el API nativo de tool calling
# (tools=[], tool_choice="auto") — replica exactamente lo que hace llm_orchestrator.
_NATIVE_TOOL_DEFS_OPENAI = [
    {
        "type": "function",
        "function": {
            "name": "mark_attendance",
            "description": "Records absences, tardiness, or justified absences for students in a course.",
            "parameters": {
                "type": "object",
                "properties": {
                    "nombres": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Last/first names of absent students. Empty list if all present.",
                    },
                    "curso": {
                        "type": "string",
                        "description": "Course abbreviation, e.g.: 3bt, 8egb, prep, 2bt",
                    },
                    "fecha": {
                        "type": "string",
                        "description": "today | yesterday | YYYY-MM-DD (default: today)",
                    },
                    "status": {
                        "type": "string",
                        "enum": ["absent", "late", "justified", "all_present"],
                    },
                },
                "required": ["nombres", "curso"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "query_attendance",
            "description": "Queries the attendance record for one or more courses.",
            "parameters": {
                "type": "object",
                "properties": {
                    "cursos": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Course abbreviations, e.g.: ['3bt', '8egb']",
                    },
                    "period": {
                        "type": "string",
                        "description": "today | yesterday | week | month | trimester_1 | trimester_2 | trimester_3",
                    },
                },
                "required": ["cursos"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "mark_homework",
            "description": "Records a new homework assignment or activity for a course.",
            "parameters": {
                "type": "object",
                "properties": {
                    "descripcion": {
                        "type": "string",
                        "description": "Full description of the assignment",
                    },
                    "curso": {
                        "type": "string",
                        "description": "Course abbreviation, e.g.: 3bt",
                    },
                    "materias": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Subjects involved, e.g.: ['Math', 'Science']",
                    },
                    "fecha_entrega": {
                        "type": "string",
                        "description": "Due date YYYY-MM-DD or day name (optional)",
                    },
                },
                "required": ["descripcion", "curso"],
            },
        },
    },
]

_NATIVE_SYSTEM = (
    "You are a school assistant helping a teacher log attendance and homework. "
    "Use the provided tools when needed. "
    "If no tool is needed (e.g., a general knowledge question), respond directly in plain text."
)

NATIVE_TESTS: dict[str, dict] = {f"{k}_nat": v for k, v in TOON_TESTS.items()}

# ── Planner tests (_pln) ──────────────────────────────────────────────────────
# Replica agent/planner.py: mismo system prompt, response_format=json_object,
# espera JSON array [{tool, params}] — NO tool_choice=auto.
# Cubre los domain controllers reales de schoolai2: attendance y homework.

_PLANNER_SYSTEM = """\
You are a planning assistant for a school management system.

Given a teacher's request and the available tools, return a JSON array of steps to execute.
Each step: {{"tool": "<name>", "params": {{<key>: <value>}}}}

Rules:
- Return ONLY a JSON array wrapped in a JSON object key "steps". No explanation.
- Use only tools from the provided list.
- Minimum steps needed — no redundant calls.
- If the request is conversational (no action needed), return {{"steps": []}}.

Available tools:
{tools}"""

_PLANNER_TOOLS_ATTENDANCE = [
    {
        "name": "record_attendance",
        "description": "Register absent, late, or justified students in a course.",
        "parameters": {
            "names": {"type": "array", "items": {"type": "string"}, "description": "Student names"},
            "course": {"type": "string", "description": "Course code or name, e.g. '3BT'"},
            "date": {"type": "string", "description": "Date: 'today', 'yesterday', or DD/MM/YYYY", "default": "today"},
            "status": {"type": "string", "enum": ["absent", "late", "justified", "all_present"], "default": "absent"},
        },
        "required": ["names", "course"],
    },
    {
        "name": "query_attendance",
        "description": "Query attendance records for a course on a given period.",
        "parameters": {
            "course": {"type": "string", "description": "Course code or name"},
            "period": {"type": "string", "description": "Period: 'today', 'yesterday', 'week', 'month'", "default": "today"},
        },
        "required": ["course"],
    },
    {
        "name": "list_courses",
        "description": "List available courses, optionally filtered by level.",
        "parameters": {
            "level": {"type": "string", "description": "Optional level filter"},
        },
        "required": [],
    },
]

_PLANNER_TOOLS_HOMEWORK = [
    {
        "name": "create_assignment",
        "description": "Create a homework assignment for a course.",
        "parameters": {
            "course": {"type": "string", "description": "Course code or name"},
            "subject": {"type": "string", "description": "Subject name"},
            "description": {"type": "string", "description": "Assignment description"},
            "due_date": {"type": "string", "description": "Due date: 'tomorrow', day name, or DD/MM/YYYY"},
        },
        "required": ["course", "description"],
    },
    {
        "name": "query_assignments",
        "description": "List pending homework assignments for a course.",
        "parameters": {
            "course": {"type": "string", "description": "Course code or name"},
            "period": {"type": "string", "description": "Period: 'trimestre', 'week', 'month'", "default": "trimestre"},
        },
        "required": ["course"],
    },
    {
        "name": "delete_assignment",
        "description": "Delete a homework assignment by number.",
        "parameters": {
            "number": {"type": "integer", "description": "Assignment number from the list"},
            "course": {"type": "string", "description": "Course code or name"},
        },
        "required": ["number", "course"],
    },
]

_PLANNER_TOOLS_GENERAL = [
    {
        "name": "list_courses",
        "description": "List available courses.",
        "parameters": {
            "level": {"type": "string", "description": "Optional level filter"},
        },
        "required": [],
    },
]

_PLANNER_TOOLS: dict[str, list] = {
    "attendance": _PLANNER_TOOLS_ATTENDANCE,
    "homework":   _PLANNER_TOOLS_HOMEWORK,
    "general":    _PLANNER_TOOLS_GENERAL,
}

PLANNER_TESTS: dict[str, dict] = {
    # Attendance — registro de ausencias
    "pln_att_absent": {
        "domain": "attendance",
        "message": "Falta Tatiana y Mario en 3BT",
        "expect_tool": "record_attendance",
        "expect_params": ["names", "course"],
    },
    # Attendance — registro tardanza
    "pln_att_late": {
        "domain": "attendance",
        "message": "Tatiana llegó atrasada en primero BT",
        "expect_tool": "record_attendance",
        "expect_params": ["names", "course"],
        "expect_status": "late",
    },
    # Attendance — consulta
    "pln_att_query": {
        "domain": "attendance",
        "message": "Muéstrame las faltas de hoy en 2do A",
        "expect_tool": "query_attendance",
        "expect_params": ["course"],
    },
    # Homework — crear tarea
    "pln_hw_create": {
        "domain": "homework",
        "message": "Registra tarea de matemáticas para el viernes para 3BT: ejercicios capítulo 5",
        "expect_tool": "create_assignment",
        "expect_params": ["course", "description"],
    },
    # Homework — consultar tareas pendientes
    "pln_hw_query": {
        "domain": "homework",
        "message": "Qué tareas tienen pendientes los de 2BT?",
        "expect_tool": "query_assignments",
        "expect_params": ["course"],
    },
    # No-action — saludo → plan vacío
    "pln_no_action": {
        "domain": "general",
        "message": "Hola, buenos días profe",
        "expect_tool": None,
        "expect_params": [],
    },
}

# ── Test suite por rol ────────────────────────────────────────────────────────
# Cada rol corre solo los tests relevantes para su función real en producción.
# "candidate" = sin rol asignado → evaluación completa para determinar el mejor fit.
_SUITE_LATENCY = frozenset(TESTS)
_SUITE_JSON    = frozenset(JSON_TESTS) | frozenset(JSON_TESTS_NOEX)
_SUITE_TOON    = frozenset(TOON_TESTS) | frozenset(TOON_TESTS_NOEX)
_SUITE_NATIVE  = frozenset(NATIVE_TESTS)
_SUITE_PLANNER = frozenset(PLANNER_TESTS)

_ROLE_SUITES: dict[str, frozenset] = {
    # Classifier: gateway/router.py — classify {domain,intent,entities} via JSON
    "classifier":          _SUITE_LATENCY | _SUITE_JSON,
    "classifier_fallback": _SUITE_LATENCY | _SUITE_JSON,
    # Planner: agent/planner.py — JSON plan [{tool,params}], NO tool_choice=auto
    "planner":          _SUITE_LATENCY | _SUITE_JSON | _SUITE_PLANNER,
    "planner_fallback": _SUITE_LATENCY | _SUITE_JSON | _SUITE_PLANNER,
    # Synthesizer: agent/synthesizer.py — respuesta conversacional en español
    "synthesizer":          _SUITE_LATENCY,
    "synthesizer_fallback": _SUITE_LATENCY,
    # Vision: modelos multimodales — sin tests de texto estructurado
    "vision":          _SUITE_LATENCY,
    "vision_fallback": _SUITE_LATENCY,
    # Candidate: evaluación completa para determinar mejor fit
    "candidate": _SUITE_LATENCY | _SUITE_JSON | _SUITE_TOON | _SUITE_NATIVE | _SUITE_PLANNER,
    # Aliases legacy (compat con JSONs de benchmark anteriores)
    "extractor":         _SUITE_LATENCY | _SUITE_JSON,
    "extractor+router":  _SUITE_LATENCY | _SUITE_JSON,
    "orchestrator":           _SUITE_LATENCY | _SUITE_TOON | _SUITE_NATIVE,
    "orchestrator_fallback":  _SUITE_LATENCY | _SUITE_TOON | _SUITE_NATIVE,
    "chat":          _SUITE_LATENCY,
    "chat_fallback": _SUITE_LATENCY,
}


def _get_suite(role: str) -> frozenset:
    """Test IDs válidos para el rol dado. Roles desconocidos → suite completa."""
    return _ROLE_SUITES.get(role, _SUITE_LATENCY | _SUITE_JSON | _SUITE_TOON | _SUITE_NATIVE)


_JSON_DECODER = json.JSONDecoder()


def decode_json_response(text: str) -> tuple[str | None, dict]:
    """Parse JSON tool call from model response. Returns (tool_name, args) or (None, {}).

    Accepts multiple key schemas models use:
      • {"name": "tool", "arguments": {...}}           ← canonical
      • {"tool": "name", "parameters": {...}}          ← Mistral Medium style
      • {"function": {"name": "tool", "arguments": {}}} ← some OpenAI-style models

    Uses raw_decode() to properly handle nested braces (greedy, depth-aware).
    """
    clean = re.sub(r"```(?:json)?\s*", "", text).replace("```", "").strip()
    i = 0
    while i < len(clean):
        idx = clean.find('{', i)
        if idx == -1:
            break
        try:
            obj, end = _JSON_DECODER.raw_decode(clean, idx)
        except json.JSONDecodeError:
            i = idx + 1
            continue
        if isinstance(obj, dict):
            name = obj.get("name") or obj.get("tool") or obj.get("tool_name")
            args = (obj.get("arguments") or obj.get("parameters")
                    or obj.get("args") or obj.get("input") or {})
            if not name and isinstance(obj.get("function"), dict):
                name = obj["function"].get("name")
                args = obj["function"].get("arguments", {})
            if name and isinstance(args, dict):
                return str(name), args
        i = end
    return None, {}


async def call_json_test(model: ModelDef, test_id: str) -> BenchResult:
    """Run a single JSON tool-calling test."""
    noex = test_id.endswith("_json_noex")
    base_id = test_id.removesuffix("_json_noex").removesuffix("_json")
    test = TOON_TESTS[base_id]
    system_prompt = _JSON_SYSTEM_PROMPT_NOEX if noex else _JSON_SYSTEM_PROMPT
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": test["prompt"]},
    ]

    max_tokens = 512 + model.effective_thinking_budget()

    client = AsyncOpenAI(api_key=model.api_key, base_url=model.base_url, timeout=CALL_TIMEOUT)
    kwargs: dict = dict(model=model.model_id, messages=messages,
                        max_tokens=max_tokens, temperature=0, stream=True)
    extra_body, messages = _build_extra(model, messages)
    if extra_body:
        kwargs["extra_body"] = extra_body
    if model.stream_usage:
        kwargs["stream_options"] = {"include_usage": True}

    t0 = time.monotonic()
    ttft_ms: Optional[int] = None
    content_parts: list[str] = []
    output_tokens: Optional[int] = None
    reasoning_tokens: Optional[int] = None
    status = "ok"
    error_str = ""
    content = ""

    try:
        stream = await client.chat.completions.create(**kwargs)
        async for chunk in stream:
            if ttft_ms is None and chunk.choices and chunk.choices[0].delta.content:
                ttft_ms = int((time.monotonic() - t0) * 1000)
            if chunk.choices and chunk.choices[0].delta.content:
                content_parts.append(chunk.choices[0].delta.content)
            if chunk.usage:
                output_tokens = chunk.usage.completion_tokens
                if hasattr(chunk.usage, "completion_tokens_details") and chunk.usage.completion_tokens_details:
                    d = chunk.usage.completion_tokens_details
                    if hasattr(d, "reasoning_tokens") and d.reasoning_tokens:
                        reasoning_tokens = d.reasoning_tokens

        content = "".join(content_parts)
        if not content:
            status = "empty"
        elif model.strip_thinking:
            content = strip_thinking(content)
    except Exception as exc:
        status = "error"
        error_str = str(exc)[:200]

    total_ms = int((time.monotonic() - t0) * 1000)

    toon_valid: Optional[bool] = None
    correct_tool: Optional[bool] = None
    correct_args: Optional[bool] = None
    toon_raw = ""

    if status == "ok":
        expect_tool = test.get("expect_tool")
        if expect_tool is None:
            # no_tool: valid if response has no JSON tool call
            tool_name, _ = decode_json_response(content)
            toon_valid = tool_name is None
            correct_tool = toon_valid
            correct_args = toon_valid
            toon_raw = content[:120]
        else:
            tool_name, args = decode_json_response(content)
            toon_raw = content[:120]
            toon_valid = tool_name is not None
            correct_tool = toon_valid and tool_name == expect_tool
            correct_args = correct_tool and _check_toon_args(args, test.get("expect_args", {}))

    preview = content[:80].replace("\n", " ") if content else error_str[:80]
    toon_score = ""
    if toon_valid is not None:
        toon_score = (f" | JSON {'✓' if toon_valid else '✗'}"
                      f" tool {'✓' if correct_tool else '✗'}"
                      f" args {'✓' if correct_args else '✗'}")
    print(f"  [{model.pool}] {model.model_name} | {test_id} run1"
          f" → {status} | TTFT {ttft_ms or '—'}ms | total {total_ms}ms{toon_score}")

    return BenchResult(
        model_id=model.model_id, model_name=model.model_name,
        provider=model.provider, pool=model.pool, role=model.role, in_use=model.in_use,
        test_id=test_id, status=status, ttft_ms=ttft_ms, total_ms=total_ms,
        output_tokens=output_tokens, reasoning_tokens=reasoning_tokens,
        content_preview=preview, error=error_str,
        toon_valid=toon_valid, correct_tool=correct_tool, correct_args=correct_args,
        toon_raw=toon_raw,
    )


def _check_toon_args(args: dict, expect_args: dict) -> bool:
    """Check that all expected arg key/values are present in actual args."""
    for k, v in expect_args.items():
        if k == "_nombres_min":
            # special: nombres list must have at least v items
            actual = args.get("nombres", args.get("names", []))
            if isinstance(actual, str):
                actual = [actual]
            if len(actual) < v:
                return False
        else:
            actual_v = str(args.get(k, "")).lower().strip()
            if str(v).lower().strip() not in actual_v:
                return False
    return True


# ── Result dataclass ──────────────────────────────────────────────────────────
@dataclass
class BenchResult:
    model_id: str
    model_name: str
    provider: str
    pool: str
    role: str
    in_use: bool
    test_id: str
    status: str           # "ok" | "error" | "empty" | "timeout" | "skipped"
    skip_reason: str = ""
    ttft_ms: Optional[int] = None
    total_ms: int = 0
    output_tokens: Optional[int] = None
    reasoning_tokens: Optional[int] = None
    content_preview: str = ""
    error: str = ""
    # TOON fields (Phase 2)
    toon_valid: Optional[bool] = None      # TOON block parseable
    correct_tool: Optional[bool] = None    # called expected tool
    correct_args: Optional[bool] = None    # key args matched
    toon_raw: str = ""                     # raw toon block for debug

    @property
    def tok_per_s(self) -> Optional[float]:
        """Tokens per second (output_tokens / total_seconds). None if data unavailable."""
        if self.output_tokens and self.total_ms > 0:
            return round(self.output_tokens / (self.total_ms / 1000), 1)
        return None


# ── Core call ─────────────────────────────────────────────────────────────────
CALL_TIMEOUT  = 45.0   # httpx socket timeout (passed to AsyncOpenAI)
TASK_TIMEOUT  = 55.0   # asyncio-level cancel — catches mid-stream hangs
POOL_TIMEOUT  = 600.0  # max 10 min per pool before forced cancel

# ── Global state: incremental saves + SIGINT recovery ────────────────────────
_g_lock: asyncio.Lock | None = None
_g_results: list[BenchResult] = []
_g_partial_path: Optional[Path] = None
_g_done_count: int = 0
_g_total_expected: int = 0


def _build_extra(model: ModelDef, messages: list[dict]) -> tuple[dict, list[dict]]:
    """Return (extra_body, messages) with provider-specific reasoning config applied.

    Centralises thinking_config / enable_thinking / reasoning_effort so that
    call_once, call_json_test and call_toon_test all behave identically.
    """
    extra_body: dict = {}
    effective_budget = model.effective_thinking_budget()

    if model.reasoning_style == "qwen":
        enable = model.reasoning_mode != "off"
        extra_body["enable_thinking"] = enable
        if not enable and messages and messages[-1]["role"] == "user":
            messages = messages[:-1] + [
                {**messages[-1], "content": "/no_think\n" + messages[-1]["content"]}
            ]
    elif model.reasoning_style == "effort":
        effort_map = {"high": "high", "medium": "medium", "low": "low", "off": "low"}
        extra_body["reasoning_effort"] = effort_map.get(model.reasoning_mode, "medium")
    elif model.reasoning_style == "budget_tokens":
        # Gemma 4 / Ollama: thinkingConfig. DeepSeek: budget via max_tokens only.
        if effective_budget > 0:
            extra_body["thinking_config"] = {"thinking_budget": effective_budget}

    if model.hf_provider:
        extra_body["provider"] = model.hf_provider

    return extra_body, messages


async def call_once(
    model: ModelDef,
    messages: list[dict],
    extra_headers: dict | None = None,
) -> BenchResult:
    """Single LLM call with streaming TTFT measurement."""
    client = AsyncOpenAI(
        api_key=model.api_key,
        base_url=model.base_url,
        timeout=CALL_TIMEOUT,
    )

    effective_budget = model.effective_thinking_budget()
    max_tokens = 256 + effective_budget
    kwargs: dict = dict(
        model=model.model_id,
        messages=messages,
        max_tokens=max_tokens,
        temperature=0,
        stream=True,
    )
    if extra_headers:
        kwargs["extra_headers"] = extra_headers

    extra_body, messages = _build_extra(model, messages)
    if extra_body:
        kwargs["extra_body"] = extra_body

    # ── stream_options for providers that need it (Google/Gemini) ─────────────
    if model.stream_usage:
        kwargs["stream_options"] = {"include_usage": True}

    t0 = time.monotonic()
    ttft_ms: Optional[int] = None
    content_parts: list[str] = []
    content = ""
    output_tokens: Optional[int] = None
    reasoning_tokens: Optional[int] = None
    status = "ok"
    error_str = ""

    try:
        stream = await client.chat.completions.create(**kwargs)
        async for chunk in stream:
            if ttft_ms is None and chunk.choices:
                delta = chunk.choices[0].delta
                if delta.content:
                    ttft_ms = int((time.monotonic() - t0) * 1000)
            if chunk.choices:
                delta = chunk.choices[0].delta
                if delta.content:
                    content_parts.append(delta.content)
            # usage in last chunk
            if chunk.usage:
                output_tokens = chunk.usage.completion_tokens
                if hasattr(chunk.usage, "completion_tokens_details") and chunk.usage.completion_tokens_details:
                    d = chunk.usage.completion_tokens_details
                    if hasattr(d, "reasoning_tokens") and d.reasoning_tokens:
                        reasoning_tokens = d.reasoning_tokens

        content = "".join(content_parts)

        # Fair retry: if streaming returned empty but usage present, try non-streaming
        if not content and output_tokens and output_tokens > 0:
            kwargs2 = {k: v for k, v in kwargs.items() if k != "stream"}
            resp = await client.chat.completions.create(**kwargs2, stream=False)
            if resp.choices:
                content = resp.choices[0].message.content or ""
                if resp.usage:
                    output_tokens = resp.usage.completion_tokens

        if not content:
            status = "empty"
        elif model.strip_thinking:
            content = strip_thinking(content)

    except TimeoutError:
        status = "timeout"
        error_str = "request timed out"
    except Exception as exc:
        status = "error"
        error_str = str(exc)[:200]

    total_ms = int((time.monotonic() - t0) * 1000)
    preview = (content[:120] + "…") if len(content) > 120 else content

    return BenchResult(
        model_id=model.model_id,
        model_name=model.model_name,
        provider=model.provider,
        pool=model.pool,
        role=model.role,
        in_use=model.in_use,
        test_id="",
        status=status,
        ttft_ms=ttft_ms,
        total_ms=total_ms,
        output_tokens=output_tokens,
        reasoning_tokens=reasoning_tokens,
        content_preview=preview,
        error=error_str,
    )


async def call_compound(model: ModelDef) -> BenchResult:
    """Separate test for compound-beta (web-search agent)."""
    messages = [{"role": "user", "content": COMPOUND_TEST["prompt"]}]
    result = await call_once(model, messages)
    result.test_id = "compound_web_search"
    return result


async def call_native_test(model: ModelDef, test_id: str) -> BenchResult:
    """Llama al modelo con function calling nativo (tools=[], tool_choice=auto).

    Replica exactamente lo que hace llm_orchestrator (base.py ReAct loop).
    El test_id debe terminar en _nat y estar en NATIVE_TESTS.
    """
    base_id = test_id.removesuffix("_nat")
    test = TOON_TESTS[base_id]
    expect_tool = test.get("expect_tool")

    messages = [
        {"role": "system", "content": _NATIVE_SYSTEM},
        {"role": "user", "content": test["prompt"]},
    ]

    client = AsyncOpenAI(api_key=model.api_key, base_url=model.base_url, timeout=CALL_TIMEOUT)
    nat_max_tokens = 512 + model.effective_thinking_budget()
    kwargs: dict = dict(
        model=model.model_id,
        messages=messages,
        tools=_NATIVE_TOOL_DEFS_OPENAI,
        tool_choice="auto",
        temperature=0,
        max_tokens=nat_max_tokens,
    )

    t0 = time.monotonic()
    status = "ok"
    error_str = ""
    toon_valid: Optional[bool] = None
    correct_tool: Optional[bool] = None
    correct_args: Optional[bool] = None
    toon_raw = ""
    ttft_ms: Optional[int] = None

    try:
        response = await client.chat.completions.create(**kwargs)
        total_ms = int((time.monotonic() - t0) * 1000)
        msg = response.choices[0].message

        if msg.tool_calls:
            ttft_ms = total_ms  # non-streaming: todo llega junto
            tc = msg.tool_calls[0]
            tool_name = tc.function.name
            try:
                args = json.loads(tc.function.arguments)
            except json.JSONDecodeError:
                args = {}
            toon_raw = f"{tool_name}({tc.function.arguments[:80]})"

            if expect_tool is None:
                # no_tool test — no debería haber llamado una herramienta
                toon_valid = False
                correct_tool = False
                correct_args = False
            else:
                toon_valid = True
                correct_tool = tool_name == expect_tool
                correct_args = correct_tool and _check_toon_args(args, test.get("expect_args", {}))
        else:
            # El modelo respondió con texto
            content = (msg.content or "").strip()
            toon_raw = content[:80]
            if expect_tool is None:
                # no_tool test — correcto
                toon_valid = True
                correct_tool = True
                correct_args = True
            else:
                # Esperaba tool call pero el modelo respondió en texto
                toon_valid = False
                correct_tool = False
                correct_args = False
            status = "ok" if toon_valid else "error"

    except Exception as exc:
        total_ms = int((time.monotonic() - t0) * 1000)
        status = "error"
        error_str = str(exc)[:200]

    toon_score = ""
    if toon_valid is not None:
        toon_score = (
            f" | NAT {'✓' if toon_valid else '✗'}"
            f" tool {'✓' if correct_tool else '✗'}"
            f" args {'✓' if correct_args else '✗'}"
        )
    print(
        f"  [{model.pool}] {model.model_name} | {test_id}"
        f" → {status} | TTFT {ttft_ms or '—'}ms | total {total_ms}ms{toon_score}"
    )

    return BenchResult(
        model_id=model.model_id, model_name=model.model_name,
        provider=model.provider, pool=model.pool, role=model.role, in_use=model.in_use,
        test_id=test_id, status=status, ttft_ms=ttft_ms, total_ms=total_ms,
        content_preview=toon_raw, error=error_str,
        toon_valid=toon_valid, correct_tool=correct_tool, correct_args=correct_args,
        toon_raw=toon_raw,
    )


async def call_planner_test(model: ModelDef, test_id: str) -> BenchResult:
    """Replica agent/planner.py: response_format=json_object, espera [{tool,params}].

    Usa el mismo system prompt y tool definitions que el planner real de schoolai2.
    Parsea siguiendo la misma lógica: array directo, step único, o wrapped {steps:[...]}.
    """
    test = PLANNER_TESTS[test_id]
    domain = test["domain"]
    tools_desc = json.dumps(_PLANNER_TOOLS[domain], ensure_ascii=False, indent=2)
    system = _PLANNER_SYSTEM.format(tools=tools_desc)

    messages = [
        {"role": "system", "content": system},
        {"role": "user", "content": test["message"]},
    ]

    client = AsyncOpenAI(api_key=model.api_key, base_url=model.base_url, timeout=CALL_TIMEOUT)
    pln_max_tokens = 512 + model.effective_thinking_budget()
    kwargs: dict = dict(
        model=model.model_id,
        messages=messages,
        temperature=0,
        max_tokens=pln_max_tokens,
        response_format={"type": "json_object"},
    )

    t0 = time.monotonic()
    status = "ok"
    error_str = ""
    toon_valid: Optional[bool] = None
    correct_tool: Optional[bool] = None
    correct_args: Optional[bool] = None
    toon_raw = ""
    ttft_ms: Optional[int] = None

    try:
        response = await client.chat.completions.create(**kwargs)
        total_ms = int((time.monotonic() - t0) * 1000)
        ttft_ms = total_ms  # non-streaming: todo llega junto
        content = response.choices[0].message.content or "{}"
        toon_raw = content[:120]

        # Parsear siguiendo la misma lógica que agent/planner.py
        raw = json.loads(content)
        if isinstance(raw, list):
            steps = raw
        elif isinstance(raw, dict) and "tool" in raw:
            steps = [raw]
        else:
            steps = next((v for v in raw.values() if isinstance(v, list)), [])

        expect_tool = test.get("expect_tool")
        expect_params: list[str] = test.get("expect_params", [])
        toon_valid = True  # JSON parseable

        if expect_tool is None:
            # Saludo → plan vacío
            correct_tool = len(steps) == 0
            correct_args = correct_tool
        elif steps:
            first = steps[0]
            got_tool   = first.get("tool", "")
            got_params = first.get("params", {})
            correct_tool = got_tool == expect_tool
            correct_args = correct_tool and all(p in got_params for p in expect_params)
            if correct_args and "expect_status" in test:
                correct_args = got_params.get("status") == test["expect_status"]
        else:
            correct_tool = False
            correct_args = False

        status = "ok" if correct_tool else "error"

    except json.JSONDecodeError as exc:
        total_ms = int((time.monotonic() - t0) * 1000)
        toon_valid = False
        correct_tool = False
        correct_args = False
        status = "error"
        error_str = f"JSON parse: {exc}"
    except Exception as exc:
        total_ms = int((time.monotonic() - t0) * 1000)
        status = "error"
        error_str = str(exc)[:200]

    pln_score = ""
    if toon_valid is not None:
        pln_score = (
            f" | PLN {'✓' if toon_valid else '✗'}"
            f" tool {'✓' if correct_tool else '✗'}"
            f" args {'✓' if correct_args else '✗'}"
        )
    print(
        f"  [{model.pool}] {model.model_name} | {test_id}"
        f" → {status} | total {total_ms}ms{pln_score}"
    )

    return BenchResult(
        model_id=model.model_id, model_name=model.model_name,
        provider=model.provider, pool=model.pool, role=model.role, in_use=model.in_use,
        test_id=test_id, status=status, ttft_ms=ttft_ms, total_ms=total_ms,
        content_preview=toon_raw, error=error_str,
        toon_valid=toon_valid, correct_tool=correct_tool, correct_args=correct_args,
        toon_raw=toon_raw,
    )


async def call_toon_test(model: ModelDef, test_id: str) -> BenchResult:
    """Run a single TOON tool-calling test. Uses TOON system prompt, parses response.

    If test_id ends with '_noex', uses _TOON_SYSTEM_PROMPT_NOEX (same tool defs,
    no format example block) to measure if models can infer the TOON format without
    an explicit example — reducing token load in production.
    """
    noex = test_id.endswith("_noex")
    base_id = test_id[:-5] if noex else test_id
    test = TOON_TESTS[base_id]
    system_prompt = _TOON_SYSTEM_PROMPT_NOEX if noex else _TOON_SYSTEM_PROMPT
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": test["prompt"]},
    ]

    toon_max_tokens = 512 + model.effective_thinking_budget()

    client = AsyncOpenAI(
        api_key=model.api_key,
        base_url=model.base_url,
        timeout=CALL_TIMEOUT,
    )
    kwargs: dict = dict(
        model=model.model_id,
        messages=messages,
        max_tokens=toon_max_tokens,
        temperature=0,
        stream=True,
    )
    extra_body, messages = _build_extra(model, messages)
    if extra_body:
        kwargs["extra_body"] = extra_body
    if model.stream_usage:
        kwargs["stream_options"] = {"include_usage": True}

    t0 = time.monotonic()
    ttft_ms: Optional[int] = None
    content_parts: list[str] = []
    output_tokens: Optional[int] = None
    reasoning_tokens: Optional[int] = None
    status = "ok"
    error_str = ""
    content = ""

    try:
        stream = await client.chat.completions.create(**kwargs)
        async for chunk in stream:
            if ttft_ms is None and chunk.choices:
                delta = chunk.choices[0].delta
                if delta.content:
                    ttft_ms = int((time.monotonic() - t0) * 1000)
            if chunk.choices:
                delta = chunk.choices[0].delta
                if delta.content:
                    content_parts.append(delta.content)
            if chunk.usage:
                output_tokens = chunk.usage.completion_tokens
                if hasattr(chunk.usage, "completion_tokens_details") and chunk.usage.completion_tokens_details:
                    d = chunk.usage.completion_tokens_details
                    if hasattr(d, "reasoning_tokens") and d.reasoning_tokens:
                        reasoning_tokens = d.reasoning_tokens

        content = "".join(content_parts)
        if not content and output_tokens and output_tokens > 0:
            kwargs2 = {k: v for k, v in kwargs.items() if k != "stream"}
            resp = await client.chat.completions.create(**kwargs2, stream=False)
            if resp.choices:
                content = resp.choices[0].message.content or ""

        if not content:
            status = "empty"
        elif model.strip_thinking:
            content = strip_thinking(content)

    except TimeoutError:
        status = "timeout"
        error_str = "request timed out"
    except Exception as exc:
        err_msg = str(exc)
        # GPT-OSS 20B (Groq) triggers native tool calling when it sees tool defs in system prompt.
        # The API rejects it with "Tool choice is none, but model called a tool".
        # Record as a specific TOON failure mode, not a generic error.
        if "called a tool" in err_msg or "tool choice" in err_msg.lower():
            status = "toon_native_call"
            error_str = "model triggered native tool calling instead of TOON text format"
        else:
            status = "error"
            error_str = err_msg[:200]

    total_ms = int((time.monotonic() - t0) * 1000)
    preview = (content[:120] + "…") if len(content) > 120 else content

    # Scoring
    toon_valid: Optional[bool] = None
    correct_tool: Optional[bool] = None
    correct_args: Optional[bool] = None
    toon_raw = ""
    expect_tool = test["expect_tool"]

    if status == "toon_native_call":
        toon_valid = False
        correct_tool = False
        correct_args = False
        toon_raw = "[native tool call — not TOON text format]"
    elif status in ("ok", "empty") and content:
        # Extract raw toon block for debug
        m = _TOON_BLOCK_RE.search(content)
        toon_raw = m.group(1).strip() if m else ""

        if expect_tool is None:
            # Expect NO tool call — valid if no ```toon block found
            toon_valid = not bool(m)
            correct_tool = toon_valid
            correct_args = toon_valid
        else:
            tool_name, args = decode_toon(content)
            toon_valid = tool_name is not None
            correct_tool = tool_name == expect_tool if toon_valid else False
            correct_args = _check_toon_args(args, test["expect_args"]) if correct_tool else False

    result = BenchResult(
        model_id=model.model_id,
        model_name=model.model_name,
        provider=model.provider,
        pool=model.pool,
        role=model.role,
        in_use=model.in_use,
        test_id=test_id,
        status=status,
        ttft_ms=ttft_ms,
        total_ms=total_ms,
        output_tokens=output_tokens,
        reasoning_tokens=reasoning_tokens,
        content_preview=preview,
        error=error_str,
        toon_valid=toon_valid,
        correct_tool=correct_tool,
        correct_args=correct_args,
        toon_raw=toon_raw,
    )
    return result


async def run_model_tests(
    model: ModelDef,
    test_ids: list[str],
    limiter: RpmLimiter,
    runs: int,
    delay_ms: int,
) -> list[BenchResult]:
    """Run all requested tests on a single model, sequentially."""
    results: list[BenchResult] = []

    if model.skip_reason:
        for tid in test_ids:
            results.append(BenchResult(
                model_id=model.model_id,
                model_name=model.model_name,
                provider=model.provider,
                pool=model.pool,
                role=model.role,
                in_use=model.in_use,
                test_id=tid,
                status="skipped",
                skip_reason=model.skip_reason,
            ))
        return results

    if model.compound_mode:
        await limiter.wait(model.rpm_pool, model.rpm)
        r = await call_compound(model)
        print(f"  [{model.pool}] {model.model_name} | compound_web_search → {r.status} | {r.total_ms}ms")
        results.append(r)
        return results

    # ── Filtrar tests según el rol del modelo ────────────────────────────────
    allowed = _get_suite(model.role)
    effective_ids = [t for t in test_ids if t in allowed]
    skipped_ids   = [t for t in test_ids if t not in allowed]
    for tid in skipped_ids:
        results.append(BenchResult(
            model_id=model.model_id, model_name=model.model_name,
            provider=model.provider, pool=model.pool, role=model.role,
            in_use=model.in_use, test_id=tid, status="skipped",
            skip_reason=f"role={model.role!r} no requiere este test",
        ))

    for tid in effective_ids:
        is_toon    = tid in TOON_TESTS or tid in TOON_TESTS_NOEX
        is_json    = tid in JSON_TESTS or tid in JSON_TESTS_NOEX
        is_native  = tid in NATIVE_TESTS
        is_planner = tid in PLANNER_TESTS
        is_tool    = is_toon or is_json or is_native or is_planner
        if is_tool:
            # compound-beta has no standard tool calling — skip tool tests
            if model.compound_mode:
                results.append(BenchResult(
                    model_id=model.model_id, model_name=model.model_name,
                    provider=model.provider, pool=model.pool, role=model.role,
                    in_use=model.in_use, test_id=tid, status="skipped",
                    skip_reason="compound-beta: no standard tool calling",
                ))
                continue
            messages_arg = None
        else:
            test = TESTS[tid]
            messages_arg = [{"role": "user", "content": test["prompt"]}]

        run_results: list[BenchResult] = []

        for run_i in range(runs):
            await limiter.wait(model.rpm_pool, model.rpm)
            t0_task = time.monotonic()
            try:
                if is_native:
                    r = await asyncio.wait_for(call_native_test(model, tid), timeout=TASK_TIMEOUT)
                elif is_planner:
                    r = await asyncio.wait_for(call_planner_test(model, tid), timeout=TASK_TIMEOUT)
                elif is_toon:
                    r = await asyncio.wait_for(call_toon_test(model, tid), timeout=TASK_TIMEOUT)
                elif is_json:
                    r = await asyncio.wait_for(call_json_test(model, tid), timeout=TASK_TIMEOUT)
                else:
                    r = await asyncio.wait_for(call_once(model, messages_arg), timeout=TASK_TIMEOUT)
                    r.test_id = tid
            except asyncio.TimeoutError:
                t_total = int((time.monotonic() - t0_task) * 1000)
                r = BenchResult(
                    model_id=model.model_id, model_name=model.model_name,
                    provider=model.provider, pool=model.pool, role=model.role,
                    in_use=model.in_use, test_id=tid,
                    status="timeout", total_ms=t_total,
                    error=f"asyncio task timeout after {TASK_TIMEOUT:.0f}s",
                )
                print(f"  [{model.pool}] {model.model_name} | {tid} → TASK TIMEOUT {t_total}ms ⚠", flush=True)
            run_results.append(r)
            if delay_ms > 0 and run_i < runs - 1:
                await asyncio.sleep(delay_ms / 1000)

        # Keep best run: for tool tests prefer correct_tool=True, then lowest total_ms
        if is_tool:
            correct = [r for r in run_results if r.correct_tool]
            best = min(correct, key=lambda r: r.total_ms) if correct else run_results[-1]
        else:
            ok_runs = [r for r in run_results if r.status in ("ok", "empty")]
            best = min(ok_runs, key=lambda r: r.total_ms) if ok_runs else run_results[-1]
        results.append(best)

    await _append_partial(results)
    return results


async def _check_ollama(base_url: str) -> bool:
    """Ping Ollama server. Returns True if reachable."""
    try:
        async with httpx.AsyncClient(timeout=3.0) as c:
            resp = await c.get(base_url.rstrip("/").replace("/v1", "") + "/api/tags")
            return resp.status_code == 200
    except Exception:
        return False


async def run_pool(
    pool_name: str,
    models: list[ModelDef],
    test_ids: list[str],
    limiter: RpmLimiter,
    runs: int,
    delay_ms: int,
) -> list[BenchResult]:
    """Run all models in a pool.

    Ollama pool (rpm=999, no shared API key): models run in parallel.
    All other pools: models run sequentially to respect shared rate limits.
    """
    print(f"\n{'─'*60}")
    print(f"  Pool: {pool_name.upper()} ({len(models)} models)")
    print(f"{'─'*60}")

    # Ollama ping
    if pool_name == "ollama":
        reachable = await _check_ollama(models[0].base_url)
        if not reachable:
            print(f"  [ollama] server not reachable at {models[0].base_url} — skipping pool")
            for m in models:
                m.skip_reason = f"ollama server not reachable at {m.base_url}"

        # Ollama Cloud has a concurrency limit — cap at 3 parallel models
        sem = asyncio.Semaphore(3)

        async def _run_with_sem(m: ModelDef) -> list[BenchResult]:
            async with sem:
                return await run_model_tests(m, test_ids, limiter, runs, delay_ms)

        nested = await asyncio.gather(*[_run_with_sem(m) for m in models])
        return [r for sub in nested for r in sub]

    all_results: list[BenchResult] = []
    for model in models:
        r = await run_model_tests(model, test_ids, limiter, runs, delay_ms)
        all_results.extend(r)

    return all_results


def _group_by_pool(models: list[ModelDef]) -> dict[str, list[ModelDef]]:
    groups: dict[str, list[ModelDef]] = {}
    for m in models:
        groups.setdefault(m.pool, []).append(m)
    return groups


# ── Console output ────────────────────────────────────────────────────────────
def _ms(v: Optional[int]) -> str:
    return f"{v}" if v is not None else "—"


def print_summary(results: list[BenchResult]) -> None:
    if not results:
        return

    print(f"\n{'═'*90}")
    print("  RESULTS BY POOL")
    print(f"{'═'*90}")

    by_pool: dict[str, list[BenchResult]] = {}
    for r in results:
        by_pool.setdefault(r.pool, []).append(r)

    for pool, pool_results in by_pool.items():
        print(f"\n  {pool.upper()}")
        header = f"  {'Model':<35} {'Test':<16} {'Status':<8} {'TTFT':>7} {'Total':>7} {'Tok/s':>6} {'Reasoning':>9}"
        print(header)
        print(f"  {'─'*87}")
        for r in pool_results:
            if r.status == "skipped":
                print(f"  {'  '+r.model_name:<35} {'—':<16} SKIP     {'—':>7} {'—':>7} {'—':>6} {'—':>9}  ({r.skip_reason[:40]})")
                continue
            indicator = "✓" if r.status == "ok" else ("⚠" if r.status in ("empty", "toon_native_call") else "✗")
            tok_s = f"{r.tok_per_s:.0f}" if r.tok_per_s else "—"
            print(
                f"  {indicator+' '+r.model_name:<35} {r.test_id:<16} {r.status:<8} "
                f"{_ms(r.ttft_ms):>7} {r.total_ms:>7} {tok_s:>6} "
                f"{_ms(r.reasoning_tokens):>9}"
            )
            if r.content_preview and r.status not in ("error", "timeout"):
                print(f"    └ {r.content_preview[:80]}")
            if r.error:
                print(f"    └ ERROR: {r.error[:80]}")

    # ── Latency ranking (ok runs only, no TOON) ──────────────────────────────
    ok_results = [r for r in results if r.status == "ok" and r.toon_valid is None]
    latency_by_model: dict[str, list[BenchResult]] = {}
    if ok_results:
        for r in ok_results:
            latency_by_model.setdefault(r.model_name, []).append(r)

        ranked = sorted(
            [
                (name, sum(r.total_ms for r in rs) // len(rs), rs[0].provider)
                for name, rs in latency_by_model.items()
            ],
            key=lambda x: x[1],
        )

        print(f"\n{'═'*60}")
        print("  RANKING LATENCIA — avg total_ms (tests ok, sin TOON)")
        print(f"{'═'*60}")
        for i, (name, avg_ms, provider) in enumerate(ranked, 1):
            bar = "█" * min(int(avg_ms / 200), 30)
            print(f"  {i:>2}. {avg_ms:>6}ms  {bar:<30}  {name} ({provider})")

    # ── TOON summary — full vs noex ───────────────────────────────────────────
    toon_results = [r for r in results if r.toon_valid is not None]
    if toon_results:
        # Separate full and noex results
        toon_full_res  = [r for r in toon_results if not r.test_id.endswith("_noex")]
        toon_noex_res  = [r for r in toon_results if r.test_id.endswith("_noex")]

        def _toon_scores(res_list: list[BenchResult]) -> dict[str, tuple[int, int, int, float]]:
            """Returns {model_name: (n, valid, tool_ok, score)}"""
            by: dict[str, list[BenchResult]] = {}
            for r in res_list:
                if r.status != "skipped":
                    by.setdefault(r.model_name, []).append(r)
            out = {}
            for name, rs in by.items():
                n = len(rs)
                valid = sum(1 for r in rs if r.toon_valid)
                tool_ok = sum(1 for r in rs if r.correct_tool)
                args_ok = sum(1 for r in rs if r.correct_args)
                out[name] = (n, valid, tool_ok, args_ok, tool_ok / n if n else 0.0)
            return out

        full_scores = _toon_scores(toon_full_res)
        noex_scores = _toon_scores(toon_noex_res)
        all_names   = sorted(set(full_scores) | set(noex_scores))

        print(f"\n{'═'*95}")
        print("  TOON TOOL CALLING — full (con ejemplos) vs noex (sin ejemplos de formato)")
        print(f"{'═'*95}")
        print(f"  {'Model':<35} {'Full N':>6} {'Full%':>6}  {'Noex N':>6} {'Noex%':>6}  {'Delta':>6}")
        print(f"  {'─'*90}")
        for name in all_names:
            f_n, _, f_tool, _, f_score = full_scores.get(name, (0, 0, 0, 0, 0.0))
            x_n, _, x_tool, _, x_score = noex_scores.get(name, (0, 0, 0, 0, 0.0))
            delta = x_score - f_score
            delta_str = f"{delta*100:+.0f}%" if f_n and x_n else "—"
            f_pct = f"{f_score*100:.0f}%" if f_n else "—"
            x_pct = f"{x_score*100:.0f}%" if x_n else "—"
            print(
                f"  {name:<35} {f_n:>6} {f_pct:>6}  {x_n:>6} {x_pct:>6}  {delta_str:>6}"
            )

        # TOON failures detail
        failures = [r for r in toon_results if r.status not in ("skipped",) and not r.correct_tool]
        if failures:
            print("\n  TOON failures:")
            for r in failures[:20]:
                variant = " [noex]" if r.test_id.endswith("_noex") else ""
                print(f"    ✗ {r.model_name}{variant} | {r.test_id} | {r.toon_raw[:60] or r.content_preview[:60]}")

    # ── Ranking global — latencia + TOON full + TOON noex ────────────────────
    # Score = (1 - latency_norm)*0.30 + toon_full*0.35 + toon_noex*0.35
    # Solo modelos con datos de latencia Y al menos un grupo TOON.
    if ok_results and toon_results:
        lat_avgs = {
            name: sum(r.total_ms for r in rs) // len(rs)
            for name, rs in latency_by_model.items()
        }
        max_lat = max(lat_avgs.values()) if lat_avgs else 1

        full_sc  = _toon_scores(toon_full_res)  # type: ignore[possibly-undefined]
        noex_sc  = _toon_scores(toon_noex_res)  # type: ignore[possibly-undefined]
        all_model_names = set(lat_avgs) & (set(full_sc) | set(noex_sc))

        global_ranked = []
        for name in all_model_names:
            lat = lat_avgs.get(name, max_lat)
            lat_norm = 1.0 - lat / max_lat
            f_score = full_sc.get(name, (0, 0, 0, 0, 0.0))[4]
            x_score = noex_sc.get(name, (0, 0, 0, 0, 0.0))[4]
            # If only one TOON group ran, weight accordingly
            if name in full_sc and name in noex_sc:
                global_score = lat_norm * 0.30 + f_score * 0.35 + x_score * 0.35
            elif name in full_sc:
                global_score = lat_norm * 0.30 + f_score * 0.70
            else:
                global_score = lat_norm * 0.30 + x_score * 0.70
            global_ranked.append((name, lat, f_score, x_score, global_score))

        global_ranked.sort(key=lambda x: -x[4])

        print(f"\n{'═'*90}")
        print("  RANKING GLOBAL  (latencia 30% · TOON-full 35% · TOON-noex 35%)")
        print(f"{'═'*90}")
        print(f"  {'#':>3}  {'Model':<35} {'Lat avg':>8} {'TOON%':>7} {'noex%':>7} {'Score':>7}")
        print(f"  {'─'*85}")
        for i, (name, lat, f_s, x_s, g_s) in enumerate(global_ranked, 1):
            bar = "█" * int(g_s * 20)
            f_pct = f"{f_s*100:.0f}%" if f_s > 0 or name in full_sc else "—"  # type: ignore[possibly-undefined]
            x_pct = f"{x_s*100:.0f}%" if x_s > 0 or name in noex_sc else "—"  # type: ignore[possibly-undefined]
            print(
                f"  {i:>3}. {name:<35} {lat:>7}ms {f_pct:>7} {x_pct:>7} {g_s*100:>6.1f}%  {bar}"
            )


# ── JSON output ───────────────────────────────────────────────────────────────
def save_json(results: list[BenchResult], extra: dict) -> Path:
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_path = Path(__file__).parent / f"benchmark-schoolai-{ts}.json"
    payload = {
        "timestamp": datetime.now().isoformat(),
        "meta": extra,
        "results": [asdict(r) for r in results],
    }
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    return out_path


# ── CLI ───────────────────────────────────────────────────────────────────────
_ALL_TEST_IDS = (
    list(TESTS.keys())
    + list(JSON_TESTS.keys())
    + list(JSON_TESTS_NOEX.keys())
    + list(TOON_TESTS.keys())        # TOON text format
    + list(TOON_TESTS_NOEX.keys())
    + list(NATIVE_TESTS.keys())      # native OpenAI function calling (_nat)
    + list(PLANNER_TESTS.keys())     # planner JSON plan [{tool,params}] (_pln)
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="SchoolAI LLM Benchmark — Phase 1+2")
    parser.add_argument(
        "--models",
        default="",
        help="Comma-separated pool names to include (default: all). E.g. google,groq,deepseek",
    )
    parser.add_argument(
        "--tests",
        default=",".join(_ALL_TEST_IDS),
        help=(
            f"Comma-separated test IDs (default: all). "
            f"Latency: {', '.join(TESTS.keys())}. "
            f"TOON full: {', '.join(TOON_TESTS.keys())}. "
            f"TOON noex (sin ejemplos): {', '.join(TOON_TESTS_NOEX.keys())}."
        ),
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=1,
        help="Runs per model per test (default: 1). Best result kept.",
    )
    parser.add_argument(
        "--delay",
        type=int,
        default=0,
        help="Extra delay in ms between runs of the same model (default: 0)",
    )
    parser.add_argument(
        "--no-json",
        action="store_true",
        help="Skip JSON output",
    )
    parser.add_argument(
        "--inuse",
        action="store_true",
        help="Solo modelos marcados in_use=True",
    )
    return parser.parse_args()


# ── Entry point ───────────────────────────────────────────────────────────────
async def main() -> None:
    args = parse_args()

    pool_filter = {p.strip() for p in args.models.split(",") if p.strip()} if args.models else set()
    test_ids = [t.strip() for t in args.tests.split(",") if t.strip() in _ALL_TEST_IDS]
    if not test_ids:
        print(f"No valid test IDs. Available: {', '.join(_ALL_TEST_IDS)}")
        sys.exit(1)

    latency_ids = [t for t in test_ids if t in TESTS]
    toon_ids    = [t for t in test_ids if t in TOON_TESTS]
    native_ids  = [t for t in test_ids if t in NATIVE_TESTS]

    all_models = _build_models()
    if pool_filter:
        all_models = [m for m in all_models if m.pool in pool_filter]
    if args.inuse:
        all_models = [m for m in all_models if m.in_use]

    print(f"\n{'═'*70}")
    print("  SchoolAI LLM Benchmark — Phase 1+2")
    if latency_ids:
        print(f"  Latency: {', '.join(latency_ids)}")
    if toon_ids:
        print(f"  TOON   : {', '.join(toon_ids)}")
    if native_ids:
        print(f"  Native : {', '.join(native_ids)}")
    print(f"  Runs  : {args.runs}")
    print(f"  Models: {len(all_models)} across {len(_group_by_pool(all_models))} pools")
    print(f"{'═'*70}")

    groups = _group_by_pool(all_models)
    limiter = RpmLimiter()

    # ── Init global incremental-save state ───────────────────────────────────
    global _g_lock, _g_partial_path, _g_done_count, _g_total_expected
    _g_lock = asyncio.Lock()
    _g_done_count = 0
    _g_results.clear()
    _g_partial_path = Path(__file__).parent / f"benchmark-partial-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    _g_total_expected = sum(
        len([t for t in test_ids if t in _get_suite(m.role)])
        for m in all_models if not m.skip_reason and not m.compound_mode
    )

    # ── SIGINT handler: save partial results on Ctrl+C ───────────────────────
    loop = asyncio.get_running_loop()
    def _on_sigint() -> None:
        print(f"\n\n⚠  Ctrl+C — guardando {len(_g_results)} resultados parciales…", flush=True)
        if _g_results and not args.no_json:
            out = save_json(_g_results, {"partial": True, "tests": test_ids,
                                         "runs": args.runs, "pools": list(groups.keys())})
            print(f"  Parcial → {out.name}", flush=True)
        loop.stop()
    try:
        loop.add_signal_handler(signal.SIGINT, _on_sigint)
    except NotImplementedError:
        pass  # Windows

    # ── Status ticker (progreso cada 30 s) ───────────────────────────────────
    ticker = asyncio.create_task(_status_ticker(30))

    # ── Pool watchdog: cancela pools que superen POOL_TIMEOUT ────────────────
    async def _run_pool_guarded(pool_name: str, models: list[ModelDef]) -> list[BenchResult]:
        try:
            return await asyncio.wait_for(
                run_pool(pool_name, models, test_ids, limiter, args.runs, args.delay),
                timeout=POOL_TIMEOUT,
            )
        except asyncio.TimeoutError:
            print(f"\n  ⚠ Pool {pool_name.upper()} timeout ({POOL_TIMEOUT:.0f}s) — "
                  f"resultados parciales ya guardados en {_g_partial_path.name}", flush=True)
            return []

    # ── Run all pools in parallel ─────────────────────────────────────────────
    await asyncio.gather(*[_run_pool_guarded(pn, ms) for pn, ms in groups.items()])

    ticker.cancel()
    try:
        await ticker
    except asyncio.CancelledError:
        pass

    # _g_results has ALL completed results (including partial pools via _append_partial)
    all_results: list[BenchResult] = list(_g_results)

    print_summary(all_results)

    if not args.no_json:
        out_path = save_json(all_results, {
            "tests": test_ids,
            "runs": args.runs,
            "delay_ms": args.delay,
            "pools": list(groups.keys()),
        })
        print(f"\n  JSON saved → {out_path.name}")
        if _g_partial_path and _g_partial_path.exists():
            _g_partial_path.unlink()
            print("  Partial file removed")


if __name__ == "__main__":
    asyncio.run(main())
