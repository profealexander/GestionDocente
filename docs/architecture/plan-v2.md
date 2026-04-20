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
│   ├── planner.py       LLM #1 (llm_orchestrator) → plan JSON
│   ├── executor.py      Python puro — ejecuta steps, captura errores
│   ├── synthesizer.py   LLM #2 (llm_router) → respuesta ES
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
├── bot/
│   ├── main.py / main_dev.py / main_agente.py   entrypoints de cada bot
│   ├── singleton.py     PID-file guard — evita Conflict 409 con watchfiles/WSL2
│   ├── startup.py       common_post_init: redis, course_map, cleanup jobs
│   ├── mode.py          modo activo del proceso: "libre" | "jornada"
│   ├── permissions.py   niveles de acceso: superadmin/admin/secretaria/teacher/none
│   ├── gateway_adapter.py  thin adapter GATEWAY_ENABLED=true → normaliza a TaskSpec
│   ├── modo_chat.py     text interceptor p=1: toggle Chat IA por usuario
│   ├── modo_editar.py   text interceptor p=2: toggle Modo Registrar / Modo Editar
│   ├── broadcast_handler.py  comunicados masivos a docentes vía WhatsApp (Green API)
│   ├── query_handler.py helpers de ejecución y formato de consultas
│   ├── handlers.py / text_interceptors.py / callback_router.py
│   ├── state.py / state_store.py   sesión por usuario RAM+Redis
│   ├── action_handler.py / action/  flujos de callback (asistencia, tarea, selección)
│   ├── jornada_handler.py / jornada/  SOP Engine + notificación matutina
│   ├── channels/        TelegramChannel, WhatsAppChannel (BaseChannel ABC)
│   └── …otros handlers: attendance, schedule, position, db, whatsapp, notif, help
│
├── api/
│   ├── main.py / auth.py / schemas.py / runner.py
│   └── routers/
│       ├── auth.py, grades.py, subjects.py, students.py
│       ├── attendance.py, homework.py, cuotas.py
│       ├── scores.py        notas académicas (gradebook)
│       ├── llm_stats.py     uso de LLMs agrupado por proveedor/modelo
│       ├── health.py        GET /health — DB + Redis status
│       ├── dev.py           endpoints de desarrollo
│       └── whatsapp_webhook.py
│
├── db/
│   ├── connection.py    sesión async SQLAlchemy + get_db_session()
│   └── models/
│       ├── grade, student, teacher, person, subject
│       ├── attendance, homework, homework_submission  (seguimiento de entregas)
│       ├── student_score    notas por estudiante/materia/trimestre/columna
│       ├── cuota, reminder, context_document
│       ├── llm_usage        registro de tokens/costo por llamada LLM
│       ├── notification     notificaciones pendientes/enviadas
│       ├── teacher_absence  ausencias de docentes
│       ├── whatsapp_contact número WhatsApp vinculado a teacher/person
│       └── student_representative  representantes (many-to-many con students)
│
└── skills/
    ├── autonomy/        APScheduler singleton + registry de jobs por bot
    ├── reports/         generate_attendance_pdf / generate_homework_pdf (fpdf2)
    ├── documents/
    │   ├── generator.py     Word (docxtpl) + PDF para notificaciones formales
    │   ├── repository.py    CRUD de documentos institucionales
    │   └── notif_repository.py  notificaciones pendientes a representantes
    ├── db/
    │   ├── service.py       insert/upsert de personas (students, teachers)
    │   ├── schedule_service.py  horarios y docentes
    │   ├── schedule_parser.py   parse de cadenas de horario
    │   ├── position_service.py  cargos institucionales
    │   └── deduplicator.py     dedup fuzzy de personas
    ├── orchestrator/
    │   ├── skill.py / agent.py / router.py / repl.py / session.py
    │   ├── _tools/           attendance, homework, cuotas, reports, courses,
    │   │                     context_docs, reminders, repl, teacher, helpers
    │   └── skill_agents/     SkillAgents: attendance, homework, cuotas,
    │                         reminders, context, repl (base ABC)
    ├── attendance/       skill + tools + matcher fuzzy + service + handler_edit
    ├── homework/         skill + tools + detector + repository + handler_edit
    ├── cuotas/           skill + tools + handlers (create/pago/query/edit) + service
    ├── query/            skill + detector + resolver + formatter
    ├── context/          documentos institucionales + búsqueda web (DuckDuckGo)
    ├── reminders/        dispatcher + repository + tools
    ├── ia/               ChatSkill — agente libre (Groq 70B)
    ├── llm/              cliente unificado + tool_caller + providers + usage tracker
    └── utils/            normalize, extract_rules, schema (via_llm), keyboards, dates

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

- **ruff**: 0 errores (verificado 2026-04-20)
- **pylint**: 9.98/10

## LLM Stack activo (2026-04-20)

| Rol | Modelo primario | Fallback chain |
|---|---|---|
| Router (classify) | `google/gemini-3.1-flash-lite-preview` | → `groq/openai/gpt-oss-120b` → `deepseek/deepseek-chat` |
| Orchestrator (planner) | `groq/qwen/qwen3-32b` | → `google/gemini-3.1-flash-lite-preview` → `deepseek/deepseek-chat` → `mistral/mistral-medium-latest` |
| Context agent | `groq/qwen/qwen3-32b` | (usa llm_context_agent, configurable independientemente) |
| Chat | `groq/compound-beta` | → `groq/qwen/qwen3-32b` |
| Extractor | `google/gemini-3.1-flash-lite-preview` | — |

Fallback implementado en `skills/llm/client.py:call_with_fallback()` — maneja 503 y 429 automáticamente.

## Bugs corregidos en smoke test (2026-04-20)

| Bug | Fix |
|---|---|
| `planner.py` — `KeyError` por `{}` del JSON en `.format()` | `.replace("{tools}", tools_desc)` |
| Parser planner — no manejaba objeto único `{"tool":...}` de Qwen3 | Extendido para 3 formatos de respuesta |
| `LLM_ORCHESTRATOR=moonshotai/...` — provider no registrado, caía a Groq | Renombrado a `moonshot/` → reemplazado por `groq/qwen/qwen3-32b` |
| `llm_override` hardcodeado en `context.py` | → `settings.llm_context_agent` |

---

## Qué No Cambia

| Componente | Estado |
|---|---|
| PostgreSQL + SQLAlchemy | Sin cambios |
| `_tools/` existentes | Reutilizados directamente por el Executor |
| LLM providers (groq, google, deepseek, mistral, zai) | Sin cambios |
| python-telegram-bot | Sin cambios (v1 en producción) |

---

## Implementado post-Fase 4

Funcionalidades añadidas tras las fases planificadas:

| Feature | Módulo | Descripción |
|---|---|---|
| Gradebook (notas) | `api/routers/scores.py` + `db/models/student_score.py` | CRUD notas por trimestre/columna |
| LLM usage tracking | `skills/llm/usage.py` + `db/models/llm_usage.py` + `api/routers/llm_stats.py` | Registro tokens/costo por llamada |
| Comunicados masivos | `bot/broadcast_handler.py` | Envío WhatsApp a docentes por nivel/cargo |
| Permisos por rol | `bot/permissions.py` | Niveles: superadmin/admin/secretaria/teacher/none |
| Singleton guard | `bot/singleton.py` | Evita Conflict 409 en WSL2 con watchfiles |
| Modo Chat IA / Modo Editar | `bot/modo_chat.py`, `bot/modo_editar.py` | Toggle de modo de trabajo por usuario |
| Documentos formales | `skills/documents/` | Word (docxtpl) + PDF para notificaciones institucionales |
| Ausencias de docentes | `db/models/teacher_absence.py` | Registro de inasistencia del personal |
| WhatsApp contacts | `db/models/whatsapp_contact.py` | Número WA vinculado a teacher/person |
| Representantes | `db/models/student_representative.py` | Many-to-many students ↔ representantes |
| Health check | `api/routers/health.py` | GET /health — estado DB + Redis |

---

## Implementaciones Futuras

- **Redis** — sesiones persistentes + pub/sub; requiere plan de failover
- **PGVector** — memoria semántica activando extensión en schoolai_v2
- **Google Classroom API** — `skills/integrations/`
- **aiogram** — migración bot framework para mejor async
- **MinIO** — almacenamiento distribuido (multi-tenant)
