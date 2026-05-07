# Plan de correcciones — Auditoría 2026-04-24

Originado por auditoría completa de código, documentación y consistencia.
Estado general: **mayoría de bugs resueltos** — actualizado 2026-05-05.

> Revisión posterior al commit inicial confirmó que Fases 1 y la mayoría de Fase 2 ya estaban implementadas en el código integrado.

---

## Fase 1 — Bugs críticos (bloquean producción)

### ~~1.1 · `call_with_fallback` bloquea el event loop~~ ✅ RESUELTO

`call_with_fallback` es async y usa `asyncio.to_thread` internamente (`skills/llm/client.py`). Los callers en `planner.py:46`, `synthesizer.py:45` y `gateway/router.py` usan `await`.

---

### ~~1.2 · Race condition en `ContextAgent._teacher_has_docs`~~ ✅ RESUELTO

Resuelto con `contextvars.ContextVar` (`_teacher_has_docs_var`) en `skills/orchestrator/skill_agents/context.py:13`. Solución más robusta que la propuesta (ContextVar es safe en asyncio).

---

### ~~1.3 · `schoolai-gateway` no existe como entry point~~ ✅ RESUELTO

Entry point `schoolai-gateway = "schoolai.gateway.runner:run"` existe en `pyproject.toml`.

---

### ~~1.4 · `bot/handlers.py` — doble trabajo cuando `GATEWAY_ENABLED=true`~~ ✅ RESUELTO

`handlers.py:102-104`: `if await intercept(...): return` — early return implementado.

---

## Fase 2 — Bugs medios (afectan correctitud)

### ~~2.1 · `bot/permissions.py` — nunca retorna `"none"`~~ ✅ RESUELTO

Corregido según backlog 2026-04-24.

---

### ~~2.2 · `bot/jornada/flow.py:390` — `session_date` no considera fin de semana~~ ✅ RESUELTO

Corregido según backlog 2026-04-24.

---

### ~~2.3 · `api/routers/health.py` — Redis reportado como "not configured" siempre~~ ✅ RESUELTO

`api/main.py:42-44` llama `init_redis()` en el lifespan startup cuando `REDIS_URL` está definido. El health endpoint ahora reporta correctamente.

---

### ~~2.4 · `gateway/auth.py:42` — rate-limit `_buckets` crece sin TTL~~ ✅ RESUELTO

`gateway/auth.py` ahora tiene purga periódica cada 500 llamadas (`_CLEANUP_EVERY = 500`). Elimina entradas cuyo último timestamp es más viejo que `_WINDOW` (60s).

---

### ~~2.5 · `skills/homework/repository.py` — race condition en sequence_num~~ ✅ RESUELTO

Usa `pg_advisory_xact_lock` en `repository.py:244-247`. Lock liberado automáticamente al final de la transacción.

---

### ~~2.6 · `gateway/app.py:24` — CORS origins sin strip de espacios~~ ❌ INCORRECTO

El código ya hace `.strip()` correctamente: `allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()]`. La auditoría estaba equivocada.

---

## Fase 3 — Documentación incorrecta

### 3.1 · `CLAUDE.md` — múltiples datos incorrectos

**Pasos**:
1. [ ] Corregir sección "Attendance extraction pipeline": fuzzy matcher usa `rapidfuzz.WRatio`, no `SequenceMatcher`
2. [ ] Corregir lista de text_interceptors (sección "Message dispatch pipeline"):
   - Agregar: `modo_chat(1)`, `modo_editar(2)`, `ausencias_natural(8)`, `horario_natural(8)`
3. [ ] Corregir nota sobre Redis: "REDIS_URL no set → RAM only" → clarificar que es degradación automática al fallar ping, no decisión de arquitectura
4. [ ] Corregir Orchestrator LLM: eliminar referencia a "GLM-4.7-Flash (Z.AI)" → poner `groq/openai/gpt-oss-120b` con fallbacks correctos según `config.py`

---

### 3.2 · `.env.example` — stack LLM obsoleto y variables faltantes

**Pasos**:
1. [ ] Eliminar modelos google/gemini-2.5-flash-lite (eliminado del stack)
2. [ ] Actualizar stack LLM completo según `config.py` actual:
   - `LLM_ROUTER=mistral/mistral-medium-latest`
   - `LLM_ROUTER_FALLBACK=deepseek/deepseek-v4-flash`
   - `LLM_SYNTHESIZER=groq/meta-llama/llama-4-scout-17b-16e-instruct`
   - `LLM_SYNTHESIZER_FALLBACK=ollama/gemini-3-flash-preview:cloud,mistral/mistral-small-latest`
   - `LLM_PLANNER=groq/openai/gpt-oss-120b`
   - `LLM_PLANNER_FALLBACK=ollama/gemini-3-flash-preview:cloud,deepseek/deepseek-v4-flash`
   - `LLM_CHAT=groq/compound-beta`
   - `LLM_VISION=openrouter/nvidia/nemotron-nano-12b-v2-vl:free`
   - `LLM_CONTEXT_AGENT=mistral/mistral-small-latest`
3. [ ] Agregar variables faltantes: `ZAI_API_KEY`, `DEEPSEEK_API_KEY`, `KILO_API_KEY`, `HF_TOKEN`, `OPENROUTER_API_KEY`, `NVIDIA_API_KEY`, `MINIMAX_API_KEY`, `MOONSHOT_API_KEY`, `ZHIPU_API_KEY`, `OLLAMA_API_KEY`, `OPENAI_API_KEY`
4. [ ] Agregar: `GATEWAY_ENABLED=false`, `GATEWAY_URL=`, `ADMIN_TELEGRAM_ID=`, `SCHOOL_TIMEZONE=Europe/Madrid`, `SUPERVISED_MODE=false`

---

### 3.3 · `docs/backlog.md` — deuda técnica resuelta marcada como pendiente

**Pasos**:
1. [ ] Marcar como ✅ resuelto: "Persistencia Jornada" (`use_redis=True` ya implementado)
2. [ ] Marcar como ✅ resuelto: "Batch inserts asistencia" (ya usa `insert(Attendance), [list_of_dicts]`)
3. [ ] Corregir: "Bloqueo fin de semana" → no es bloqueo, es fallback a viernes (pero con bug en `_on_absent_day_reason`, ver 2.2)
4. [ ] Agregar como pendiente: los bugs críticos encontrados en esta auditoría (bugs 1.1, 1.2, 1.3)

---

### 3.4 · Docstrings de módulos LLM obsoletos

**Archivos**: `agent/planner.py:4`, `agent/synthesizer.py:4`, `skills/llm/client.py:6`, `skills/llm/usage.py:8`, `skills/orchestrator/skill.py:1`

**Pasos**:
1. [x] `agent/planner.py:4` — corregido a "groq/openai/gpt-oss-120b"
2. [x] `agent/synthesizer.py:4` — corregido a "llm_synthesizer" (2026-05-05)
3. [ ] `skills/llm/client.py:6` — cambiar ejemplo de modelo a uno del stack activo
4. [x] `skills/llm/usage.py:8` — corregido ejemplo a `provider="groq", model="openai/gpt-oss-120b"` (2026-05-05)
5. [ ] `skills/orchestrator/skill.py:1` — actualizar referencia a modelo real del planner

**Nota adicional (2026-05-05):** `skills/context/extractor.py:60,77` hardcodea `model="gemini-3.1-flash-lite-preview"` en código real (no solo docstring). `skills/llm/structured.py:69` docstring corregido.

---

### 3.5 · `docs/architecture/architecture.md` — referencias al entry point inexistente

**Pasos**:
1. [ ] Línea 122 y 254: agregar nota "(entry point pendiente / ver 1.3)" o actualizar si ya se añade el entry point

---

## Fase 4 — Inconsistencias de código

### ~~4.1 · `async_session()` directo en ~40 archivos~~ ✅ RESUELTO

Solo 2 ocurrencias restantes, ambas en `db/connection.py` donde es la implementación interna. Todos los callers usan `get_db_session()`. Corregido según backlog 2026-04-24.

---

### ~~4.2 · `bot/permissions.py:39` — lógica redundante~~ ✅ RESUELTO

Flujo de control limpio, sin returns redundantes.

---

### ~~4.3 · `pyproject.toml` — grupos dev duplicados con versiones diferentes~~ ✅ RESUELTO

Un solo `[dependency-groups].dev` en pyproject.toml.

---

### 4.4 · `watchfiles` no declarado como dependencia directa

**Archivo**: `pyproject.toml`, `src/schoolai/bot/dev.py:3`  
**Pasos**:
1. [ ] `uv add watchfiles` para declararlo explícitamente

---

### ~~4.5 · `bot/state.py:325` — lazy import de `timedelta`~~ ✅ RESUELTO

Import movido a nivel de módulo en `bot/state.py:11`.

---

### ~~4.6 · Alias legacy `call_groq_tools` en `tool_caller.py`~~ ✅ RESUELTO (2026-05-05)

Alias eliminado de `tool_caller.py`. 3 callers migrados: `homework/tools.py`, `attendance/tools.py`, `query/tools.py`.

---

## Fase 5 — Código muerto

### 5.1 · Eliminar funciones nunca invocadas

**Pasos**:
1. [x] `bot/attendance_handler.py` — `start_attendance()` eliminado (2026-05-05, cero callers)
2. ~~`cli/dispatcher.py:154` — `_start_gateway()`~~ NO EXISTE — ya fue eliminado o nunca existió
3. ~~`db/connection.py` — `get_session()`~~ NO ESTÁ MUERTO — usado por 10+ routers FastAPI (la auditoría estaba equivocada)

---

### ~~5.2 · Entry points `schoolai.channels` sin loader~~ ✅ RESUELTO (2026-05-05)

Entry points eliminados de `pyproject.toml`. Los canales se importan directamente, no vía entry points.

---

## Fase 6 — Seguridad

### 6.1 · Rotar API keys expuestas en `.env`

**Problema**: `.env` con secretos reales puede haberse compartido en logs, debugging, o accidentalmente en git.

**Pasos**:
1. [ ] Verificar que `.env` está en `.gitignore` y nunca fue commiteado: `git log --all -- .env`
2. [ ] Rotar las siguientes keys como precaución:
   - `GROQ_API_KEY`
   - `MISTRAL_API_KEY`
   - `DEEPSEEK_API_KEY`
   - `OPENROUTER_API_KEY`
   - `ZAI_API_KEY`
   - `JWT_SECRET_KEY`
   - Los tres `TELEGRAM_BOT_TOKEN_*` (solo si hubo riesgo de exposición)
3. [ ] Actualizar `.env` con los nuevos valores

---

### 6.2 · `gateway/auth.py:27` — admin sin bypass

**Pasos**:
1. [ ] Agregar bypass de admin igual que `bot/handlers.py:84`:
   ```python
   if str(user_id) == str(settings.admin_telegram_id):
       return
   ```
2. [ ] Mismo fix en `gateway/webhook.py:68`

---

## Fase 7 — Optimizaciones y mejoras menores

### 7.1 · Documentación LLM — única fuente de verdad

**Pasos**:
1. [ ] Decidir: `config.py` es la fuente de verdad para el stack LLM activo
2. [ ] `docs/llm-benchmark.md:26` — corregir `LLM_PLANNER=moonshotai/kimi-k2-instruct` → `groq/openai/gpt-oss-120b`
3. [ ] `docs/architecture/architecture.md` tabla LLM — alinear con `config.py`
4. [ ] Añadir nota en cada doc: "Stack activo siempre en config.py — este doc puede estar desactualizado"

---

### 7.2 · `skills/planner.py:32` — fragmentos de 4 chars descartados

**Pasos**:
1. [ ] Cambiar umbral `len <= 5` a algo más inteligente (ej. `len < 3` o filtrar solo espacios/puntuación)
2. [ ] Añadir test con fragmento `"hoy"` y `"3bt"`

---

### 7.3 · `bot/singleton.py:70` — `open()` sin encoding

**Pasos**:
1. [ ] Agregar `encoding="utf-8"` al `open(..., "w")`

---

### 7.4 · `skills/orchestrator/skill.py:43` — `except Exception` demasiado amplio

**Pasos**:
1. [ ] Cambiar a capturar `(httpx.HTTPError, openai.APIError, asyncio.TimeoutError, ValueError)`
2. [ ] Dejar que `AttributeError`, `TypeError` etc. propaguen para detectar bugs de programación

---

### 7.5 · `gateway/app.py` — falta shutdown del bucket de rate-limit

**Pasos**:
1. [ ] Agregar tarea periódica (o purga inline) para eliminar entradas viejas del dict `_buckets`

---

## Orden de ejecución recomendado

```
Fase 1 (críticos)     → implementar todos antes de cualquier deploy
Fase 2 (medios)       → en paralelo con Fase 3
Fase 3 (docs)         → puede hacerse en cualquier momento, bajo riesgo
Fase 6 (seguridad)    → 6.1 primero si hubo riesgo de exposición de keys
Fase 4.1 (db session) → tarea grande, hacer por módulo
Fases 4.2-4.6, 5, 7   → limpieza incremental
```

---

## Métricas de progreso

> Actualizado 2026-05-05 tras auditoría completa docs vs código.

| Fase | Issues | Estado |
|------|--------|--------|
| 1 — Bugs críticos | 4 | ✅ 4/4 resueltos |
| 2 — Bugs medios | 6 | ✅ 6/6 resueltos (2.3, 2.4, 2.6 confirmados/fijados) |
| 3 — Docs incorrectas | 5 | ✅ 3.1–3.3 resueltos — 3.4 parcial (3/5 docstrings corregidos, 2 pendientes) |
| 4 — Inconsistencias | 6 | ✅ 6/6 resueltos (4.2–4.6 confirmados/fijados) |
| 5 — Código muerto | 2 | ✅ 5.1 resuelto (start_attendance eliminado, _start_gateway no existe, get_session NO está muerto) — 5.2 resuelto (entry points eliminados) |
| 6 — Seguridad | 2 | 6.1 verificar .gitignore (pendiente), 6.2 gateway admin bypass (pendiente) |
| 7 — Optimizaciones | 5 | Pendiente (bajo riesgo) |

### Issues pendientes prioritarios

- **3.4** Docstrings restantes: `skills/llm/client.py:6`, `skills/orchestrator/skill.py:1`
- **3.4** `skills/context/extractor.py:60,77` hardcodea modelo `gemini-3.1-flash-lite-preview` en código
- **6.1** Verificar `.env` nunca fue commiteado, rotar API keys
- **6.2** `gateway/auth.py:27` — admin no tiene bypass
- **7.x** Optimizaciones menores (bajo riesgo)
