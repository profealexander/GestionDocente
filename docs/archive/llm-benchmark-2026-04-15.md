# Benchmark LLM SchoolAI — 2026-04-15

Script: `scripts/benchmark_llm.py` (Phase 1+2+noex)  
Tests: `simple`, `format` (latencia) + `att_absent`, `att_query`, `att_query_long`, `no_tool`, `tool_choice` (TOON full) + versiones `_noex` (sin ejemplo de formato)  
Modo: pools en paralelo, secuencial dentro de cada pool (ollama: semáforo 3 concurrentes)  
Runs: 1 por test

---

## Stack activo al momento del benchmark

```env
LLM_EXTRACTOR=google/gemini-2.5-flash-lite
LLM_ROUTER=google/gemini-2.5-flash-lite
LLM_CHAT=groq/compound-beta
LLM_CHAT_FALLBACK=mistral/mistral-small-latest
LLM_ORCHESTRATOR=deepseek/deepseek-reasoner
LLM_ORCHESTRATOR_FALLBACK=deepseek/deepseek-chat,google/gemini-2.5-flash-lite,groq/openai/gpt-oss-20b,mistral/mistral-large-latest
LLM_VISION=openrouter/nvidia/nemotron-nano-12b-v2-vl:free
LLM_VISION_FALLBACK=openrouter/google/gemma-4-31b-it:free
```

---

## Ranking latencia (avg total_ms, tests simple+format)

| # | Modelo | Provider | avg ms | Rol actual |
|---|--------|----------|-------:|--------:|
| 1 | **GPT-OSS 20B** | Groq | **385ms** | orchestrator fallback |
| 2 | **Llama 4 Scout 17B** | Groq | **500ms** | candidate |
| 3 | Gemini 2.5 Flash Lite ← **en uso** | Google | 828ms | extractor/router |
| 4 | Mistral Small ← **en uso** | Mistral | 882ms | chat fallback |
| 5 | GPT-OSS 120B | Groq | 1017ms | candidate |
| 6 | Gemini 2.5 Flash | Google | 1145ms | candidate |
| 7 | Mistral Medium | Mistral | 1184ms | candidate |
| 8 | Gemini 3.1 Flash Lite Preview | Google | 1451ms | candidate |
| 9 | Mistral Large ← **en uso** | Mistral | 1669ms | fallback |
| 10 | DeepSeek V3.2 ← **en uso** | DeepSeek | 1899ms | orchestrator fallback |
| 11 | Gemini 3 Flash Preview | Ollama Cloud | 1902ms | candidate |
| 12 | Gemma 4 31B [medium] | Ollama Cloud | 511ms† | candidate |
| — | DeepSeek R1 ← **en uso** | DeepSeek | 5211ms | orchestrator |
| — | Compound Beta ← **en uso** | Groq | 6337ms | chat (web) |

†Ollama Cloud: latencia local, no reproducible en producción API.

---

## TOON Tool Calling — full vs noex (10 tests: att_absent, att_query, att_query_long, no_tool, tool_choice × 2)

> **noex** = mismo YAML de tool definitions, sin el bloque de ejemplo de formato TOON.  
> Objetivo: medir si los modelos infieren el formato sin ejemplos (ahorro ~60-80 tokens/llamada).

| Modelo | Provider | Full% | noex% | Delta | Nota |
|--------|----------|------:|------:|------:|------|
| **Gemma 4 26B** | Google | 100% | **100%** | 0% | Usa JSON — parseado por fallback decoder |
| **Mistral Small** | Mistral | 100% | **40%** | -60% | Mejor noex del grupo cloud API |
| **Mistral Medium** | Mistral | 100% | **40%** | -60% | Ídem |
| **Gemma 4 31B** | Google | 100% | 40% | -60% | |
| **MiniMax M2.7 [off]** | Ollama Cloud | 100% | 40% | -60% | |
| **Gemini 3 Flash Preview** | Ollama Cloud | 100% | 67%† | -33% | Mejor noex absoluto (cloud) |
| Gemini 2.5 Flash | Google | 100% | 33% | -67% | 2 vacíos en noex |
| Gemini 2.5 Flash Lite | Google | 100% | 20% | -80% | Falla con `tool_code` Python-style |
| Gemini 3.1 Flash Lite Preview | Google | 100% | 20% | -80% | JSON format en noex |
| GPT-OSS 120B | Groq | 100% | 20% | -80% | JSON con prefijo `TOON{` |
| DeepSeek V3.2 | DeepSeek | 100% | 20% | -80% | |
| DeepSeek R1 | DeepSeek | 100% | 20% | -80% | |
| Llama 4 Scout 17B | Groq | 100% | 20% | -80% | JSON puro en noex |
| Qwen3 32B | Groq | 100% | 20% | -80% | |
| Kimi K2.5 | Ollama Cloud | 100% | 20% | -80% | Trunca `8egb→8eg` |
| Gemma 4 31B (Ollama Cloud) | Ollama Cloud | 100% | 20% | -80% | |
| **GPT-OSS 20B** | Groq | 20% | 20% | 0% | ⚠️ Native tool calling — incompatible con TOON |
| Mistral Large | Mistral | 100% | — | — | 429 rate limit (datos incompletos) |

†Gemini 3 Flash Preview noex: 4/6 tests ok (2 devolvieron `empty`).

### Veredicto noex

**El ejemplo de formato es imprescindible.** Sin él, todos los modelos saben QUÉ tool llamar pero inventan el formato (JSON, Python, `<tool_call>`, funciones). La excepción es Gemma 4 26B que produce JSON parseable por el fallback decoder del script — abre la puerta a un formato alternativo JSON en producción, pero requeriría cambio de protocolo.

---

## Ranking Global — latencia 30% · TOON-full 35% · TOON-noex 35%

> Solo modelos con datos completos de latencia y TOON.

| # | Modelo | Provider | Lat avg | TOON% | noex% | Score |
|---|--------|----------|---------|------:|------:|------:|
| 1 | **Mistral Small** | Mistral | 882ms | 100% | 40% | **74.8%** |
| 2 | Mistral Medium | Mistral | 1184ms | 100% | 40% | 73.4% |
| 3 | Gemini 2.5 Flash | Google | 1145ms | 100% | 33% | 71.2% |
| 4 | Gemma 4 31B [medium] | Ollama Cloud | 511ms | 100% | 20% | 71.3% |
| 5 | Gemma 4 31B [low] | Ollama Cloud | 1398ms | 100% | 20% | 70.1% |
| 6 | Llama 4 Scout 17B | Groq | 500ms | 100% | 20% | 69.6% |
| 7 | Gemini 2.5 Flash Lite | Google | 828ms | 100% | 20% | 68.1% |
| 8 | GPT-OSS 120B | Groq | 1017ms | 100% | 20% | 67.2% |
| 9 | Gemini 3.1 Flash Lite Preview | Google | 1451ms | 100% | 20% | 65.1% |
| 10 | Gemini 3 Flash Preview | Ollama Cloud | 1902ms | 100% | 67% | **85.7%**† |
| 11 | DeepSeek V3.2 | DeepSeek | 1899ms | 100% | 20% | 63.0% |
| 12 | DeepSeek R1 | DeepSeek | 5211ms | 100% | 20% | 47.3% |

†Gemini 3 Flash Preview score alto pero Ollama Cloud — no disponible como API directa.

---

## att_query_long — truncación de course codes

Test específico para detectar bugs de truncación en nombres de cursos (`8egb→8eg`).

| Modelo | `8egb` ok | `prep` ok | `1bt` ok | Estado |
|--------|:---------:|:---------:|:--------:|--------|
| Gemini 2.5 Flash Lite | ✓ | ✓ | ✓ | ✅ ok |
| Gemini 2.5 Flash | ✓ | ✓\* | ✓\* | ✅ ok |
| Gemini 3.1 Flash Lite Preview | ✓ | ✓ | ✓ | ✅ ok |
| Mistral Small/Medium | ✓ | ✓ | ✓ | ✅ ok |
| GPT-OSS 120B | ✓ | ✓ | ✓ | ✅ ok |
| DeepSeek V3.2 | ✓ | ✓ | ✓ | ✅ ok |
| **Kimi K2.5** | ✗ `8eg` | ✗ | ✗ | ❌ trunca consistentemente |
| **Gemini 3 Flash Preview** | ✗ `8eg` | ✗ | ✗ | ❌ trunca (`8egb→8eg`) |

\*Solo visible en preview truncado por el script.

---

## Problemas detectados y estado

| Modelo / Fix | Error | Causa | Estado |
|---|---|---|---|
| **GPT-OSS 20B (TOON)** | `toon_native_call` | Groq activa native tool calling al ver YAML en system prompt | ✅ Conocido — no usar para extracción TOON |
| **Qwen3 32B simple/format** | 400 `enable_thinking unsupported` | Groq eliminó soporte a `enable_thinking` (2026-04-15) | ✅ **Fixed**: `reasoning_style=""` en catálogo |
| **Gemma 4 26B/31B simple/format** | 400 `Invalid JSON payload` | `thinking_config` rechazado por Google OpenAI-compat para Gemma IT | ✅ **Fixed**: `thinking_budget=0, reasoning_style=""` en catálogo |
| **Mistral Large** | 429 rate limit | Pool compartido Small+Medium+Large a 20 RPM — demasiado rápido | ✅ **Fixed**: todos a 12 RPM |
| **Kimi K2.5** | Trunca `8egb→8eg` | Bug del modelo — sistemático | ⚠️ Conocido — no usar como extractor producción |
| **Gemini 3 Flash Preview** | Trunca `8egb→8eg` | Ídem | ⚠️ Conocido |
| **GLM 5.1** | 403 `model experiencing high volume` | Servidor Ollama Cloud saturado | ⏳ Pendiente retest de madrugada |
| **Llama 3.3 70B** / **Llama 3.1 8B** | 404 | Retirados de API Groq | 🔧 Actualizar IDs |

---

## Observaciones clave

### noex confirma: ejemplo de formato imprescindible en producción
Todos los modelos conocen la semántica de los tools pero inventan el formato de serialización sin el ejemplo. Gemma 4 26B es la excepción (JSON parseable), pero requeriría cambio de protocolo TOON→JSON. **No cambiar el prompt de producción.**

### Candidatos a reemplazar Gemini 2.5 Flash Lite (deprecación 17 jun 2026)
Ordenados por balance velocidad/TOON:
1. **Gemini 3.1 Flash Lite Preview** — 1451ms, 100% TOON, misma familia Google, probablemente mismo endpoint. **Candidato principal.**
2. **Mistral Small** — 882ms, 100% TOON, 40% noex (el mejor noex API cloud). Requiere cambiar provider.
3. **Llama 4 Scout 17B** (Groq) — 500ms, 100% TOON, muy rápido. noex 20%.

### GPT-OSS 120B vs 20B para fallback
120B tiene 100% TOON full en Groq mientras 20B es 0% (native tool calling). Para la cadena de fallback del extractor, **20B debe reemplazarse por 120B**.

### Gemma 4 26B — único con noex 100%
Produce JSON `{"name":..., "arguments":...}` que el decoder acepta vía fallback. Latencia ~4-9s (no viable para extractor). Pero si el protocolo de producción migra a JSON, sería un candidato.

### DeepSeek R1 — overhead de reasoning en TOON
599-894 reasoning tokens por test TOON. Sigue siendo correcto como orchestrator (razona antes de decidir), pero confirma que **no debe usarse como extractor**.

---

## Cambios de configuración recomendados

```env
# URGENTE antes del 17 jun 2026 — migrar extractor desde gemini-2.5-flash-lite:
LLM_EXTRACTOR=google/gemini-3.1-flash-lite-preview   # candidato principal
LLM_ROUTER=google/gemini-3.1-flash-lite-preview

# Fallback chain — reemplazar GPT-OSS 20B por 120B para TOON:
# LLM_ORCHESTRATOR_FALLBACK=...,groq/openai/gpt-oss-120b   # 120B: 100% TOON vs 0% del 20B

# Chat fallback — Mistral Small sigue siendo sólido (882ms, 100% TOON, 40% noex)
# No cambiar.
```

---

## Comparación con benchmark 2026-04-13

| Métrica | Anterior | Actual | Delta |
|---------|----------|--------|-------|
| Gemini 2.5 Flash Lite latencia | 1292ms | 828ms | -464ms |
| Mistral Small latencia | 784ms | 882ms | +98ms |
| DeepSeek V3.2 latencia | 2918ms | 1899ms | -1019ms |
| Llama 4 Scout 17B | nuevo | 500ms | — |
| TOON coverage | 4 tests | 10 tests (+noex) | fase 2 completa |
