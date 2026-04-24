# LLM Benchmark — 2026-04-19

**Script:** `scripts/benchmark_llm.py` Phase 1+2+JSON  
**Runs:** 1 por test  
**Fecha:** 2026-04-19  

---

## Modelos probados

### API directa (pools: google, groq, deepseek, mistral, openrouter, zai, nvidia)

| Modelo | Provider | Model ID | Rol actual |
|--------|----------|----------|-----------|
| Gemini 2.5 Flash Lite | Google | `gemini-2.5-flash-lite` | extractor+router |
| Gemini 3.1 Flash Lite Preview | Google | `gemini-3.1-flash-lite-preview` | candidato |
| Gemma 4 26B | Google | `gemma-4-26b-a4b-it` | candidato |
| Gemma 4 31B | Google | `gemma-4-31b-it` | candidato |
| Gemma 3 27B | Google | `gemma-3-27b-it` | candidato |
| Gemma 3 12B | Google | `gemma-3-12b-it` | candidato |
| GPT-OSS 20B | Groq | `openai/gpt-oss-20b` | fallback |
| GPT-OSS 120B | Groq | `openai/gpt-oss-120b` | candidato |
| Llama 4 Scout 17B | Groq | `meta-llama/llama-4-scout-17b-16e-instruct` | candidato |
| Qwen3 32B | Groq | `qwen/qwen3-32b` | candidato |
| Compound Beta | Groq | `compound-beta` | chat (web agent) |
| DeepSeek V3.2 Chat | DeepSeek | `deepseek-chat` | fallback |
| DeepSeek V3.2 Reasoner | DeepSeek | `deepseek-reasoner` | orchestrator |
| Mistral Small | Mistral | `mistral-small-latest` | chat_fallback |
| Mistral Large | Mistral | `mistral-large-latest` | fallback |
| Mistral Medium | Mistral | `mistral-medium-latest` | candidato |
| Nemotron Nano 12B VL | OpenRouter | `nvidia/nemotron-nano-12b-v2-vl:free` | vision |
| Gemma 4 31B (OpenRouter) | OpenRouter | `google/gemma-4-31b-it:free` | vision_fallback |
| Arcee Trinity Large | OpenRouter | `arcee-ai/trinity-large-preview:free` | candidato (nuevo) |
| Stepfun Step-3.5 Flash | OpenRouter | `stepfun/step-3.5-flash` | candidato (nuevo) |
| ByteDance Seed 2.0 Lite | OpenRouter | `bytedance-seed/seed-2.0-lite` | candidato (nuevo) |
| GLM-4V Flash | Z.AI | `glm-4v-flash` | candidato |
| Llama 3.3 70B | NVIDIA NIM | `meta/llama-3.3-70b-instruct` | candidato |

### Ollama Cloud (pool: ollama)

| Modelo | Modos probados |
|--------|---------------|
| Kimi K2.5 | cloud |
| GPT-OSS 20B | cloud |
| GPT-OSS 120B | [medium], [off] |
| Gemma 4 31B | [low], [medium], [off] |
| MiniMax M2.7 | cloud, [off] |
| Nemotron 3 Super 120B | cloud |
| Gemini 3 Flash Preview | cloud |
| GLM 5.1 | [medium], [low] — todos 403 |

---

## Resultados TOON (run bpy3m6z3c — 2026-04-19)

### Latencia avg por modelo (tests ok, sin TOON)

| # | Modelo | Provider | Lat avg |
|---|--------|----------|---------|
| 1 | GPT-OSS 20B | Groq | 406ms |
| 2 | GPT-OSS 120B | Groq | 457ms |
| 3 | Llama 4 Scout 17B | Groq | 822ms |
| 4 | Mistral Small | Mistral | 1056ms |
| 5 | Qwen3 32B | Groq | 1092ms |
| 6 | Gemini 2.5 Flash Lite | Google | 1323ms |
| 7 | Mistral Medium | Mistral | 1379ms |
| 8 | Llama 3.3 70B | NVIDIA NIM | 1486ms |
| 9 | GLM-4V Flash | Z.AI | 1722ms |
| 10 | Gemma 3 27B | Google | 2707ms |
| 11 | DeepSeek V3.2 Chat | DeepSeek | 3069ms |
| 12 | Gemma 4 26B | Google | 4092ms |
| 13 | Gemma 4 31B | Google | 4935ms |
| 14 | DeepSeek V3.2 Reasoner | DeepSeek | 6343ms |
| 15 | Gemini 3.1 Flash Lite | Google | 6760ms¹ |
| 16 | Compound Beta | Groq | 7236ms |
| 17 | Nemotron Nano 12B VL | OpenRouter | 7413ms |
| — | Gemma 3 12B | Google | 31588ms² |

> ¹ Outlier: cold start 19s en `no_tool` inflando avg. Latencia real ~1-2s.  
> ² Gemma 3 12B: simple/format ok pero TOON todos 400 error. Latencia muy alta.

### TOON tool calling — Full% vs Noex%

| Modelo | Full (10 tests) | Noex (10 tests) | Delta |
|--------|----------------|-----------------|-------|
| **Gemma 4 26B** | **100%** | **90%** | -10% |
| Mistral Small | 100% | 40% | -60% |
| Gemini 2.5 Flash | 100% | 33% | -67% |
| Mistral Large | 100%³ | 33%³ | — |
| GPT-OSS 120B | 100% | 10% | -90% |
| Llama 4 Scout 17B | 100% | 10% | -90% |
| Qwen3 32B | 100%⁴ | 10% | -90% |
| Gemma 4 31B | 100% | 20% | -80% |
| Mistral Medium | 100% | 10% | -90% |
| Llama 3.3 70B NVIDIA | 100% | 10% | -90% |
| GLM-4V Flash | 100% | 10% | -90% |
| DeepSeek V3.2 Chat | 100% | 10% | -90% |
| Gemini 2.5 Flash Lite | 100% | 0% | -100% |
| DeepSeek V3.2 Reasoner | 100% | 10% | -90% |
| Gemini 3.1 Flash Lite | 100% | 10% | -90% |
| Nemotron Nano 12B VL | 33% | 17% | — |
| GPT-OSS 20B | 20% | 10% | — |
| Gemma 3 27B/12B | **0%** | 0% | ❌ 400 errors |

> ³ Mistral Large: rate limited (429) — datos parciales (1/10 full, 3/10 noex probados).  
> ⁴ Qwen3 32B: 9/10 full (1 test 429 rate limit).

### Ranking global TOON (lat 30% · full 35% · noex 35%)

| # | Modelo | Lat avg | TOON Full | TOON Noex | Score |
|---|--------|---------|-----------|-----------|-------|
| 1 | Gemma 4 26B | 4092ms | 100% | 90% | **92.6%** |
| 2 | Mistral Small | 1056ms | 100% | 40% | 78.0% |
| 3 | Gemini 2.5 Flash | 1848ms | 100% | 33% | 74.9% |
| 4 | GPT-OSS 120B | 457ms | 100% | 10% | 68.1% |
| 5 | Llama 4 Scout 17B | 822ms | 100% | 10% | 67.7% |
| 6 | Qwen3 32B | 1092ms | 100% | 10% | 67.5% |
| 7 | Gemma 4 31B | 4935ms | 100% | 20% | 67.3% |
| 8 | Mistral Medium | 1379ms | 100% | 10% | 67.2% |
| 9 | Llama 3.3 70B NVIDIA | 1486ms | 100% | 10% | 67.1% |
| 10 | GLM-4V Flash | 1722ms | 100% | 10% | 66.9% |
| 11 | DeepSeek V3.2 Chat | 3069ms | 100% | 10% | 65.6% |
| 12 | Gemini 2.5 Flash Lite | 1323ms | 100% | 0% | 63.7% |
| 13 | DeepSeek V3.2 Reasoner | 6343ms | 100% | 10% | 62.5% |
| 14 | Gemini 3.1 Flash Lite | 6760ms¹ | 100% | 10% | 62.1% |
| — | Nemotron Nano 12B VL | 7413ms | 33% | 17% | 40.5% |

---

## Resultados Ollama Cloud (run brfvx22tc — 2026-04-19)

### Ranking global Ollama (lat 30% · full 35% · noex 35%)

| # | Modelo | Lat avg | TOON Full | TOON Noex | Score |
|---|--------|---------|-----------|-----------|-------|
| 1 | GPT-OSS 20B (cloud) | 4608ms | 100% | **100%** | **96.5%** |
| 2 | Gemini 3 Flash Preview (cloud) | 5076ms | 100% | 88% | 91.8% |
| 3 | Gemma 4 31B [off] | 4009ms | 100% | 20% | 68.9% |
| 4 | MiniMax M2.7 [off] | 6134ms | 100% | 20% | 67.3% |
| 5 | Nemotron 3 Super 120B (cloud) | 1903ms | 100% | 10% | 67.1% |
| 6 | Kimi K2.5 (cloud) | 4724ms | 100% | 10% | 64.9% |
| 7 | GPT-OSS 120B [medium] | 4762ms | 100% | 10% | 64.9% |
| 8 | MiniMax M2.7 (cloud) | 4888ms | 100% | 10% | 64.8% |
| 9 | GPT-OSS 120B [off] | 21772ms | 100% | 10% | 51.9% |
| 10 | Gemma 4 31B [low] | 35653ms | 100% | 20% | 44.9% |
| — | GLM 5.1 | — | 0% | 0% | ❌ 403 (capacidad) |

---

## Resultados JSON (run bphpv4q6e — 2026-04-19, parser fix)

**Hallazgo principal: JSON noex es dramáticamente superior a TOON noex.**

La mayoría de modelos que tenían 10% TOON noex alcanzaron **100% JSON noex**.

### JSON tool calling — Full% vs Noex%

| Modelo | JSON Full | JSON Noex | TOON noex (ref) | Delta noex |
|--------|-----------|-----------|-----------------|------------|
| Gemini 3.1 Flash Lite | 100% | **100%** | 10% | +90pp |
| DeepSeek V3.2 Chat | 100% | **100%** | 10% | +90pp |
| DeepSeek V3.2 Reasoner | 100% | **100%** | 10% | +90pp |
| Qwen3 32B | 100% | **100%** | 10% | +90pp |
| Mistral Medium | 100% | **100%** | 10% | +90pp |
| GPT-OSS 120B | 100% | **100%** | 10% | +90pp |
| Gemma 4 26B | 100% | **100%** | 90% | +10pp |
| Gemma 4 31B | 100% | **100%** | 20% | +80pp |
| ByteDance Seed 2.0 Lite | 100% | **100%** | — (nuevo) | ✨ |
| Mistral Large⁵ | 100% | **100%** | 33% | +67pp |
| Mistral Small | 100% | 80% | 40% | +40pp |
| Llama 3.3 70B NVIDIA | 100% | 67% | 10% | +57pp |
| Llama 4 Scout 17B | 90%⁶ | 60% | 10% | +50pp |
| Stepfun Step-3.5 Flash | 100% | 40% | — (nuevo) | — |
| GLM-4V Flash | 100% | 20% | 10% | +10pp |
| Gemma 3 27B/12B | ❌ | ❌ | ❌ | 400 error (sys prompt OpenAI-compat) |
| GPT-OSS 20B | ⚠️ | ⚠️ | 10% | native tool calling interno |

> ⁵ Mistral Large: datos parciales (4/10 full, 3/10 noex) por rate limit compartido con Small+Medium.  
> ⁶ Llama 4 Scout: `att_query_json` devolvió mark_attendance en vez de query_attendance (confusión semántica).

### Latencia nuevos modelos (simple + format, run bvldm7yrp)

| Modelo | Lat avg | JSON Full | JSON Noex |
|--------|---------|-----------|-----------|
| Stepfun Step-3.5 Flash | 2263ms | 100% | 40% |
| ByteDance Seed 2.0 Lite | 5297ms | 100% | **100%** |
| Arcee Trinity Large | — | — | — |

> Arcee Trinity no pudo testar — RPD diario agotado en OpenRouter free tier durante el run.

---

## Errores / modelos descartados

| Modelo | Error | Causa | Acción |
|--------|-------|-------|--------|
| Gemma 3 27B | 400 en todos los TOON/JSON tests | OpenAI-compat endpoint rechaza `system` prompt complejo | Usar native Gemini API (`google.generativeai`) |
| Gemma 3 12B | 400 igual que 27B | Mismo root cause | Igual |
| GLM 5.1 [medium/low] | 403 en todos | Capacidad saturada en Ollama Cloud | Reintentar en otro horario |
| Gemini 2.5 Flash | Removido del script | RPD 20/día ya consumido (2026-04-19) | — |
| Arcee Trinity | 429 free-models-per-day | Cuota diaria agotada | Reintentar mañana |
| Gemma 4 31B (OpenRouter free) | 429 desde test 2 | Cuota agotada inmediatamente | Misma cuota que Nemotron |

---

## Nota sobre DeepSeek

A 2026-04-19, ambos modelos DeepSeek son **V3.2** (no R1):
- `deepseek-chat` = V3.2 sin thinking
- `deepseek-reasoner` = V3.2 con thinking habilitado

---

## Google AI Studio — Rate limits verificados

| Modelo | RPM | TPM | RPD | Estado |
|--------|-----|-----|-----|--------|
| Gemini 2.5 Flash Lite | 10 | 250K | ~20 | Consumido (run agotó RPD) |
| Gemini 3.1 Flash Lite Preview | 15 | 250K | 500 | OK |
| Gemma 4 26B | 15 | ilimitado | 1500 | OK |
| Gemma 4 31B | 15 | ilimitado | 1500 | OK |
| Gemma 3 27B | 30 | 15K | 14400 | OK (pero TOON incompatible) |
| Gemma 3 12B | 30 | 15K | 14400 | OK (pero TOON incompatible) |
| Gemini 2.5 Flash | 5 | 250K | 20 | Eliminado — RPD muy bajo |
