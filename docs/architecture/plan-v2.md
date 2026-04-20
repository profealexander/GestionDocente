# SchoolAI v2 — Arquitectura Hub-and-Spoke

**Estado:** Implementado (Fases 1–4 completas)
**Rama:** `refactor/v2-hub-spoke`
**Directorio:** `/home/edwin8600/schoolai2/`

---

## Contexto

El sistema v1 funciona en producción pero tiene problemas estructurales:

- El LLM decide qué función llamar por nombre libre → hallucination de tools
- Razonamiento y ejecución mezclados en el mismo agente → difícil de mantener
- 3 bots con lógica duplicada → sin punto de entrada único
- Router basado en regex → frágil, no escala semánticamente
- Latencia variable (3 LLM calls encadenados = 15-20s en peor caso)

---

## Arquitectura

```
┌─────────────────────────────────────────────────────┐
│  CANALES DE ENTRADA                                  │
│  Telegram Bot │ SvelteKit Web │ CLI │ Webhook        │
└──────────────────────┬──────────────────────────────┘
                       │ mensaje crudo
┌──────────────────────▼──────────────────────────────┐
│  GATEWAY (FastAPI — puerto 8001)                     │
│  POST /gateway/message   → HTTP (CLI, Web)           │
│  WS   /gateway/ws/{uid}  → WebSocket (SvelteKit)     │
│  POST /gateway/telegram/{token} → Webhook Telegram   │
│  Auth + Rate Limiting (20 msg/60s por usuario)       │
│  Session Manager (sha256 user+canal+día)             │
│  Message Normalizer → TaskSpec (LLM: llm_router)     │
└──────────────────────┬──────────────────────────────┘
                       │ TaskSpec
┌──────────────────────▼──────────────────────────────┐
│  AGENT RUNTIME                                       │
│  ├── Agent Loop       ciclo principal + timing       │
│  ├── Router           Python puro → DomainController │
│  ├── Planner          LLM call #1 → [{tool, params}] │
│  ├── Executor         Python puro → ejecuta steps    │
│  ├── Synthesizer      LLM call #2 → respuesta final  │
│  └── Context Engine   historial RAM (10 turnos)      │
└──────────────────────┬──────────────────────────────┘
                       │ acciones
┌──────────────────────▼──────────────────────────────┐
│  DOMAIN CONTROLLERS                                  │
│  AttendanceController  │ HomeworkController           │
│  CuotasController      │ ReportsController            │
│  GeneralController                                   │
└──────────────────────┬──────────────────────────────┘
                       │ reusan sin modificar
┌──────────────────────▼──────────────────────────────┐
│  SKILLS / _TOOLS/ (v1 — sin cambios)                 │
│  attendance/ │ homework/ │ cuotas/ │ reports/        │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────┐
│  PERSISTENCIA                                        │
│  PostgreSQL schoolai_v2 (clon de schoolai)           │
│  Archivos locales (PDFs temporales en /tmp)          │
└─────────────────────────────────────────────────────┘
```

---

## Decisiones de Arquitectura

| Componente | Decisión | Razón |
|---|---|---|
| Bot framework | python-telegram-bot se mantiene | aiogram = fase futura |
| Frontend | SvelteKit — nueva página `/agente` | WebSocket nativo |
| Agent Loop | Custom Planner+Executor | LangGraph = over-engineering |
| Vector DB | PGVector (pendiente activar) | PostgreSQL ya existe |
| Redis | Fase futura | sesiones en RAM aceptables |
| PDF | fpdf2 (ya instalado en v1) | sin dependencias nuevas |
| Scheduler | APScheduler 3.x AsyncIOScheduler | independiente de PTB |

---

## TaskSpec — contrato Gateway → Agent Runtime

```python
class TaskSpec(BaseModel):
    channel: Literal["telegram", "web", "cli", "cron"]
    domain: Literal["attendance", "homework", "cuotas", "reports", "web_search", "general"]
    intent: Literal["query", "record", "delete", "search", "chat"]
    entities: list[str]
    raw_text: str
    user_id: str
    session_id: str
```

---

## Domain Controllers implementados

| Controller | Tools | Delega a |
|---|---|---|
| AttendanceController | record_attendance, query_attendance, list_courses | `_tools/attendance.py` |
| HomeworkController | create_assignment, query_assignments, delete_assignment | `_tools/homework.py` |
| CuotasController | list_activities, activity_status, register_payment | `_tools/cuotas.py` |
| ReportsController | attendance_pdf, homework_pdf | `_tools/reports.py` |
| GeneralController | list_courses | `_tools/courses.py` |

---

## Estructura de Archivos

```
src/schoolai/
├── gateway/
│   ├── app.py           FastAPI — HTTP + WebSocket + Webhook endpoints
│   ├── normalizer.py    MessageSpec → TaskSpec
│   ├── router.py        LLM classifier (llm_router = gemini-flash-lite)
│   ├── auth.py          check_auth + rate limit (20 msg/60s, RAM)
│   ├── session.py       session_id sha256 por user+canal+día
│   ├── webhook.py       Telegram webhook handler + reply via Bot API
│   ├── runner.py        uvicorn en puerto 8001 (schoolai-gateway)
│   └── schemas.py       TaskSpec, MessageSpec, ResponseSpec
│
├── agent/
│   ├── loop.py          ciclo principal con timing y logs
│   ├── orchestrator.py  Router Python puro: domain → DomainController
│   ├── planner.py       LLM #1 (llm_orchestrator/kimi-k2) → plan JSON
│   ├── executor.py      Python puro — ejecuta steps, captura errores
│   ├── synthesizer.py   LLM #2 (llm_router/gemini-flash) → respuesta ES
│   ├── context.py       Context Engine RAM, 10 turnos/sesión
│   ├── schemas.py       PlanStep, ActionResult, AgentContext, AgentResponse
│   └── domains/
│       ├── base.py          BaseDomainController (ABC)
│       ├── attendance.py    AttendanceController
│       ├── homework.py      HomeworkController
│       ├── cuotas.py        CuotasController
│       ├── reports.py       ReportsController
│       └── general.py       GeneralController (fallback)
│
├── cli/
│   └── main.py          CLI interactivo con rich — chat HTTP al gateway
│
└── skills/
    ├── autonomy/
    │   ├── scheduler.py     AsyncIOScheduler singleton
    │   ├── bot_registry.py  Registry bot → APScheduler jobs
    │   └── jobs.py          register_jobs(bot) — reminders c/5min
    │
    ├── reports/
    │   ├── _pdf.py          Helpers compartidos: init_pdf, safe, footer
    │   ├── attendance.py    generate_attendance_pdf(AttendanceData) → bytes
    │   └── homework.py      generate_homework_pdf(HomeworkData) → bytes
    │
    └── orchestrator/
        └── _tools/
            └── reports.py   _report_attendance_pdf, _report_homework_pdf

ui/                          SvelteKit (copiado de ~/schoolaiUI)
├── src/lib/api/gateway.ts   GatewaySocket — WebSocket con auto-reconnect
└── src/routes/agente/       Chat UI tiempo real — burbujas, typing, tags
```

---

## Fases de Implementación

### Fase 1 — Gateway Hub Central ✅
Punto de entrada único. Message Normalizer → `TaskSpec`. Flag `GATEWAY_ENABLED` para correr en paralelo con v1.
**Entregable:** Gateway recibe mensaje y produce `TaskSpec` válido.

### Fase 2 — Agent Runtime ✅
Loop → Router → Planner (LLM#1) → Executor → Synthesizer (LLM#2). 2 LLM calls fijos, sin hallucination.
**Entregable:** respuesta <6s, domain controllers con firmas verificadas contra `_tools/`.

### Fase 3 — Skills Expansion ✅
APScheduler reemplaza PTB job_queue para reminders. Reports PDF con fpdf2 (attendance + homework).
**Entregable:** APScheduler activo; PDFs generados correctamente.

### Fase 4 — Canales Adicionales ✅
WebSocket (`ws://localhost:8001/gateway/ws/{user_id}`), CLI con rich, Webhooks Telegram.
**Entregable:** SvelteKit recibe respuesta vía WebSocket en tiempo real.

---

## Cómo Arrancar v2

```bash
cd ~/schoolai2

# Backend
uv run schoolai-gateway          # Gateway en puerto 8001

# Frontend
cd ui && npm run dev             # SvelteKit en puerto 5173

# CLI
uv run schoolai-cli              # Chat interactivo en terminal
```

**Variables de entorno relevantes:**
```
GATEWAY_ENABLED=false    # true → bots Telegram también normalizan via gateway
DATABASE_URL=postgresql+asyncpg://schoolai:1234@localhost:5432/schoolai_v2
VITE_GATEWAY_URL=http://localhost:8001
VITE_GATEWAY_WS=ws://localhost:8001
```

---

## Calidad de Código

- **ruff**: 0 errores
- **pylint**: 9.98/10

---

## Qué No Cambia

| Componente | Estado |
|---|---|
| PostgreSQL + SQLAlchemy | Sin cambios |
| `_tools/` existentes | Reutilizados directamente por el Executor |
| LLM providers (groq, google, moonshot) | Sin cambios |
| python-telegram-bot | Sin cambios (v1 en producción) |

---

## Implementaciones Futuras

- **Redis** — sesiones persistentes + pub/sub; requiere plan de failover
- **PGVector** — memoria semántica activando extensión en schoolai_v2
- **Google Classroom API** — `skills/integrations/`
- **aiogram** — migración bot framework para mejor async
- **MinIO** — almacenamiento distribuido (multi-tenant)
