# LLM Benchmark — 2026-04-21

**Script:** `scripts/benchmark_llm.py`  
**Tests:** JSON-full (10 casos) · JSON-noex (10 casos sin example block) · Latencia (simple, format, multilang, spanish_input)  
**Modelos probados:** 46 · **Pools activos:** DeepSeek, Google, Groq, HuggingFace (nuevo), Kilo, Mistral, NVIDIA, Ollama Cloud, OpenRouter, Z.AI  
**Nota:** Se eliminaron los tests TOON YAML del default — solo JSON desde este run.

---

## Ranking Global

Score = latencia 30% + JSON-full 35% + JSON-noex 35%

| # | Modelo | Provider | Pool | Lat avg | Tok/s | JSON full | JSON noex | Score | Rol en stack |
|---|--------|----------|------|---------|-------|-----------|-----------|-------|-------------|
| 1 | **Mistral Medium** | Mistral | mistral | 1992ms | 36t/s | 100% | 100% | **95.3%** | extractor+router ★ |
| 2 | GPT-OSS 120B [off] | Ollama Cloud | ollama | 3604ms | — | 100% | 100% | 91.5% | candidato |
| 3 | Gemma 4 31B [off] | Ollama Cloud | ollama | 3641ms | — | 100% | 100% | 91.4% | candidato |
| 4 | **Qwen3 32B (HF/nscale)** 🆕 | HuggingFace | hf | **803ms** | 254t/s | 90% | 90% | **91.1%** | candidato |
| 5 | Gemma 4 26B | Google | google | 3797ms | 3t/s | 100% | 100% | 91.0% | candidato |
| 6 | **DeepSeek V3.2 Chat** | DeepSeek | deepseek | 4836ms | 12t/s | 100% | 100% | **88.6%** | fallback ★ |
| 7 | Gemma 4 31B [low] | Ollama Cloud | ollama | 5352ms | — | 100% | 100% | 87.4% | candidato |
| 8 | GPT-OSS 120B [medium] | Ollama Cloud | ollama | 4031ms | — | 100% | 90% | 87.0% | candidato |
| 9 | Grok Code Fast 1 | Kilo AI | kilo | 4692ms | 79t/s | 100% | 90% | 85.4% | candidato |
| 10 | **Llama 3.1 8B (HF/cerebras)** 🆕 | HuggingFace | hf | **385ms** | 172t/s | 60% | 100% | **85.1%** | candidato |
| 11 | Gemma 4 31B [medium] | Ollama Cloud | ollama | 6912ms | — | 100% | 100% | 83.7% | candidato |
| 12 | **Mistral Small** | Mistral | mistral | 1120ms | 58t/s | 100% | 60% | **83.4%** | chat_fallback ★ |
| 13 | Gemini 3 Flash Preview | Ollama Cloud | ollama | 7224ms | — | 100% | 100% | 82.9% | candidato |
| 14 | ByteDance Dola Seed 2.0 Pro | Kilo AI | kilo | 7403ms | 25t/s | 100% | 100% | 82.5% | candidato |
| 15 | Kimi K2.5 | Ollama Cloud | ollama | 7922ms | — | 100% | 100% | 81.3% | candidato |
| 16 | Gemma 4 31B | Google | google | 6795ms | 3t/s | 90% | 100% | 80.5% | candidato |
| 17 | Stepfun Step-3.5 Flash | OpenRouter | openrouter | 2070ms | 88t/s | 100% | 50% | 77.6% | candidato |
| 18 | **GPT-OSS 120B** | Groq | groq | **597ms** | 136t/s | 100% | 40% | 77.6% | orchestrator_fallback ★ |
| 19 | Qwen3 32B | Groq | groq | 8898ms | 121t/s | 100% | 90% | 75.5% | candidato |
| 20 | Gemini 3.1 Flash Lite Preview | Google | google | 10808ms | 6t/s | 100% | 100% | 74.5% | candidato |
| 21 | Llama 4 Scout 17B | Groq | groq | 1959ms | 51t/s | 100% | 40% | 74.4% | candidato |
| 22 | **DeepSeek V3.2 Reasoner** | DeepSeek | deepseek | 11192ms | 21t/s | 100% | 100% | **73.6%** | orchestrator ★ |
| 23 | ByteDance Seed 2.0 Lite | OpenRouter | openrouter | 12707ms | 26t/s | 100% | 100% | 70.0% | candidato |
| 24 | Qwen3 8B (HF/nscale) 🆕 | HuggingFace | hf | 1529ms | 147t/s | 100% | 20% | 68.4% | candidato |
| 25 | GLM-4V Flash | Z.AI | zai | 2201ms | 17t/s | 100% | 20% | 66.8% | candidato |
| 26 | Nemotron 3 Super 120B | Kilo AI | kilo | 4065ms | 36t/s | 100% | 30% | 65.9% | candidato |
| 27 | Qwen3 14B (HF/nscale) 🆕 | HuggingFace | hf | 4233ms | 43t/s | 100% | 30% | 65.5% | candidato |
| 28 | MiniMax M2.7 [off] | Ollama Cloud | ollama | 5251ms | — | 100% | 30% | 63.1% | candidato |
| 29 | Gemma 3 27B (HF/nscale) 🆕 | HuggingFace | hf | 2132ms | — | 80% | 20% | 60.0% | candidato |
| 30 | Nemotron 3 Super 120B | Ollama Cloud | ollama | 3997ms | — | 100% | 10% | 59.1% | candidato |
| 31 | MiniMax M2.7 | Ollama Cloud | ollama | 7448ms | — | 100% | 30% | 57.9% | candidato |
| 32 | Llama 3.3 70B (NVIDIA NIM) | NVIDIA | nvidia | 6094ms | — | 70% | 50% | 57.6% | candidato |
| 33 | Llama 3.3 70B (HF/sambanova) 🆕 | HuggingFace | hf | 1324ms | 41t/s | 20% | 50% | 51.4% | candidato |
| 34 | DeepSeek R1 Distill 7B (HF/nscale) 🆕 | HuggingFace | hf | 5105ms | 47t/s | 80% | 10% | 49.4% | candidato |
| 35 | Llama 3.3 70B (HF/cerebras) 🆕 | HuggingFace | hf | 781ms | 80t/s | 10% | 40% | 45.7% | candidato |
| 36 | ~~Mistral Large~~ | Mistral | mistral | 2166ms | 30t/s | 10% | 30% | 38.9% | reemplazado |
| 37 | ~~GPT-OSS 20B~~ | Groq | groq | 694ms | 133t/s | 10% | 10% | 35.4% | reemplazado |
| 38 | GPT-OSS 20B (Ollama Cloud) | Ollama Cloud | ollama | 2821ms | — | 10% | 10% | 30.3% | candidato |
| 39 | ~~Gemini 2.5 Flash Lite~~ | Google | google | 733ms | 23t/s | 0% | 0% | 28.3% | reemplazado |
| 40 | Gemma 3 27B | Google | google | 2932ms | — | 0% | 0% | 23.1% | candidato |
| 41 | Gemma 3 12B | Google | google | 6518ms | — | 0% | 0% | 14.6% | candidato |

---

## Sin datos (error / skipped)

| Modelo | Razón |
|--------|-------|
| Arcee Trinity Large (OpenRouter) | Errores HTTP en todos los TOON JSON |
| Arcee Trinity Large Thinking (Kilo) | 403 — requiere cuenta PRO |
| Gemma 4 31B (OpenRouter free) | Errores HTTP |
| Nemotron Nano 12B VL (OpenRouter) | Errores HTTP |
| Llama 3.3 70B (Groq) | 404 — ID retirado |
| Llama 3.1 8B (Groq) | 404 — ID retirado |
| Llama 4 Scout (OpenRouter free) | 404 — ID no encontrado |
| MiniMax M1 | Sin saldo |
| Moonshot v1 8K | Key inválida |
| Compound Beta (web agent) | Request Entity Too Large |

---

## Cambios de stack aplicados

| Rol | Antes | Después | Razón |
|-----|-------|---------|-------|
| extractor+router | `google/gemini-3.1-flash-lite-preview` | **`mistral/mistral-medium-latest`** | Gemini 0%/0% → Mistral 100%/100% |
| chat_fallback | `groq/qwen/qwen3-32b` (vía Groq) | **`mistral/mistral-small-latest`** | Mejor score noex consistente |
| orchestrator_fallback | `…,mistral/mistral-large-latest` | sin Mistral Large | Large 10%/30% — peor que Small |
| orchestrator_fallback | `groq/openai/gpt-oss-20b` (implícito) | **`groq/openai/gpt-oss-120b`** | 120B: 100%/40% vs 20B: 10%/10% |

---

## Notas HuggingFace (nuevo pool)

- **Qwen3 32B vía nscale**: 803ms, 254 tok/s — el más rápido con score >90%. Candidato fuerte para reemplazar extractor si se integra HF provider en el cliente.
- **Llama 3.1 8B vía cerebras**: 385ms — el más rápido absoluto del benchmark. full 60% / noex 100% — patrón inverso inusual.
- **Llama 3.3 70B** (cerebras y sambanova): latencia buena pero TOON muy bajo (10-40%) — no apto para tool calling.
- `hf_token` añadido a `config.py`; provider `huggingface` añadido a `providers.py`.

---

## Nota sobre Mistral Medium

En el run `2026-04-19-181605` Mistral Medium marcó 1/10 — falso negativo por rate limiting (12 RPM pool compartido de 3 modelos, throttled). En todos los demás runs: 10/10 consistente. El score 95.3% es fiable.
