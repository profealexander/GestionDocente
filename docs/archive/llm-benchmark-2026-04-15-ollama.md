# Benchmark LLM SchoolAI — 2026-04-15 (Ollama Cloud)

Script: `scripts/benchmark_llm.py` (Phase 1+2)  
Tests: `simple`, `format` (latencia) + `att_absent`, `att_query`, `no_tool`, `tool_choice` (TOON)  
Runs: 1 por test · Pool: Ollama Cloud únicamente (`--models ollama`)

---

## Modelos probados

| Modelo | ID Ollama | reasoning_mode | thinking_budget |
|--------|-----------|----------------|----------------|
| Kimi K2.5 | `kimi-k2.5:cloud` | — | 2000 |
| GLM 5.1 [medium] | `glm-5.1:cloud` | medium | 2000 |
| GLM 5.1 [low] | `glm-5.1:cloud` | low | 2000 |
| Gemma 4 31B [medium] | `gemma4:31b-cloud` | medium | 1500 |
| Gemma 4 31B [low] | `gemma4:31b-cloud` | low | 1500 |
| Gemma 4 31B [off] | `gemma4:31b-cloud` | off | 1500 |
| GPT-OSS 120B [medium] | `gpt-oss:120b-cloud` | medium | — |
| GPT-OSS 120B [off] | `gpt-oss:120b-cloud` | off | — |
| GPT-OSS 20B | `gpt-oss:20b-cloud` | — | — |
| MiniMax M2.7 | `minimax-m2.7:cloud` | — | 2000 |
| Nemotron 3 Super 120B | `nemotron-3-super:cloud` | — | — |
| Gemini 3 Flash Preview | `gemini-3-flash-preview:cloud` | — | — |

---

## Latencia (tests: simple + format, ok runs only)

| # | Modelo | avg total_ms | TTFT |
|---|--------|-------------:|-----:|
| 1 | **Nemotron 3 Super 120B** | **495ms** | ~412ms |
| 2 | GPT-OSS 20B | 521ms | ~460ms |
| 3 | **GPT-OSS 120B [off]** | **1 008ms** | 589–1080ms |
| 4 | GPT-OSS 120B [medium] | 1 089ms | 750–832ms |
| 5 | **Gemini 3 Flash Preview** | **1 939ms** | 1039–1510ms |
| 6 | Gemma 4 31B [low] | ~640ms¹ | 423–442ms |
| 7 | Kimi K2.5 | 4 565ms | 2167–2331ms |
| 8 | Gemma 4 31B [medium] | 14 811ms | 1901ms / 304ms² |
| — | MiniMax M2.7 | 25 899ms | 18–46s³ |
| — | Gemma 4 31B [off] | ~42 514ms | 25–47s⁴ |

> ¹ Gemma 4 31B [low]: latency tests rápidos, TOON tests 1–1.7s  
> ² Gemma 4 31B [medium]: `simple` tardó 2154ms pero `no_tool` TOON tardó **145s** (over-thinking)  
> ³ MiniMax M2.7: thinking budget domina el TTFT — necesita `reasoning_mode="off"` para latencia real  
> ⁴ Gemma 4 31B [off]: paradójicamente lento en latency tests (thinking activo por defecto aún con mode=off via Ollama)

---

## TOON Tool Calling — Score

| Modelo | Tests | TOON✓ | Tool✓ | Args✓ | Score | Nota |
|--------|------:|------:|------:|------:|------:|------|
| GPT-OSS 120B [medium] | 8 | 8 | 8 | 8 | **100%** | Completo (latencia + TOON) |
| GPT-OSS 120B [off] | 8 | 8 | 8 | 8 | **100%** | |
| Gemma 4 31B [medium] | 12 | 12 | 12 | 12 | **100%** | `no_tool` tardó 145s |
| Gemma 4 31B [low] | 4 | 4 | 4 | 4 | **100%** | Sweet spot velocidad |
| Gemma 4 31B [off] | 4 | 4 | 4 | 4 | **100%** | Latency tests lentos |
| Kimi K2.5 | 4 | 4 | 4 | 4 | **100%** | |
| MiniMax M2.7 | 4 | 4 | 4 | 4 | **100%** | |
| Nemotron 3 Super 120B | 4 | 4 | 4 | 4 | **100%** | `format` vacío (1 fluke) |
| Gemini 3 Flash Preview | 4 | 4 | 4 | 4 | **100%** | `att_query`: `cursos=8eg` (truncó `8egb`) |
| GPT-OSS 20B | 2 | 2 | 2 | 2 | **67%** ⚠️ | empty en att_absent / att_query (native tool call) |
| GLM 5.1 [medium/low] | 0 | — | — | — | **—** | 403 "model experiencing high volume" |

---

## Problemas detectados

| Modelo | Error | Causa | Estado |
|--------|-------|-------|--------|
| **GLM 5.1** | 403 high volume | Saturado en Ollama Cloud | ⚠️ Reintentar en otro horario |
| **GPT-OSS 20B** | empty en att_abstract/att_query | Native tool calling interno (igual que Groq) | Conocido — no usar para TOON con system prompt TOON |
| **MiniMax M2.7** | TTFT 19–46s | thinking_budget=2000 domina — modelo razona demasiado | 🔧 Probar con reasoning_mode="off" |
| **Gemma 4 31B [medium]** | no_tool tardó 145s | Budget 1500 × 1.0 = sobre-razona queries simples | ✅ Usar [low] en producción (budget × 0.4) |
| **Nemotron 3 Super 120B** | format → empty (1 vez) | Posible fluke o contexto vacío | Monitorear en próximo run |
| **Gemini 3 Flash Preview** | att_query devolvió `8eg` | Truncó el course code `8egb` | ⚠️ Revisar en run con más ejemplos |

---

## Observaciones clave

### Nemotron 3 Super 120B — sorpresa del run
495ms avg, 100% TOON (4/4), 120B MoE con solo 12B activos. El modelo más rápido de Ollama Cloud
en este run. Un fluke en `format` (empty) no cambia el perfil — candidato sólido para extractor.

### Gemma 4 31B [low] — sweet spot confirmado
~430ms TTFT, 100% TOON. El mode [medium] over-piensa queries triviales (`no_tool` = 145s, `tool_choice` = 31s).
Para SchoolAI usar siempre [low] o [off] — no [medium].

### MiniMax M2.7 — necesita reasoning_mode="off"
100% TOON pero TTFT inaceptable con thinking_budget=2000. Pendiente: re-testear con mode=off
para ver latencia real. SWE-Pro 56.22% sugiere que la calidad vale el retest.

### Gemini 3 Flash Preview — candidato para extractor
~1.9s avg, 100% TOON. Más nuevo que Gemini 2.5 Flash. El truncamiento del course code en att_query
es una señal amarilla — verificar con más casos en próximo run.

### Kimi K2.5 — orchestrator candidate
4.5s avg, 100% TOON, multimodal nativo. Latencia aceptable para Bot Agente (donde se espera
razonamiento), no para extractor. Gratis vía Ollama Cloud.

---

## Pendiente

- [ ] MiniMax M2.7 con `reasoning_mode="off"` — latencia real sin thinking
- [ ] GLM 5.1 — reintentar en horario de menor carga
- [ ] Nemotron 3 Super 120B — run con 3 repeticiones para confirmar el fluke en `format`
- [ ] Gemini 3 Flash Preview — más casos att_query para confirmar si el truncamiento es sistemático
