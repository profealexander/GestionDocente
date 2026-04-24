# Evaluación de Modelos LLM — 2026-04-13

Benchmark completo corrido desde local (WSL2) contra el script `openclaw/benchmark-ollama-native.mjs`.
18 prompts por modelo: latencia, calidad, razonamiento, tool calling, multilingüe (español), instrucciones, contexto multi-turn.

---

## Stack actual de SchoolAI (2026-04-13)

```env
LLM_EXTRACTOR=google/gemini-2.5-flash-lite
LLM_ROUTER=google/gemini-2.5-flash-lite
LLM_CHAT=mistral/mistral-small-latest
LLM_ORCHESTRATOR=deepseek/deepseek-reasoner
LLM_ORCHESTRATOR_FALLBACK=deepseek/deepseek-chat,google/gemini-2.5-flash-lite,mistral/mistral-large-latest
```

Historial de cambios:

| Fecha | Variable | Antes | Después | Razón |
|---|---|---|---|---|
| 2026-04-13 | `LLM_CHAT` | `mistral-large-latest` | `mistral-small-latest` | Misma quality (97%), más rápido y barato |
| 2026-04-13 | `LLM_ORCHESTRATOR` | `mistral-small-latest` | `deepseek/deepseek-reasoner` | 100% quality + reasoning para multi-step tool planning |
| 2026-04-13 | Fallback | `gemini,nvidia,mistral-large` | `deepseek-chat,gemini,mistral-large` | NVIDIA eliminado (P95=11s inaceptable); DeepSeek Chat más estable (P95=1.7s) |

**Nota Gemini:** `google/gemini-2.5-flash-lite` se usa en SchoolAI como extractor/router (gratis, 94% quality, 460ms P50). Decisión de eliminar Gemini aplica solo a OpenClaw.

---

## Resultados por provider

### Google AI Studio (gratis — 14,400 req/día)

| Modelo | ID | Quality | Avg TTFT | P50 TTFT | Tok/s | Tool | Costo |
|---|---|:---:|:---:|:---:|:---:|:---:|:---:|
| Gemma 4 26B MoE | `gemma-4-26b-a4b-it` | 94% | 911ms | 834ms | 6.4 | ✅ 100% | $0 |
| **Gemini 2.5 Flash Lite** | `gemini-2.5-flash-lite` | 94% | 558ms | 460ms | 54.4 | ✅ 100% | $0 |

**Gemini 2.5 Flash Lite** es la mejor opción gratuita: más rápida que Gemma, igual quality, perfecta para extractor y router.

---

### Mistral AI

| Modelo | ID | Quality | Avg TTFT | P50 TTFT | Tok/s | Tool | Costo/1M |
|---|---|:---:|:---:|:---:|:---:|:---:|:---:|
| **Mistral Small** | `mistral-small-latest` | 97% | 455ms | 421ms | 51.9 | ✅ 100% | $0.20/$0.60 |
| Mistral Large | `mistral-large-latest` | 97% | 524ms | 470ms | 32.1 | ✅ 100% | mayor |

Misma quality en ambos. Small es más rápido y barato — usar como primario. Large solo como último fallback pagado.

---

### NVIDIA NIM (gratis — free tier)

| Modelo | ID | Quality | Avg TTFT | P50 TTFT | P95 TTFT | Tok/s | Tool |
|---|---|:---:|:---:|:---:|:---:|:---:|:---:|
| Llama 3.3 70B | `meta/llama-3.3-70b-instruct` | 97% | 1,823ms | 314ms | 11,407ms | 31.4 | ✅ 100% |

**Advertencia:** P95 de 11s por `throttled_queue` en free tier. Bueno como fallback de emergencia, no como primario. Cuando no está bajo carga, P50=314ms es excelente.

---

### Groq (gratis — free tier con límite 12K tokens en Railway)

| Modelo | ID | Quality | Avg TTFT | P50 TTFT | Tok/s | Tool | Deep Think | Costo/1M |
|---|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **GPT-OSS 20B** | `openai/gpt-oss-20b` | **100%** | 235ms | 213ms | 309 | ✅ 100% | ✅ 55tok | $0 |
| GPT-OSS 120B | `openai/gpt-oss-120b` | 95% | 356ms | 270ms | 212 | ✅ 100% | ✅ 61tok | $0 |
| Llama 4 Scout 17B | `meta-llama/llama-4-scout-17b-16e-instruct` | 94% | 811ms | 756ms | 55.9 | ✅ 100% | — | $0.11/$0.34 |
| Llama 3.1 8B | `llama-3.1-8b-instant` | 89% | 287ms | 222ms | 92 | ✅ 100% | — | $0.05/$0.08 |
| Qwen3-32B | `qwen/qwen3-32b` | 100%* | 426ms | 280ms | 191 | ⚠️ 67% | ✅ 109tok | $0.29/$0.59 |
| Groq Compound | `groq/compound` | 96% | 1,812ms | 1,145ms | — | ❌ | — | $0 |
| Groq Compound Mini | `groq/compound-mini` | 93% | 1,143ms | 1,071ms | — | ❌ | — | $0 |
| Llama 3.3 70B | `llama-3.3-70b-versatile` | 91% | 249ms | 226ms | 91 | ⚠️ 89% | — | $0.59/$0.79 |

*Qwen3-32B: quality 100% en razonamiento pero thinking mode interfiere con tool calling (67% accuracy).

**Notas importantes:**
- El "límite de 12K tokens de Groq" documentado anteriormente en OpenClaw era un error empírico de Railway, **no un límite oficial de Groq**. El context window real en todos los modelos Groq free tier es 131,072 tokens. Los límites reales son RPM/TPM/TPD por modelo.
- GPT-OSS 20B y 120B son gratis y los más rápidos del benchmark completo
- Groq Compound / Compound Mini no soportan tool calling (HTTP 400) — no aptos para orchestrator
- Groq Whisper sigue siendo el mejor para transcripción de voz en español

**Posición pendiente de aplicar:** GPT-OSS 20B podría ir entre Gemini y NVIDIA en el fallback del orchestrator. Para SchoolAI en localhost no hay restricción de contexto.

---

### Kilo Gateway (gratis)

| Modelo | ID | Quality | Avg TTFT | P50 TTFT | Tok/s | Tool | Deep Think |
|---|---|:---:|:---:|:---:|:---:|:---:|:---:|
| Nemotron 120B | `nvidia/nemotron-3-super-120b-a12b:free` | **100%** | 6,505ms | 3,166ms | 20.5 | ✅ 100% | ✅ 58tok |

Quality perfecta pero demasiado lento para chat interactivo. P95=23s. Útil solo si quality importa más que velocidad.

---

### Ollama Cloud (gratis — requiere cuenta ollama.com)

| Modelo | ID Ollama | Quality | Avg TTFT | P50 TTFT | Tok/s | Tool |
|---|---|:---:|:---:|:---:|:---:|:---:|
| **Gemma 4 31B** | `gemma4:31b-cloud` | 94% | 4,117ms* | 796ms | 14.8 | ✅ 100% |
| GPT-OSS 120B | `gpt-oss:120b-cloud` | 61% | 744ms | 434ms | 44.4 | ✅ 100% |
| GLM 5.1 | `glm-5.1:cloud` | 18% | 2,263ms | 1,055ms | 16.9 | ✅ 100% |

*TTFT promedio inflado por cold start del primer request (~42s). P50 real: 796ms.

GPT-OSS 120B y GLM 5.1 tienen `thinking_present_native` — tokens de razonamiento mezclados en la respuesta corrompen respuestas cortas y JSON puro.

---

### Providers inaccesibles (estado 2026-04-13)

| Provider | Modelo | Error | Acción |
|---|---|---|---|
| Xiaomi MiMo | `mimo-v2-flash` / `mimo-v2-pro` | 401 key expirada | Regenerar en xiaomimimo.com |
| ZAI/BigModel | `glm-4v-flash` | fetch failed (WSL) | Funciona en Railway |
| Arcee AI | `trinity-mini` / `trinity-large-thinking` | Saldo $0 — stream vacío | Recargar |
| Clarifai | `gemma-4-31B-it` | 404 modelo no existe | Verificar ID actual |
| Clarifai | `Qwen3_5-35B-A3B-FP8` | 402 sin saldo | Recargar |
| Moonshot/Kimi | `moonshot-v1-8k` | 401 key expirada | Regenerar en platform.moonshot.cn |
| ZhipuAI | `glm-4-air` | 400 modelo no existe | Verificar en consola bigmodel.cn |
| MiniMax | `MiniMax-Text-01` | 429 sin saldo | Sin free tier internacional |
| Meta Muse Spark | — | API privada, solo partners | Esperar acceso público |

---

### DeepSeek AI — ✅ nueva incorporación (2026-04-13)

| Modelo | ID | Quality | P50 TTFT | P95 TTFT | Tok/s | Tool | Deep Think | Costo/1M in/out |
|---|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **DeepSeek V3.2 Chat** | `deepseek-chat` | **97%** | **974ms** | 1,791ms | 18.6 | ✅ 100% | — | $0.28 / $0.42 |
| **DeepSeek V3.2 Reasoner** | `deepseek-reasoner` | **100%** | **986ms** | 1,157ms | 35.6 | ✅ 100% | ✅ 141tok | $0.28 / $0.42* |

*El Reasoner cobra reasoning tokens a $0.55/1M output. Costo real depende del presupuesto de thinking configurado.

**Endpoint:** `https://api.deepseek.com` — OpenAI-compatible. Key var: `DEEPSEEK_KEY`.

DeepSeek V3.2 Chat tiene quality idéntica a Mistral Small/Large con TTFT comparable.
DeepSeek V3.2 Reasoner es el único modelo del benchmark con **100% quality + 100% tool calling + reasoning confirmado** y TTFT bajo 1s.

---

## Tabla global — todos los modelos funcionales

Ordenados por quality desc, P50 TTFT asc. Solo modelos con tool calling funcional.

| Modelo | Provider | Quality | P50 TTFT | P95 TTFT | Tok/s | Tool | Deep Think | Costo | Apto SchoolAI |
|---|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| **DeepSeek V3.2 Reasoner** | DeepSeek | **100%** | 986ms | 1,157ms | 35.6 | ✅ | ✅ 141tok | bajo | ✅ |
| GPT-OSS 20B | Groq | 100% | 213ms | — | 309 | ✅ | ✅ 55tok | $0 | ✅ |
| Nemotron 120B | Kilo | 100% | 3,166ms | ~23s | 21 | ✅ | ✅ 58tok | $0 | lento |
| Mistral Small | Mistral | 97% | 421ms | — | 52 | ✅ | — | bajo | ✅ primario |
| Mistral Large | Mistral | 97% | 470ms | — | 32 | ✅ | — | medio | ✅ fallback |
| Llama 3.3 70B (NVIDIA) | NVIDIA NIM | 97% | 314ms | 11,407ms | 31 | ✅ | — | $0 | ✅ fallback |
| **DeepSeek V3.2 Chat** | DeepSeek | **97%** | 974ms | 1,791ms | 18.6 | ✅ | — | bajo | ✅ fallback |
| GPT-OSS 120B | Groq | 95% | 270ms | — | 212 | ✅ | ✅ 61tok | $0 | ✅ |
| Gemini 2.5 Flash Lite | Google | 94% | 460ms | — | 54 | ✅ | — | $0 | ✅ extractor |
| Gemma 4 26B MoE | Google | 94% | 834ms | — | 6 | ✅ | — | $0 | ✅ |
| Llama 4 Scout 17B | Groq | 94% | 756ms | — | 56 | ✅ | — | bajo | ✅ |
| Gemma 4 31B (Ollama) | Ollama Cloud | 94% | 796ms | — | 15 | ✅ | — | $0 | — |
| Llama 3.1 8B | Groq | 89% | 222ms | — | 92 | ✅ | — | mínimo | ⚠️ calidad baja |
| Step 3.5 Flash (Puter) | Puter/StepFun | 22% | 1,391ms | — | — | ⚠️ | — | $0 | ❌ |

---

## Stack SchoolAI recomendado (2026-04-13)

```env
LLM_EXTRACTOR=google/gemini-2.5-flash-lite
LLM_ROUTER=google/gemini-2.5-flash-lite
LLM_ORCHESTRATOR=mistral/mistral-small-latest
LLM_CHAT=mistral/mistral-small-latest
LLM_ORCHESTRATOR_FALLBACK=google/gemini-2.5-flash-lite,nvidia/llama-3.3-70b-instruct,deepseek/deepseek-chat,mistral/mistral-large-latest
```

Cambio respecto a la config anterior:
- Agregado `deepseek/deepseek-chat` en fallback (entre NVIDIA y Mistral Large)
- DeepSeek es el único fallback pagado con P95 estable (1,791ms vs 11,407ms de NVIDIA)
