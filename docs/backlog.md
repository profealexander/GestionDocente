# SchoolAI — Backlog

**Última actualización:** 2026-04-24  
**Rama activa:** `refactor/v2-hub-spoke` en `/home/edwin8600/schoolai2/`

---

## Estado actual v2 ✅

| Fase | Estado |
|---|---|
| Fase 1 — Gateway FastAPI (puerto 8001): HTTP + WebSocket + Telegram webhook | ✅ |
| Fase 2 — Agent Runtime: Loop → Classifier → Planner → Executor → Synthesizer | ✅ |
| Fase 3 — Skills Expansion: APScheduler reminders, PDFs fpdf2 | ✅ |
| Fase 4 — Canales: CLI, WebSocket SvelteKit, webhook Telegram | ✅ |

---

## Deuda técnica

### Urgente
_(ninguno — todos resueltos en audit 2026-04-24)_

### Menor
- [ ] Tests básicos — fuzzy matcher, dispatcher, gateway router
- [ ] `_pending_pago` en RAM → migrar a Redis (StateStore sin `use_redis=True`)

### Resuelto ✅
- ~~Persistencia Jornada~~ — `use_redis=True` implementado en `bot/state.py`
- ~~Batch inserts asistencia~~ — ya usa `insert(Attendance), [list_of_dicts]`
- ~~Bloqueo fin de semana~~ — hay fallback a viernes
- ~~`_on_absent_day_reason` sin fallback de fin de semana~~ — corregido (2026-04-24)
- ~~`permissions.py` retorna `"teacher"` para usuarios sin perfil~~ — corregido (2026-04-24)
- ~~Race condition `MAX(sequence_num)` en homework~~ — `pg_advisory_xact_lock` (2026-04-24)
- ~~32 archivos con `async_session()` sin auto-rollback~~ — migrados a `get_db_session()` (2026-04-24)

---

## Benchmark LLM

- [ ] Correr `--models ollama` para `qwen3-coder:480b-cloud` (variantes medium/low/off)
- [ ] Pool `google` excluido (colgaba en Gemma 4 26B) — reinvestigar
- [ ] Lanzar con `--runs 3` para estadísticas más robustas

JSON vigente: `scripts/benchmark-schoolai-20260423-200745.json` (56 modelos, 3301 resultados)

---

## Roadmap

### FASE 0 — CLI profesional

Inspirado en `ollama` y OpenClaw. UX: escribir `schoolai` sin args abre un selector interactivo con flechas ↑↓. También funciona escribiendo subcomandos directamente.

**Stack:** Typer + questionary (o prompt_toolkit) para el selector interactivo.

Subcomandos objetivo:

| Comando | Descripción |
|---|---|
| `schoolai` | Selector interactivo con flechas |
| `schoolai start` | Arranca el Gateway (puerto 8001) |
| `schoolai api` | Arranca la REST API (puerto 8000) |
| `schoolai cli` | Chat terminal |
| `schoolai bot` | Arranca bot Libre |
| `schoolai status` | Estado en tiempo real de procesos |
| `schoolai doctor` | Chequea DB, env vars, puertos, API keys |
| `schoolai logs [servicio]` | Tail de logs por servicio |
| `schoolai update` | git pull + uv sync |

### FASE 1 — MVP

- [ ] Importación masiva via LLM (PDF/Excel → extrae estudiantes, docentes, representantes)
- [ ] Reusar formatter asistencia en Agent Runtime (v2)

### FASE 2 — PWA completa

- [ ] Pantalla Jornada — vista del día hora por hora
- [ ] Admin Cursos y Docentes

### FASE 3 — Multi-docente

- [ ] WhatsApp como canal completo
- [ ] Permisos por rol (directivo vs docente vs admin)
- [ ] Tests de integración

### FASE 4 — Analítica

- [ ] Dashboard asistencia histórica
- [ ] Alertas automáticas (N faltas → notifica representantes)
- [ ] Exportaciones consolidadas

### FASE 5 — Servidor propio

- [ ] Migrar a VPS propio (Vultr Miami ~$18-24/mes)
- [ ] Tenant isolation, panel SaaS

---

## Implementaciones futuras anotadas

- **Redis** — sesiones persistentes + pub/sub (requiere plan de failover)
- **PGVector** — memoria semántica sobre PostgreSQL existente
- **aiogram** — migración bot framework para mejor async
- **MinIO** — almacenamiento distribuido (multi-tenant)
- **Google Classroom API** — integración con `skills/integrations/`
