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

# Services (systemd user units via wrapper)
./sai.sh [start|stop|restart|enable|disable|status|backup|logs [api|bot|jornada|agente]]

# Entry points (direct run without systemd)
uv run schoolai-api
uv run schoolai-bot
uv run schoolai-bot-jornada
uv run schoolai-bot-agente
```


## Architecture

### Three processes, one codebase

| Process | Entry point | Purpose |
|---|---|---|
| `schoolai-api` | `schoolai.api.runner:run` | FastAPI REST API (uvicorn) |
| `schoolai-bot` | `schoolai.bot.main:run` | Telegram bot "Libre" (teachers) |
| `schoolai-bot-jornada` | `schoolai.bot.main_dev:run_dev` | Telegram bot "Jornada" (school-day view) |
| `schoolai-bot-agente` | `schoolai.bot.main_agente:run_agente` | Telegram bot "Agente" (LLM orchestrator) |

PostgreSQL runs in Docker container `schoolai-db`. Nightly backup at 02:00 via `backup.sh` + systemd timer.

### Message dispatch pipeline (Libre / Jornada bots)

```
incoming message
  → text_interceptors.run()      # priority queue: jornada_absent_other(5), horario(8), edit_flow(10)
  → registry.detect_all()        # all skills where matches()==True, sorted by priority
      AttendanceEditSkill  p=8
      AttendanceSkill      p=10
      HomeworkSkill        p=20
      QuerySkill           p=30
      ...
      OrchestratorSkill    p=90  # explicit fallback, matches()==False always
      ChatSkill            p=100 # last resort
```

Each skill's `handle()` is called independently. Text interceptors run first and can short-circuit the pipeline by returning `True`.

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
- Fuzzy name matching in `skills/attendance/matcher.py` uses `SequenceMatcher` with `SIMILARITY_THRESHOLD = 0.75`.
- `normalize()` in `skills/utils/text.py` — NFKD + uppercase + strip accents, LRU-cached. Used throughout for all comparisons.

### Jornada mode state machine

`JornadaSession` is stored per-user in `StateStore` (`bot/state.py`). States: `waiting → active → paused → done`. The session carries `grade_id`, `grade_name`, `subject_id`, `subject_name` when `status == "active"`, and `current_period` when `status == "waiting"`. Both are used by `get_jornada_context()` to inject course context into attendance/homework registrations without the teacher naming the course explicitly.

`StateStore` is a two-layer store (RAM + optional Redis). `REDIS_URL` is **not** currently set in `.env` — state lives in RAM only and is lost on process restart.

### Bot packages

- `bot/action/` — Telegram callback/action flow (attendance, homework, selection widgets)
- `bot/jornada/` — Jornada bot: schedule card, helpers, keyboards, notifications
- `bot/channels/` — channel adapters: `TelegramChannel`, `WhatsAppChannel`

### LLM stack (benchmark 2026-04-23)

| Variable | Primary | Fallback 1 | Fallback 2 | Rol |
|---|---|---|---|---|
| `llm_router` | `mistral/mistral-medium-latest` | `deepseek/deepseek-reasoner` | — | Classifier |
| `llm_synthesizer` | `groq/meta-llama/llama-4-scout-17b-16e-instruct` | `ollama/gemini-3-flash-preview:cloud` | `mistral/mistral-small-latest` | Synthesizer |
| `llm_orchestrator` | `groq/openai/gpt-oss-120b` | `ollama/gemini-3-flash-preview:cloud` | `deepseek/deepseek-reasoner` | Planner |

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

### Orchestrator (Bot Agente)

`skills/orchestrator/_tools/` — individual tool modules loaded by `OrchestratorSkill`. Uses GLM-4.7-Flash (Z.AI) with tool calling. Session history stored in Redis (falls back to in-process dict if `REDIS_URL` not set). Fallback provider: Groq llama-3.3-70b-versatile.

### Database sessions

Always use `get_db_session()` from `schoolai.db.connection` — never raw `async_session()`. It handles commit/rollback automatically.

```python
from schoolai.db.connection import get_db_session
async with get_db_session() as db:
    ...
```

PostgreSQL upserts use `sqlalchemy.dialects.postgresql.insert(...).on_conflict_do_update()` — requires a named `UniqueConstraint` on the model.

### API

FastAPI app at `schoolai.api.main:app`. Routers in `src/schoolai/api/routers/` — one file per domain (grades, students, attendance, homework, scores, cuotas, auth, …).

### Frontend

Separate repo at `~/schoolaiUI` (SvelteKit + Svelte 5 runes). API client at `src/lib/api/client.ts`. Domain API wrappers (e.g. `scores.ts`, `grades.ts`) live in `src/lib/api/`.

## Migrations

Name files sequentially: `0012_description.py`. After creating a model add:
1. `UniqueConstraint` / `Index` to `__table_args__` on the model
2. A new alembic revision
3. `uv run alembic upgrade head`
