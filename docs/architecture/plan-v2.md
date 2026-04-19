# SchoolAI v2 — Plan de Migración

**Estado:** En planificación  
**Inicio estimado:** Por definir  
**Rama:** `main`

---

## Contexto

El sistema actual (v1) funciona en producción pero tiene problemas estructurales:

- El LLM decide qué función llamar por nombre libre → hallucination de tools
- Razonamiento y ejecución mezclados en el mismo agente → difícil de mantener
- 3 bots con lógica duplicada → sin punto de entrada único
- Router basado en regex → frágil, no escala semánticamente
- Latencia variable (3 LLM calls encadenados = 15-20s en peor caso)

---

## Arquitectura Objetivo

```
┌─────────────────────────────────────────────────────┐
│  CANALES DE ENTRADA                                  │
│  Telegram Bot │ SvelteKit Web │ CLI │ Cron           │
└──────────────────────┬──────────────────────────────┘
                       │ mensaje crudo
┌──────────────────────▼──────────────────────────────┐
│  GATEWAY (FastAPI Hub)                               │
│  Message Normalizer → TaskSpec                       │
│  Auth + Rate Limiting                                │
│  Session Manager                                     │
└──────────────────────┬──────────────────────────────┘
                       │ TaskSpec
┌──────────────────────▼──────────────────────────────┐
│  AGENT RUNTIME                                       │
│  ├── Agent Loop       ciclo principal                │
│  ├── Router           elige Domain Controller        │
│  ├── Planner          LLM → plan [{tool, params}]   │
│  ├── Executor         Python puro, sin LLM           │
│  ├── Synthesizer      LLM → respuesta formateada     │
│  └── Context Engine   historial + memoria            │
└──────────────────────┬──────────────────────────────┘
                       │ acciones
┌──────────────────────▼──────────────────────────────┐
│  DOMAIN TOOLS (Skills)                               │
│  Attendance │ Homework │ Cuotas │ WebSearch          │
│  Reports │ Notifications │ Autonomy │ Integrations   │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────┐
│  PERSISTENCIA                                        │
│  PostgreSQL + PGVector │ Archivos locales            │
└─────────────────────────────────────────────────────┘
```

---

## Decisiones de Arquitectura

| Componente | Decisión | Razón |
|---|---|---|
| Bot framework | python-telegram-bot se mantiene | aiogram = fase futura, migración costosa |
| Frontend | SvelteKit se mantiene | no migrar a React |
| Agent Loop | Custom Planner+Executor | LangGraph = over-engineering para esta escala |
| Vector DB | Solo PGVector | Chroma es redundante, PostgreSQL ya existe |
| Archivos | Sistema local | MinIO = fase futura (relevante en multi-tenant) |
| Redis | Fase futura | sesiones en RAM por ahora son aceptables |
| Skills | Sin plugin system | registro estático por ahora |

---

## Agent Runtime — Detalle

Solo **Planner** y **Synthesizer** llaman al LLM. El resto es Python puro.

```
TaskSpec (del Gateway)
  → Agent Loop
      → Router/Orchestrator     Python puro → selecciona DomainController
      → DomainController        Python puro → prepara tools disponibles (máx 3-4)
      → Planner                 LLM call 1  → [{tool, params}, ...]
      → Executor                Python puro → ejecuta cada step
      → Synthesizer             LLM call 2  → respuesta formateada
  → Response (al Gateway)
```

**Resultado:** 2 LLM calls fijos por respuesta. Sin hallucination. Latencia predecible ~3-5s.

### TaskSpec (contrato Gateway → Agent Runtime)

```python
class TaskSpec(BaseModel):
    channel: Literal["telegram", "web", "cli", "cron"]
    domain: Literal["attendance", "homework", "cuotas", "web_search", "general"]
    intent: Literal["query", "record", "delete", "search", "chat"]
    entities: list[str]
    raw_text: str
    user_id: str
    session_id: str
```

### Domain Controllers

Cada controller tiene máximo 3-4 tools. Reemplazan los `skill_agents/` actuales:

| Controller | Tools |
|---|---|
| AttendanceController | record_attendance, query_attendance, list_courses |
| HomeworkController | create_assignment, query_assignments, delete_assignment |
| CuotasController | register_payment, activity_status, list_activities |
| WebSearchController | web_search, save_web_page |
| GeneralController | my_courses, my_schedule |

---

## Estructura de Archivos Nueva

```
src/schoolai/
├── gateway/
│   ├── app.py           FastAPI app del gateway
│   ├── normalizer.py    mensaje crudo → TaskSpec
│   ├── router.py        Structured Output LLM → domain/intent
│   ├── auth.py          autenticación + rate limiting
│   ├── session.py       manejo de sesión
│   └── schemas.py       TaskSpec, MessageSpec, ResponseSpec
│
├── agent/
│   ├── loop.py          Agent Loop principal
│   ├── orchestrator.py  Router (Python puro)
│   ├── planner.py       LLM → plan JSON
│   ├── executor.py      Python puro, ejecuta plan
│   ├── synthesizer.py   LLM → respuesta final
│   ├── context.py       Context Engine
│   ├── schemas.py       PlanStep, ActionResult, AgentResponse
│   └── domains/
│       ├── base.py
│       ├── attendance.py
│       ├── homework.py
│       ├── cuotas.py
│       ├── web_search.py
│       └── general.py
│
└── skills/              (se mantiene — Executor los llama directamente)
    ├── attendance/
    ├── homework/
    ├── cuotas/
    └── ...
```

---

## Fases de Migración

### Fase 1 — Gateway Hub Central
**Objetivo:** punto de entrada único para todos los canales.

- Crear `src/schoolai/gateway/`
- Message Normalizer convierte Telegram/Web/CLI → `TaskSpec`
- Router con Structured Output reemplaza regex actual
- Auth y Rate Limiting centralizados
- Los 3 bots actuales pasan a ser adaptadores finos (solo reenvían al Gateway)
- Switch con flag en `.env` — Gateway y sistema v1 corren en paralelo

**Entregable:** Gateway recibe mensaje Telegram y produce `TaskSpec` válido.

---

### Fase 2 — Agent Runtime Restructure
**Objetivo:** separar razonamiento de ejecución.

- Crear `src/schoolai/agent/`
- Implementar Agent Loop, Router, Planner, Executor, Synthesizer, Context Engine
- Implementar Domain Controllers (máx 3-4 tools cada uno)
- Reusar `_tools/` existentes en el Executor sin modificarlos
- 2 LLM calls fijos por respuesta

**Entregable:** respuesta en <6s, sin hallucination de tools.

---

### Fase 3 — Skills Expansion
**Objetivo:** nuevas capacidades sobre la base limpia.

- `skills/reports/` — PDF/Excel (base ya existe)
- `skills/notifications/` — Telegram + WhatsApp unificado
- `skills/autonomy/` — APScheduler reemplaza PTB job queue
- `skills/integrations/` — Google Classroom API
- PGVector activado para memoria semántica

**Entregable:** APScheduler corre recordatorios; PDF generado correctamente.

---

### Fase 4 — Canales Adicionales
**Objetivo:** más puntos de entrada sobre el Gateway estable.

- CLI con `rich` + HTTP al Gateway
- SvelteKit conectado al Gateway vía WebSocket (respuestas en tiempo real)
- Webhooks Telegram (reemplaza polling actual)

**Entregable:** Web UI recibe respuesta vía WebSocket en tiempo real.

---

## Qué No Cambia en Ninguna Fase

| Componente | Estado |
|---|---|
| PostgreSQL + SQLAlchemy | Sin cambios |
| SvelteKit frontend | Sin cambios hasta Fase 4 |
| python-telegram-bot | Sin cambios hasta fase futura |
| Sistema de configuración `.env` | Sin cambios |
| `_tools/` existentes | Se reusan directamente en el Executor |
| LLM providers actuales | Sin cambios |

---

## Implementaciones Futuras (anotadas, no planificadas)

- **Redis** — sesiones persistentes + pub/sub para respuestas async; requiere plan de failover
- **aiogram** — migración del bot framework para mejor performance async
- **MinIO** — almacenamiento distribuido (relevante cuando haya multi-tenant / varias escuelas)
- **Plugin system** — registro dinámico de skills como entry points

---

## Criterio de Éxito por Fase

| Fase | Criterio |
|---|---|
| 1 — Gateway | Gateway recibe mensaje Telegram y produce TaskSpec válido |
| 2 — Runtime | Respuesta en <6s con 2 LLM calls, sin hallucination de tools |
| 3 — Skills | APScheduler corre recordatorios; PDF generado correctamente |
| 4 — Canales | SvelteKit recibe respuesta vía WebSocket en tiempo real |
