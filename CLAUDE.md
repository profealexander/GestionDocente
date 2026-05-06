# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Install / sync deps
uv sync

# Lint
uv run ruff check src/schoolai/

# Run tests
uv run pytest

# Run a single test
uv run pytest tests/path/to/test_file.py::test_name

# Migrations
uv run alembic upgrade head
uv run alembic revision --autogenerate -m "description"

# Comando global (disponible desde cualquier ruta)
gestion                      # menú interactivo (sin args)
gestion start                # arrancar todo (API + Gateway + Bots)
gestion stop / status        # detener / estado
gestion api                  # FastAPI REST — port 8000
gestion gateway              # Gateway v2 — port 8001
gestion cli                  # CLI interactiva (requiere gateway)
gestion logs [api|bot|jornada|agente|gateway]
gestion debug [api|gateway|bot|jornada]   # pudb paso a paso
gestion doctor               # diagnóstico: .env, procesos, DB, Redis, endpoints
gestion update               # git pull + uv sync + reinicio opcional

# Gestión systemd (bajo nivel)
./sai.sh [start|stop|restart|enable|disable|status|backup|logs [api|bot|jornada|agente]]
```


## Architecture

### Procesos activos

| Proceso | Entry point | Propósito |
|---|---|---|
| `schoolaiapi` | `schoolai.api.runner:run` | FastAPI REST API (uvicorn, puerto 8000) |
| `schoolai-gateway` | `schoolai.gateway.runner:run` | Gateway v2 Hub Central (uvicorn, puerto 8001) |
| `schoolai-bot` | `schoolai.bot.main:run` | Telegram bot "Libre" — docentes |
| `schoolai-bot-jornada` | `schoolai.bot.main_dev:run_dev` | Telegram bot "Jornada" — vista de jornada escolar |

> `schoolai-bot-agente` es un proceso **legacy v1** (usa OrchestratorSkill directo) — en proceso de sustitución por el Agent Runtime v2 (`GATEWAY_ENABLED=true`).

PostgreSQL runs in Docker container `schoolai-db`. Nightly backup at 02:00 via `backup.sh` + systemd timer.

### v2 — Flujo principal (Gateway + Agent Runtime)

Activo cuando `GATEWAY_ENABLED=true` o vía acceso directo al gateway (web, CLI, webhook):

```
Telegram / Web / CLI
  → Gateway (puerto 8001) — normaliza a TaskSpec via llm_router (classifier)
  → Agent Runtime
      Router     — Python puro: dominio → DomainController
      Planner    — LLM#1 (llm_planner): genera [{tool, params}]
      Executor   — Python puro: ejecuta tools
      Synthesizer — LLM#2 (llm_synthesizer): redacta respuesta en español
  → _tools/ (attendance, homework, cuotas, reports…) → PostgreSQL
```

### v1 — Pipeline de dispatch (bots Libre / Jornada con GATEWAY_ENABLED=false)

```
incoming message
  → text_interceptors.run()      # priority queue (ver lista completa abajo)
  → registry.detect_all()        # skills donde matches()==True, sorted by priority
      AttendanceEditSkill  p=8
      AttendanceSkill      p=10
      HWReportSkill        p=20
      HomeworkSkill        p=30
      CuotaSkill           p=35
      HWEditSkill          p=40
      QuerySkill           p=40
      OrchestratorSkill    p=50  # default
      ChatSkill            p=100  # last resort
```

Each skill's `handle()` is called independently. Text interceptors run first and can short-circuit the pipeline by returning `True`.

Text interceptors activos (orden de prioridad):
- `modo_chat(1)`, `modo_editar(2)`, `jornada_absent_other(5)`
- `horario_natural(8)`, `ausencias_natural(8)`, `hw_edit_text(10)`
- `cuota_edit_text(20)`, `cuota_participante_text(30)`, `cuota_nombre_text(40)`, `cuota_names_text(50)`

### Skill Registry pattern

`src/schoolai/skills/` contains domain skills registered as entry points under `schoolai.skills` in `pyproject.toml`. Each skill extends `BaseSkill` and declares:
- `intent` — canonical name
- `priority` — lower = higher priority in dispatch
- `keywords` / `patterns` — used by `matches()` for fast O(1) detection
- `handle(update, user_id, text)` — async handler

### Attendance extraction pipeline

`AttendanceSkill.handle()` runs three stages in order, stopping at first success:

1. `extract_prefilter(text)` — regex-only, fast. Returns `intent="query"` for messages like "asistencia" or "Faltas de hoy 3BT"; returns `intent="attendance"` for clear registrations; returns `None` for ambiguous input.
2. `extract_fallback(text)` — rule-based fallback using `_ABSENT_RE`, `_JUSTIFIED_RE`, `_LATE_RE`.
3. `llm_fallback(text)` — Groq LLM, only when rules fail.

Key rules in `skills/utils/extract_rules.py`:
- `extract_prefilter` treats a message starting with an att keyword (falta/asistencia) as a **query** only if it also has a period/course token (`hoy`, `3BT`, `bachillerato`, etc.) OR the message is only att keywords. "Falta tatiana" → registration; "Faltas de hoy" → query.
- `_extract_names` strips course codes (`_COURSE_RE`) and verbal course forms (`_COURSE_VERBAL_RE`, e.g. "Primero BT") before splitting candidate names. Tokens in `_ATT_KW` are excluded from name candidates.
- Fuzzy name matching in `skills/attendance/matcher.py` uses `rapidfuzz.fuzz.WRatio` with `SIMILARITY_THRESHOLD = 0.75`.
- `normalize()` in `skills/utils/text.py` — NFKD + uppercase + strip accents, LRU-cached. Used throughout for all comparisons.

### Jornada mode state machine

`JornadaSession` is stored per-user in `StateStore` (`bot/state.py`). States: `waiting → active → paused → done`. The session carries `grade_id`, `grade_name`, `subject_id`, `subject_name` when `status == "active"`, and `current_period` when `status == "waiting"`. Both are used by `get_jornada_context()` to inject course context into attendance/homework registrations without the teacher naming the course explicitly.

`StateStore` is a two-layer store (RAM + optional Redis). When `REDIS_URL` is set, state persists across restarts; otherwise degrades to RAM-only automatically.

### Bot packages

- `bot/action/` — Telegram callback/action flow (attendance, homework, selection widgets)
- `bot/jornada/` — Jornada bot: schedule card, helpers, keyboards, notifications
- `bot/channels/` — channel adapters: `TelegramChannel`, `WhatsAppChannel`

### LLM stack (benchmark 2026-04-23)

| Variable | Primary | Fallback 1 | Fallback 2 | Rol |
|---|---|---|---|---|
| `llm_router` | `mistral/mistral-medium-latest` | `deepseek/deepseek-v4-flash` | — | Classifier (gateway) |
| `llm_planner` | `groq/openai/gpt-oss-120b` | `ollama/gemini-3-flash-preview:cloud` | `deepseek/deepseek-v4-flash` | Planner (agent runtime) |
| `llm_synthesizer` | `groq/meta-llama/llama-4-scout-17b-16e-instruct` | `ollama/gemini-3-flash-preview:cloud` | `mistral/mistral-small-latest` | Synthesizer (agent runtime) |
| `llm_chat` | `groq/compound-beta` | `mistral/mistral-small-latest` | — | Chat libre (v1) |
| `llm_extractor` | `groq/openai/gpt-oss-120b` | `mistral/mistral-medium-latest` | — | Extractor (v1 legacy) |
| `llm_context_agent` | `mistral/mistral-small-latest` | — | — | Context skill agent |

Groq free tier: 20 RPM por modelo — planner y synthesizer usan modelos distintos, cuotas independientes.

### Benchmark LLM

```bash
# Correr benchmark completo (excluye google — cuelga)
uv run python scripts/benchmark_llm.py --models deepseek,groq,hf,kilo,mistral,nvidia,ollama,openrouter,zai,mulerouter

# Solo modelos en uso
uv run python scripts/benchmark_llm.py --inuse

# Ranking
uv run python scripts/rank_llm.py --json scripts/<file>.json
uv run python scripts/rank_llm.py --json scripts/<file>.json --role classifier
uv run python scripts/rank_llm.py --json scripts/<file>.json --role planner
uv run python scripts/rank_llm.py --json scripts/<file>.json --role synthesizer
```

JSON vigente: `scripts/benchmark-schoolai-20260423-200745.json`

### Agent Runtime (v2)

Package: `src/schoolai/agent/`. Entry point: `schoolai-gateway` (puerto 8001). El bot Telegram delega al runtime cuando `GATEWAY_ENABLED=true`.

| Módulo | Rol |
|---|---|
| `agent/loop.py` | Ciclo principal: orquesta Router → Planner → Executor → Synthesizer |
| `agent/orchestrator.py` | Router v2: mapea `task.domain` → `DomainController` (Python puro) |
| `agent/planner.py` | LLM#1: genera `[{tool, params}]` vía `llm_planner` |
| `agent/executor.py` | Ejecuta cada tool step (Python puro) usando módulos de `_tools/` |
| `agent/synthesizer.py` | LLM#2: redacta respuesta final en español vía `llm_synthesizer` |
| `agent/context.py` | Carga y persiste historial de conversación por sesión |
| `agent/domains/` | `DomainController` por dominio: attendance, homework, cuotas, reports, general |

`skills/orchestrator/_tools/` — tool modules reutilizados por el Executor. `skills/orchestrator/skill_agents/` — skill agents legacy usados por el bot-agente v1 (en proceso de sustitución por el Agent Runtime).

### LLM client

All LLM calls go through `skills/llm/client.py`. Use `call_with_fallback` — it tries `primary`, then each comma-separated model in `fallbacks` on 5xx/429, and runs the blocking SDK call in a thread pool:

```python
from schoolai.skills.llm.client import call_with_fallback
from schoolai.config import settings

resp = await call_with_fallback(
    primary=settings.llm_planner,
    fallbacks=settings.llm_planner_fallback,
    messages=[...],
    response_format={"type": "json_object"},
)
```

Model strings are `"provider/model"` (e.g. `"groq/llama-3.1-8b-instant"`). Providers are registered in `skills/llm/providers.py`. Each provider maps to a `settings` attribute for its API key.

### Gateway endpoints (v2)

| Method | Path | Descripción |
|---|---|---|
| `POST` | `/gateway/message` | Canal → Agent Runtime → respuesta |
| `POST` | `/gateway/classify` | Solo clasificación (sin ejecutar el agente) |
| `WS` | `/gateway/ws/{user_id}` | WebSocket para SvelteKit / CLI web |
| `POST` | `/gateway/telegram/{token}` | Telegram webhook |
| `GET` | `/gateway/health` | Health check |

### Key env vars

Critical vars that must be set in `.env`:

| Var | Required | Default |
|---|---|---|
| `DATABASE_URL` | yes | — |
| `TELEGRAM_BOT_TOKEN` | yes | — |
| `JWT_SECRET_KEY` | yes (prod) | — |
| `GATEWAY_ENABLED` | no | `false` |
| `REDIS_URL` | no | RAM-only state |
| `TELEGRAM_ALLOWED_USERS` | no | all users allowed |
| `SCHOOL_TIMEZONE` | no | `America/Guayaquil` |

### Database sessions

Dos patrones según el contexto:

**Dentro de routers FastAPI** — usar `get_session` como dependencia. La sesión no hace auto-commit; el router debe llamar `await session.commit()` explícitamente en los endpoints de escritura:
```python
from schoolai.db.connection import get_session
async def my_endpoint(session: AsyncSession = Depends(get_session)):
    session.add(obj)
    await session.commit()
```

**Fuera de FastAPI** (skills, background tasks, CLI) — usar `get_db_session()`. Hace auto-commit al salir y rollback automático en excepciones. Nunca usar `async_session()` directo:
```python
from schoolai.db.connection import get_db_session
async with get_db_session() as db:
    ...
```

PostgreSQL upserts use `sqlalchemy.dialects.postgresql.insert(...).on_conflict_do_update()` — requires a named `UniqueConstraint` on the model.

### API

FastAPI app at `schoolai.api.main:app`. Routers in `src/schoolai/api/routers/` — one file per domain (grades, students, attendance, homework, scores, cuotas, auth, …).

### Frontend

Subcarpeta `ui/` dentro de este repo (SvelteKit + Svelte 5 runes). API client at `ui/src/lib/api/client.ts`. Domain API wrappers (e.g. `scores.ts`, `grades.ts`, `gateway.ts`) live in `ui/src/lib/api/`.

```bash
cd ui && npm install   # instalar deps frontend
cd ui && npm run dev   # dev server (puerto 5173)
cd ui && npm run build # build producción
```

## Migrations

Name files sequentially: `0015_description.py` (próxima libre). After creating a model add:
1. `UniqueConstraint` / `Index` to `__table_args__` on the model
2. A new alembic revision
3. `uv run alembic upgrade head`

## Homework backend (planificado — NO implementado aún)

> **Estado:** La migración a Google Sheets está planificada pero NO iniciada. Los archivos del patrón Repository aún no existen. Actualmente solo existe `skills/homework/repository.py` (monolítico).

El almacén de tareas será migrado de PostgreSQL a **Google Sheets** como store primario.

**Variables de entorno:**
```
HOMEWORK_BACKEND=db       # default — PostgreSQL (actual)
HOMEWORK_BACKEND=sheets   # nuevo — Google Sheets
GOOGLE_SHEETS_SPREADSHEET_ID=<id>
GOOGLE_SERVICE_ACCOUNT_JSON=<path o JSON inline>
```

**Patrón Repository — NO importar `repository.py` directamente:**
```python
# ✅ correcto
from schoolai.skills.homework.repository_factory import get_homework_repo
repo = get_homework_repo()
hw = await repo.save_homework(session, ...)

# ❌ incorrecto (acoplamiento directo al backend DB)
from schoolai.skills.homework.repository import save_homework
```

Mientras `HOMEWORK_BACKEND=db` (default), el comportamiento es idéntico al actual.
Los archivos del módulo cuando esté implementado:
- `skills/homework/repository_base.py` — ABC con la interfaz
- `skills/homework/repository_db.py` — implementación PostgreSQL (actual `repository.py`)
- `skills/homework/repository_sheets.py` — implementación Google Sheets
- `skills/homework/repository_factory.py` — selecciona backend según settings
