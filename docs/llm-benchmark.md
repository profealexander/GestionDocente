# LLM Benchmark — Ranking Consolidado SchoolAI

Todos los modelos evaluados. Se muestra el mejor resultado por modelo (mejor run / mejor modo).  
Fuentes: `docs/llm-benchmark-2026-04-13.md`, `docs/llm-benchmark-2026-04-15.md`, `docs/llm-benchmark-2026-04-15-ollama.md`, `docs/llm-benchmark-2026-04-19.md`, `docs/llm-benchmark-2026-04-19-ollama.md`

---

## Práctica de documentación

| Artefacto | Propósito |
|-----------|-----------|
| `docs/llm-benchmark.md` | **Este doc** — ranking consolidado, actualizar con cada run |
| `docs/llm-benchmark-YYYY-MM-DD.md` | Resultados completos de un run específico |
| `docs/llm-benchmark-YYYY-MM-DD-<tag>.md` | Run temático (pool específico, modo experimental) |
| `scripts/benchmark_llm.py --no-json` | Sin JSON output — solo consola |
| `scripts/benchmark_llm.py` (default) | Con JSON — raw results en `benchmarks/YYYYMMDD_HHMMSS.json` |

---

## Ranking TOON — mejor resultado por modelo

Ordenado por score global (lat 30% · full 35% · noex 35%).  
`noex` = test sin bloque de formato ejemplo en el prompt — mide inferencia real del modelo.

| # | Modelo | Provider | Lat avg | TOON Full | TOON Noex | Score | Run |
|---|--------|----------|---------|-----------|-----------|-------|-----|
| 1 | **GPT-OSS 20B** ☁ | Ollama Cloud | 4608ms | 100% | **100%** | **96.5%** | 04-19 |
| 2 | **Gemma 4 26B** | Google API | 4092ms | 100% | **90%** | **92.6%** | 04-19 |
| 3 | **Gemini 3 Flash Preview** ☁ | Ollama Cloud | 5076ms | 100% | **88%** | **91.8%** | 04-19 |
| 4 | Mistral Small | Mistral API | 1056ms | 100% | 40% | 78.0% | 04-19 |
| 5 | Gemma 4 31B [off] | Ollama local | 4009ms | 100% | 20% | 68.9% | 04-19 |
| 6 | GPT-OSS 120B | Groq API | 457ms | 100% | 10% | 68.1% | 04-19 |
| 7 | Llama 4 Scout 17B | Groq API | 822ms | 100% | 10% | 67.7% | 04-19 |
| 8 | Qwen3 32B | Groq API | 1092ms | 100% | 10% | 67.5% | 04-19 |
| 9 | Gemma 4 31B | Google API | 4935ms | 100% | 20% | 67.3% | 04-19 |
| 10 | MiniMax M2.7 [off] | Ollama local | 6134ms | 100% | 20% | 67.3% | 04-19 |
| 11 | Mistral Medium | Mistral API | 1379ms | 100% | 10% | 67.2% | 04-19 |
| 12 | Llama 3.3 70B | NVIDIA NIM | 1486ms | 100% | 10% | 67.1% | 04-19 |
| 13 | Nemotron 3 Super 120B ☁ | Ollama Cloud | 1903ms | 100% | 10% | 67.1% | 04-19 |
| 14 | GLM-4V Flash | Z.AI | 1722ms | 100% | 10% | 66.9% | 04-19 |
| 15 | DeepSeek V3.2 Chat | DeepSeek API | 3069ms | 100% | 10% | 65.6% | 04-19 |
| 16 | Kimi K2.5 ☁ | Ollama Cloud | 4724ms | 100% | 10% | 64.9% | 04-19 |
| 17 | GPT-OSS 120B [medium] ☁ | Ollama Cloud | 4762ms | 100% | 10% | 64.9% | 04-19 |
| 18 | MiniMax M2.7 ☁ | Ollama Cloud | 4888ms | 100% | 10% | 64.8% | 04-19 |
| 19 | Gemini 2.5 Flash Lite | Google API | 1323ms | 100% | 0% | 63.7% | 04-19 |
| 20 | DeepSeek V3.2 Reasoner | DeepSeek API | 6343ms | 100% | 10% | 62.5% | 04-19 |
| 21 | Gemini 3.1 Flash Lite ⚠ | Google API | 6760ms¹ | 100% | 10% | 62.1% | 04-19 |
| — | Nemotron Nano 12B VL | OpenRouter | 7413ms | 33% | 17% | 40.5% | 04-19 |
| — | GPT-OSS 120B [off] ☁ | Ollama Cloud | 21772ms | 100% | 10% | 51.9% | 04-19 |
| — | Gemma 3 27B/12B | Google API | — | **0%** | 0% | ❌ | 04-19 |
| — | GLM 5.1 | Ollama Cloud | — | **0%** | 0% | ❌ 403 | 04-19 |

> ¹ Gemini 3.1 Flash Lite: cold start de 19s en `no_tool` infla avg. Latencia real ~1-2s.  
> ☁ Ollama Cloud: latencia vía red, no comparable directamente con API directa.

---

## Ranking JSON — mejor resultado por modelo (2026-04-19, todos los pools)

**JSON format es el recomendado para SchoolAI en producción.**  
Incluye: API directa (run bphpv4q6e), Ollama (run 20260419-212234), OpenRouter (run 20260419-213010), Kilo AI (run 20260419-212602).

### API Directa

| # | Modelo | Provider | Lat avg | JSON Full | JSON Noex | TOON noex | Delta |
|---|--------|----------|---------|-----------|-----------|-----------|-------|
| 1 | GPT-OSS 120B | Groq API | 395ms | 100% | **100%** | 10% | +90pp |
| 2 | Llama 4 Scout 17B | Groq API | 367ms | 90%³ | 60% | 10% | +50pp |
| 3 | Mistral Small | Mistral API | 792ms | 100% | 80% | 40% | +40pp |
| 4 | Gemini 3.1 Flash Lite | Google API | 990ms | 100% | **100%** | 10% | +90pp |
| 5 | Qwen3 32B | Groq API | 1038ms | 100% | **100%** | 10% | +90pp |
| 6 | Mistral Medium | Mistral API | 1186ms | 100% | **100%** | 10% | +90pp |
| 7 | Mistral Large² | Mistral API | 1436ms | 100% | **100%** | 33% | +67pp |
| 8 | Llama 3.3 70B | NVIDIA NIM | 1486ms | 100% | 67% | 10% | +57pp |
| 9 | DeepSeek V3.2 Chat | DeepSeek API | 1825ms | 100% | **100%** | 10% | +90pp |
| 10 | GLM-4V Flash | Z.AI | 887ms | 100% | 20% | 10% | +10pp |
| 11 | Gemma 4 31B | Google API | 2006ms | 100% | **100%** | 20% | +80pp |
| 12 | Gemma 4 26B | Google API | 2202ms | 100% | **100%** | 90% | +10pp |
| 13 | DeepSeek V3.2 Reasoner | DeepSeek API | 4292ms | 100% | **100%** | 10% | +90pp |
| — | Gemma 3 27B/12B | Google API | — | ❌ | ❌ | ❌ | 400 error |

> ² Mistral Large: datos parciales (429 frecuente — pool compartido con Small+Medium).  
> ³ Llama 4 Scout: `att_query_json` retornó mark_attendance en vez de query_attendance.

### Ollama Cloud (run 20260419-212234)

| # | Modelo | Provider | Lat avg | JSON Full | JSON Noex | Score |
|---|--------|----------|---------|-----------|-----------|-------|
| 1 | GPT-OSS 20B ☁ | Ollama Cloud | 1610ms | 100% | **100%** | 98.4% |
| 2 | GPT-OSS 120B [medium] ☁ | Ollama Cloud | 2163ms | 100% | **100%** | 97.9% |
| 3 | Gemini 3 Flash Preview ☁ | Ollama Cloud | 2226ms | 100% | **100%** | 97.8% |
| 4 | Gemma 4 31B [off] ☁ | Ollama Cloud | 2245ms | 100% | **100%** | 97.8% |
| 5 | GPT-OSS 120B [off] ☁ | Ollama Cloud | 2752ms | 100% | **100%** | 97.3% |
| 6 | MiniMax M2.7 [off] ☁ | Ollama Cloud | 1922ms | 100% | 50% | 80.6% |
| 7 | Kimi K2.5 ☁ | Ollama Cloud | 24068ms | 100% | **100%** | 76.5% |
| 8 | Nemotron 3 Super 120B ☁ | Ollama Cloud | 1728ms | 100% | 25% | 72.1% |
| 9 | MiniMax M2.7 ☁ | Ollama Cloud | 3130ms | 100% | 25% | 70.7% |
| 10 | Gemma 4 31B [low] ☁ | Ollama Cloud | 30455ms | 100% | **100%** | 70.3% |
| 11 | Gemma 4 31B [medium] ☁ | Ollama Cloud | 30761ms | 100% | **100%** | 70.0% |

> Thinking modes [low/medium] vs [off]: no diferencia en calidad JSON — solo latencia. Usar [off] siempre.

### OpenRouter (run 20260419-213010)

| # | Modelo | Provider | Lat avg | JSON Full | JSON Noex | Nota |
|---|--------|----------|---------|-----------|-----------|------|
| 1 | Nemotron Nano 12B VL | OpenRouter free | 2846ms | 100%⁴ | **100%**⁴ | 2 empty |
| 2 | Stepfun Step-3.5 Flash | OpenRouter | 3326ms | 100% | 50% | mejoró de 40% |
| 3 | ByteDance Seed 2.0 Lite | OpenRouter | 6435ms | 100% | **100%** | confirmado |
| ❌ | Arcee Trinity Large | OpenRouter free | — | ❌ | ❌ | 429 cuota diaria |
| ❌ | Gemma 4 31B | OpenRouter free | — | ❌ | ❌ | 429 cuota |

> ⁴ Nemotron Nano: 2 tests empty (tool_choice_json, att_query_long_json_noex) — N efectiva 9/10 full, 3/4 noex.

### Kilo AI (run 20260419-212602)

| # | Modelo | Provider | Lat avg | JSON Full | JSON Noex | Nota |
|---|--------|----------|---------|-----------|-----------|------|
| 1 | **Grok Code Fast 1** | Kilo AI free | 3619ms | 100% | **100%** | ✨ nuevo |
| 2 | ByteDance Dola Seed 2.0 Pro | Kilo AI free | 7508ms | 100% | 75% | variante de Seed |
| 3 | Nemotron 3 Super 120B | Kilo AI free | 4278ms | 100% | 25% | igual que Ollama |
| ❌ | Arcee Trinity Thinking | Kilo AI free | — | ❌ | ❌ | 403 requiere plan pago |

### Clarifai — sin free tier de inferencia

Balance $0.00 → 402 en todos los modelos. Open source requiere "dedicated compute" (pago). Descartado.

---

## Ranking JSON consolidado — 100% noex (mejor por modelo único)

Modelos con **100% JSON noex** confirmado, ordenados por latencia:

| Modelo | Provider | Lat avg | Notas |
|--------|----------|---------|-------|
| GPT-OSS 120B | Groq API | **395ms** | más rápido con 100% noex |
| Gemini 3.1 Flash Lite | Google API | 990ms | candidato extractor/router |
| Qwen3 32B | Groq API | 1038ms | — |
| Mistral Medium | Mistral API | 1186ms | — |
| Mistral Large | Mistral API | 1436ms | datos parciales |
| DeepSeek V3.2 Chat | DeepSeek API | 1825ms | — |
| GPT-OSS 20B ☁ | Ollama Cloud | 1610ms | ☁ latencia red |
| GPT-OSS 120B [medium] ☁ | Ollama Cloud | 2163ms | ☁ latencia red |
| Gemma 4 31B [off] ☁ | Ollama Cloud | 2245ms | ☁ latencia red |
| Gemma 4 31B | Google API | 2006ms | — |
| Gemma 4 26B | Google API | 2202ms | — |
| Gemini 3 Flash Preview ☁ | Ollama Cloud | 2226ms | ☁ latencia red |
| GPT-OSS 120B [off] ☁ | Ollama Cloud | 2752ms | ☁ latencia red |
| Grok Code Fast 1 | Kilo AI free | 3619ms | nuevo — prometedor |
| DeepSeek V3.2 Reasoner | DeepSeek API | 4292ms | lento |
| ByteDance Seed 2.0 Lite | OpenRouter | 6435ms | lento |
| Kimi K2.5 ☁ | Ollama Cloud | 24068ms | muy lento |

---

## Stack SchoolAI activo

```env
# Actualizado: 2026-04-19 (post-benchmark)
LLM_EXTRACTOR=google/gemini-3.1-flash-lite-preview
LLM_ROUTER=google/gemini-3.1-flash-lite-preview
LLM_CHAT=groq/compound-beta
LLM_CHAT_FALLBACK=mistral/mistral-small-latest
LLM_ORCHESTRATOR=moonshotai/kimi-k2-instruct
LLM_ORCHESTRATOR_FALLBACK=deepseek/deepseek-chat,deepseek/deepseek-reasoner,groq/openai/gpt-oss-120b,mistral/mistral-large-latest
LLM_VISION=openrouter/nvidia/nemotron-nano-12b-v2-vl:free
LLM_VISION_FALLBACK=openrouter/google/gemma-4-31b-it:free
```

### Cambios aplicados 2026-04-19

| Variable | Anterior | Nuevo | Razón |
|----------|----------|-------|-------|
| `LLM_EXTRACTOR` | `gemini-2.5-flash-lite` | `gemini-3.1-flash-lite-preview` | Deprecación jun 2026 · 100% JSON noex · 500 RPD vs ~20 |
| `LLM_ROUTER` | `gemini-2.5-flash-lite` | `gemini-3.1-flash-lite-preview` | Igual |
| `LLM_ORCHESTRATOR_FALLBACK` | `...gemini-2.5-flash-lite,gpt-oss-20b...` | `...gpt-oss-120b...` | Eliminado gemini-2.5 (RPD 20/día inútil en fallback) · gpt-oss-120b es 3× más potente |
| `extractor.py` hardcode | `gemini-2.5-flash-lite` | `gemini-3.1-flash-lite-preview` | Modelo hardcodeado en context extractor (archivos/URLs) |

---

## Notas sobre proveedores

| Proveedor | Nota |
|-----------|------|
| DeepSeek | A 2026-04-19, `deepseek-reasoner` es V3.2 thinking mode — **ya no es R1** |
| Gemma 3 | Incompatible con endpoint OpenAI-compat de Google para TOON/JSON — requiere native Gemini API |
| Gemini 2.5 Flash | Eliminado del script — RPD 20/día, ya consumido en un run |
| Arcee Trinity | `arcee-ai/trinity-large-preview:free` — sin resultados (cuota diaria OpenRouter agotada) |
| ByteDance Seed 2.0 Lite | Nuevo — 100% JSON noex, 5297ms latencia (lento pero correcto) |
| Stepfun Step-3.5 Flash | Nuevo — 100% JSON full, 40% noex |
| GLM 5.1 | Todos 403 en Ollama Cloud — reintentar en otro horario |

---

## Modelos descartados / con problemas conocidos

| Modelo | Provider | Problema | Estado |
|--------|----------|----------|--------|
| GPT-OSS 20B | Groq API | TOON 0% — native tool calling interno rechaza system prompt | No usar para extractor directo |
| Llama 3.3 70B | Groq | 404 — retirado de Groq API | Reemplazar con llama-4-scout-17b |
| Llama 3.1 8B | Groq | 404 — retirado de Groq API | Sin reemplazo directo |
| Llama 4 Scout | OpenRouter free | 404 ID incorrecto | Verificar ID en openrouter.ai |
| Gemma 3 27B/12B | Google | 400 — OpenAI-compat rechaza system prompt complejo | Requiere native Gemini API |
| GLM 5.1 | Ollama Cloud | 403 high volume | Reintentar en otro horario |
| Gemini 2.5 Flash | Google | RPD 20/día — removido del script | — |
| Moonshot v1-8k | Moonshot | 401 key inválida | Regenerar en platform.moonshot.cn |
| MiniMax M1 | MiniMax | 429 sin saldo | Recargar en api.minimax.io |
| Arcee Trinity Large | OpenRouter free | 429 cuota diaria — reintentar mañana | Pendiente |
| Arcee Trinity Thinking | Kilo AI free | 403 — requiere plan pago en Kilo | Descartado free |
| Clarifai | Clarifai | $0.00 balance → 402 en todo. Open source = dedicated compute (pago) | Sin free tier real |
| Gemma 4 31B | OpenRouter free | 429 cuota diaria compartida con Nemotron Nano | Descartado free |

---

## Ranking completo JSON — con thinking, RPM y costo (2026-04-19)

Todos los pools combinados. Ordenado por noex% → latencia.  
`noex` = sin bloque de ejemplo en prompt — escenario de producción real.

### Tier 1 — 100% JSON noex

| # | Modelo | Thinking | Provider | Lat avg | Full | Noex | RPM | Costo |
|---|--------|----------|----------|---------|------|------|-----|-------|
| 1 | GPT-OSS 120B | — | Groq API | **395ms** | 100% | 100% | 30 free | gratis |
| 2 | Gemini 3.1 Flash Lite | — | Google API | 990ms | 100% | 100% | 15 / 500 RPD | gratis |
| 3 | Qwen3 32B | — | Groq API | 1038ms | 100% | 100% | 30 free | gratis |
| 4 | Mistral Medium | — | Mistral API | 1186ms | 100% | 100% | ~60 | ~$0.40/$1.20 /1M |
| 5 | Mistral Large⁵ | — | Mistral API | 1436ms | 100% | 100% | ~30 | ~$2/$6 /1M |
| 6 | DeepSeek V3.2 Chat | — | DeepSeek API | 1825ms | 100% | 100% | 60 | $0.28/$0.42 /1M |
| 7 | GPT-OSS 20B ☁ | — | Ollama Cloud | 1610ms | 100% | 100% | 999 | gratis ☁ |
| 8 | GPT-OSS 120B [medium] ☁ | medium | Ollama Cloud | 2163ms | 100% | 100% | 999 | gratis ☁ |
| 9 | GPT-OSS 120B [off] ☁ | off | Ollama Cloud | 2752ms | 100% | 100% | 999 | gratis ☁ |
| 10 | Gemma 4 31B | — | Google API | 2006ms | 100% | 100% | 15 / 1500 RPD | gratis |
| 11 | Gemma 4 26B | — | Google API | 2202ms | 100% | 100% | 15 / 1500 RPD | gratis |
| 12 | Gemini 3 Flash Preview ☁ | — | Ollama Cloud | 2226ms | 100% | 100% | 999 | gratis ☁ |
| 13 | Gemma 4 31B [off] ☁ | **off** | Ollama Cloud | 2245ms | 100% | 100% | 999 | gratis ☁ |
| 14 | Grok Code Fast 1 | optimized | Kilo AI free | 3619ms | 100% | 100% | ~20 | gratis |
| 15 | DeepSeek V3.2 Reasoner | thinking | DeepSeek API | 4292ms | 100% | 100% | 60 | $0.28/$0.42 /1M |
| 16 | ByteDance Seed 2.0 Lite | — | OpenRouter | 6435ms | 100% | 100% | 20 | ? |
| 17 | Kimi K2.5 ☁ | — | Ollama Cloud | 24068ms | 100% | 100% | 999 | gratis ☁ |
| 18 | Gemma 4 31B [low] ☁ | low | Ollama Cloud | 30455ms | 100% | 100% | 999 | gratis ☁ |
| 19 | Gemma 4 31B [medium] ☁ | medium | Ollama Cloud | 30761ms | 100% | 100% | 999 | gratis ☁ |

> ⁵ Mistral Large: datos parciales (429 frecuente — pool compartido). [low/medium] en Ollama = misma calidad que [off], solo más lento — usar **[off]** siempre.

### Tier 2 — 75–80% JSON noex

| # | Modelo | Thinking | Provider | Lat avg | Full | Noex | RPM | Costo |
|---|--------|----------|----------|---------|------|------|-----|-------|
| 20 | Mistral Small | — | Mistral API | 792ms | 100% | 80% | ~60 | ~$0.1/$0.3 /1M |
| 21 | ByteDance Dola Seed 2.0 Pro | — | Kilo AI free | 7508ms | 100% | 75% | ~20 | gratis |
| 22 | Nemotron Nano 12B VL⁴ | — | OpenRouter free | 2846ms | 100% | 100% | 10 | gratis |

> ⁴ Nemotron Nano: 2 tests empty (tool_choice, att_query_long) — N real 9/10 full, 3/4 noex. Latencia muy variable (5s–98s).

### Tier 3 — 50–67% JSON noex

| # | Modelo | Thinking | Provider | Lat avg | Full | Noex | RPM | Costo |
|---|--------|----------|----------|---------|------|------|-----|-------|
| 23 | Llama 4 Scout 17B | — | Groq API | **367ms** | 90% | 60% | 30 free | gratis |
| 24 | Llama 3.3 70B | — | NVIDIA NIM | 1486ms | 100% | 67% | 30 free | gratis |
| 25 | MiniMax M2.7 [off] ☁ | off | Ollama Cloud | 1922ms | 100% | 50% | 999 | gratis ☁ |
| 26 | Stepfun Step-3.5 Flash | — | OpenRouter | 3326ms | 100% | 50% | 20 | ? |

### Tier 4 — < 50% JSON noex

| # | Modelo | Thinking | Provider | Lat avg | Full | Noex | RPM | Costo |
|---|--------|----------|----------|---------|------|------|-----|-------|
| 27 | GLM-4V Flash | — | Z.AI | 887ms | 100% | 20% | 20 | gratis |
| 28 | Nemotron 3 Super 120B ☁ | — | Ollama Cloud | 1728ms | 100% | 25% | 999 | gratis ☁ |
| 29 | Nemotron 3 Super 120B | — | Kilo AI free | 4278ms | 100% | 25% | ~20 | gratis |
| 30 | MiniMax M2.7 ☁ | medium | Ollama Cloud | 3130ms | 100% | 25% | 999 | gratis ☁ |

### ❌ Descartados / sin resultados

| Modelo | Provider | Problema |
|--------|----------|----------|
| Gemma 3 27B/12B | Google API | 400 — requiere native Gemini API |
| Arcee Trinity Large | OpenRouter free | 429 cuota diaria — reintentar |
| Arcee Trinity Thinking | Kilo AI free | 403 — requiere plan pago |
| GLM 5.1 | Ollama Cloud | 403 alta carga — reintentar otro horario |
| Clarifai (todos) | Clarifai | $0 balance — sin free tier real |
| Gemma 4 31B | OpenRouter free | 429 cuota diaria compartida |

### Tabla de decisión por rol

| Rol | Candidato | Razón |
|-----|-----------|-------|
| Extractor/Router (migrar) | `gemini-3.1-flash-lite-preview` | 990ms · 100% noex · 500 RPD gratis |
| Fallback extractor | `groq/openai/gpt-oss-120b` | 395ms · 100% noex · gratis |
| Chat (mantener) | `groq/compound-beta` | web search integrado |
| Orchestrator (mantener) | `groq/moonshotai/kimi-k2-instruct` | — |
| Alternativa gratis rápida | `groq/qwen3-32b` | 1038ms · 100% noex · gratis |
| Alternativa pago barato | `deepseek/deepseek-chat` | 1825ms · 100% noex · $0.28/$0.42/1M |
| Nuevo candidato free | `kilo/x-ai/grok-code-fast-1:optimized:free` | 3619ms · 100% noex · gratis |

---

## Historial de runs

| Fecha | Archivo / Run | Modelos | Tests |
|-------|--------------|---------|-------|
| 2026-04-13 | `llm-benchmark-2026-04-13.md` | 14 modelos directos | quality + latency |
| 2026-04-15 | `llm-benchmark-2026-04-15.md` | 19 modelos directos | simple, format, TOON ×20 |
| 2026-04-15 | `llm-benchmark-2026-04-15-ollama.md` | 12 Ollama Cloud | simple, format, TOON ×20 |
| 2026-04-19 | `llm-benchmark-2026-04-19.md` | 23 API directa + 8 Ollama | TOON ×20 + JSON ×20 + latencia |
| 2026-04-19 | run 20260419-212234 | 11 Ollama (modos thinking) | JSON ×14 + simple/format |
| 2026-04-19 | run 20260419-213010 | 4 OpenRouter + 2 free | JSON ×14 + simple/format |
| 2026-04-19 | run 20260419-212602 | 4 Kilo AI free | JSON ×14 + simple/format |
