# Benchmark LLM — Tests Pendientes

Última actualización: 2026-04-19

---

## ✅ Completado en 2026-04-19

| Item | Descripción |
|------|-------------|
| JSON tests | 20 tests `_json` / `_json_noex` implementados y corridos en todos los API pools |
| Parser fix | `decode_json_response()` corregido — regex no-greedy → `json.JSONDecoder.raw_decode()` |
| Gemma 3 27B/12B | Probados — incompatibles con OpenAI-compat (400 error en system prompt) |
| Gemma 4 26B/31B | TOON y JSON completos — Gemma 4 26B líder TOON noex (90%) |
| RPM Google corregido | Todos los modelos Google tienen RPM real en el script (10–15 RPM, no 30) |
| Ollama completo TOON | 8 modelos + múltiples modos (off/low/medium) |
| Ollama JSON completo | 11 modelos con modos thinking — run 20260419-212234 |
| Nuevos OpenRouter | Arcee Trinity, Stepfun Step-3.5, ByteDance Seed 2.0 Lite agregados |
| OpenRouter JSON | Stepfun, ByteDance, Nemotron Nano con JSON + simple/format — run 20260419-213010 |
| DeepSeek confirmado | `deepseek-reasoner` ahora es V3.2 thinking — nombre actualizado en script |
| Rate limits Google | Documentados por modelo (RPM/TPM/RPD) en memory y benchmark |
| Kilo AI integrado | 4 modelos free probados — Grok Code Fast 1 destaca (100% noex, 3.6s) — run 20260419-212602 |
| Clarifai evaluado | Sin free tier real — $0.00 balance, todo 402. Open source = dedicated compute (pago) |
| Thinking modes Ollama | [off/low/medium] en Gemma 4 31B y GPT-OSS 120B — conclusión: [off] = misma calidad, menor latencia |

---

## Tests pendientes inmediatos

### Arcee Trinity Large — reintentar mañana
```bash
uv run python scripts/benchmark_llm.py --models openrouter \
  --tests simple,format,att_absent_json,att_late_json,att_all_present_json,att_justified_json,att_query_json,att_multi_json,hw_assign_json,no_tool_json,tool_choice_json,att_query_long_json,att_absent_json_noex,att_query_json_noex,no_tool_json_noex,att_query_long_json_noex
```
Cuota OpenRouter free agotada el 2026-04-19. `arcee-ai/trinity-large-preview:free`

### GLM 5.1 — reintentar en otro horario
Todos 403 "high volume" en Ollama Cloud. Reintentar a las 06:00 UTC (mediodía China menor carga).

### Gemma 3 27B — native Gemini API
El endpoint OpenAI-compat rechaza system prompts complejos para Gemma 3 (400 error).  
Necesita refactor del script para usar `google-generativeai` SDK nativo.  
**Impacto:** Gemma 3 27B tiene 30 RPM y RPD 14.400/día — el mayor margen de Google free tier.

---

## Modelos nuevos — pull pendiente (Ollama)

| Modelo | ID Ollama | Razón |
|--------|-----------|-------|
| devstral-small-2 | `devstral-small-2:cloud` | 24B coding, candidato orchestrator |
| qwen3-next | `qwen3-next:cloud` | Sucesor Qwen3, 80B MoE |
| ministral-3 | `ministral-3:cloud` | Edge 3B-14B, latencia mínima |

```bash
ollama pull devstral-small-2:cloud
ollama pull qwen3-next:cloud
ollama pull ministral-3:cloud
```

---

## Tests de modos thinking (API directa)

Los modelos Ollama se prueban en [off/low/medium] pero los modelos API solo tienen una entrada.  
Para probar DeepSeek V3.2 Reasoner en distintos `thinking_budget`:

| Modelo | Modo pendiente | Razón |
|--------|---------------|-------|
| DeepSeek V3.2 Reasoner | [low] thinking_budget=1000 | ¿Es más rápido con menos thinking? |
| DeepSeek V3.2 Reasoner | [off] thinking_budget=0 | Baseline sin thinking |
| Qwen3 32B | thinking habilitado en Groq | Groq rechazó el param — verificar si ya aceptan |

---

## Mejoras al script pendientes

| Feature | Descripción | Prioridad |
|---------|-------------|-----------|
| Native Gemini API | `google-generativeai` para Gemma 3 — evita 400 en OpenAI-compat | Alta |
| SQLite history | Guardar resultados en DB para P50/P95 reales | Media |
| Ranking latencia en runs JSON | El ranking global queda vacío si no hay tests de latencia en el run | Media |
| `--runs 3` por defecto | Estadísticas reales vs 1 run actual | Media |
| Retry en `empty` status | Re-run no-streaming cuando streaming retorna vacío | Baja |
| Pricing dict | Costo estimado por test en centavos | Baja |

---

## Modelos con problemas conocidos — watchlist

| Modelo | Provider | Problema | Acción pendiente |
|--------|----------|----------|-----------------|
| Gemma 3 27B/12B | Google | 400 OpenAI-compat | Native Gemini API |
| GLM 5.1 | Ollama Cloud | 403 alta carga | Reintentar otro horario |
| Arcee Trinity | OpenRouter free | 429 cuota diaria | Reintentar 2026-04-20 |
| Mistral Large | Mistral | 429 frecuente (pool compartido) | Separar pool o aumentar delay |
| Llama 4 Scout 17B | Groq | JSON: att_query devuelve mark_attendance | Bug semántico — revisar system prompt |
| Gemini 2.5 Flash Lite | Google | Deprecación 2026-06-17 | Migrar a gemini-3.1-flash-lite-preview |
| kimi-k2-instruct | Groq (via moonshotai) | En producción como orchestrator | Monitorear disponibilidad |
