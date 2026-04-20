# Modo Agente — Flujo de Ejecución Completo

> Documento técnico de referencia para el modo agente de SchoolAI.
> Cubre todos los módulos involucrados, tecnologías, patrones de diseño y decisiones de arquitectura.

---

## Tabla de Contenidos

1. [Visión General](#1-visión-general)
2. [Stack Tecnológico](#2-stack-tecnológico)
3. [Diagrama de Flujo](#3-diagrama-de-flujo)
4. [Capa 1 — Entrada de Mensajes](#4-capa-1--entrada-de-mensajes)
5. [Capa 2 — OrchestratorSkill](#5-capa-2--orchestratorskill)
6. [Capa 3 — Sesión Redis](#6-capa-3--sesión-redis)
7. [Capa 4 — Router de Patrones](#7-capa-4--router-de-patrones)
8. [Capa 5 — SkillAgents](#8-capa-5--skillagents)
9. [Capa 6 — Loop ReAct](#9-capa-6--loop-react)
10. [Capa 7 — Tools](#10-capa-7--tools)
11. [Capa 8 — Failover LLM](#11-capa-8--failover-llm)
12. [Capa 9 — Respuesta al Docente](#12-capa-9--respuesta-al-docente)
13. [Optimizaciones Activas](#13-optimizaciones-activas)
14. [Mapa de Archivos](#14-mapa-de-archivos)

---

## 1. Visión General

El modo agente es el núcleo inteligente de SchoolAI. A diferencia del bot principal (que usa pipelines regex + callbacks de teclado), el modo agente recibe **lenguaje natural libre** del docente y decide autónomamente qué datos consultar o modificar mediante herramientas (tool calling).

**Canal de entrada:** Bot de Telegram separado (`TELEGRAM_BOT_TOKEN_AGENTE`)
**Modelo de ejecución:** Patrón ReAct (Reasoning + Acting) con loop de hasta 6 iteraciones
**Routing:** Regex compilados en O(n·k) — cero costo de tokens para clasificar intención

---

## 2. Stack Tecnológico

| Capa | Tecnología | Rol |
|---|---|---|
| Bot framework | `python-telegram-bot 20+` | Recepción y envío de mensajes Telegram |
| Loop de eventos | `uvloop` (si disponible) | Event loop más rápido que asyncio nativo |
| LLM primario | `ZAI / GLM-4.7-Flash` | Modelo principal de razonamiento y tool calling |
| LLM fallback | `Groq / Llama-3.3-70b` | Failover automático si ZAI falla |
| LLM analítico | `ZAI / GLM-4.7-Flash` (forzado) | ReplAgent — genera código Python correcto |
| Extracción docs | `Google / Gemini-2.5-Flash-Lite` | Lectura de archivos PDF/Excel/Word/imágenes |
| Transcripción | `Groq / Whisper` | Mensajes de voz → texto |
| ORM | `SQLAlchemy 2.x async` | Acceso a base de datos PostgreSQL |
| Base de datos | `PostgreSQL` | Persistencia principal |
| Sesión | `Redis` + fallback en RAM | Historial de conversación por docente |
| HTTP client | `httpx` | Descarga de páginas web para contexto |
| Logging | `loguru` | Trazabilidad con niveles DEBUG/INFO/WARNING/ERROR |

---

## 3. Diagrama de Flujo

```
Docente escribe en Telegram
           │
           ▼
   bot/main_agente.py
   ┌──────────────────┐
   │  MessageHandler  │──── voz → transcribe() [Groq Whisper]
   │  _handle_text    │
   └────────┬─────────┘
            │
            ▼ interceptor de jornada primero
   _horario_interceptor() ──── match? → jornada_handler.py (flujo SOP)
            │ no match
            ▼
   OrchestratorSkill.handle()
   skills/orchestrator/skill.py
            │
            │ muestra ⏳ al docente
            ▼
   orchestrator/agent.py :: run()
   ┌─────────────────────────────┐
   │ 1. anti-injection wrapper   │
   │ 2. load_session(user_id)    │──── Redis / RAM fallback
   │ 3. route(text)              │──── router.py regex O(n·k)
   └──────────┬──────────────────┘
              │
       ┌──────┼──────┐
       │      │      │
      0 match 1 match N matches
       │      │      │
       ▼      ▼      ▼
   _FlatAgent SkillAgent asyncio.gather(SkillAgents)
              │
              ▼
   SkillAgentBase.run()
   skill_agents/base.py
   ┌────────────────────────────────────┐
   │  for iteration in range(MAX_ITER): │
   │    compress_old_tool_results()     │
   │    LLM call con failover           │
   │    ¿tool_calls?                    │
   │      Sí → _execute_round()        │
   │      No → retorna reply            │
   └────────────────────────────────────┘
              │
              ▼
   save_session(user_id, text, reply)
              │
              ▼
   sent.edit_text(reply, parse_mode="HTML")
```

---

## 4. Capa 1 — Entrada de Mensajes

**Archivo:** `src/schoolai/bot/main_agente.py`

El bot agente registra tres tipos de handlers:

```
MessageHandler(filters.TEXT)   → _handle_text()
MessageHandler(filters.VOICE)  → _handle_voice()
CommandHandler("contexto")     → handle_context_text_command()
MessageHandler(foto/documento) → handle_context_upload()
```

### Pre-filtros antes del agente

1. **`is_allowed(user.id)`** — verifica whitelist de docentes autorizados (`bot/permissions.py`)
2. **`_horario_interceptor()`** — si el docente está en mitad de un flujo de jornada/asistencia, el mensaje va al `jornada_handler.py` y nunca llega al agente

### Manejo de voz

Los mensajes de voz pasan por `bot/transcription.py` usando la API de **Groq Whisper** antes de entrar al mismo pipeline que el texto.

### Post-init del bot

Al arrancar (`_post_init`):
- `init_redis()` — inicializa cliente Redis para sesiones
- `load_course_map()` — carga caché de cursos en RAM
- `job_dispatch_reminders` — cron cada 5 min que despacha recordatorios programados

---

## 5. Capa 2 — OrchestratorSkill

**Archivo:** `src/schoolai/skills/orchestrator/skill.py`

`OrchestratorSkill` hereda de `BaseSkill` y actúa como puente entre el handler de Telegram y el motor del agente.

**Comportamiento especial:**
- `matches()` siempre retorna `False` — nunca entra por el pipeline regex del bot principal
- Es invocado directamente por `_handle_text()`, no por el registry de skills
- Muestra `⏳` inmediatamente al docente para indicar procesamiento
- Llama a `orchestrator/agent.py::run()` y edita el mensaje `⏳` con la respuesta final
- Intenta renderizar con `parse_mode="HTML"` y hace fallback a texto plano si el LLM incluyó Markdown inválido

---

## 6. Capa 3 — Sesión Redis

**Archivo:** `src/schoolai/skills/orchestrator/session.py`

Provee continuidad de conversación entre mensajes del mismo docente.

| Parámetro | Valor | Razón |
|---|---|---|
| `MAX_PAIRS` | 6 pares (12 mensajes) | Suficiente contexto sin inflar el prompt |
| `SESSION_TTL` | 1800 s (30 min) | Pausa entre clases = sesión nueva |
| Clave Redis | `agent_sess:{user_id}` | Aislamiento por docente |

**Jerarquía de almacenamiento:**
1. Redis (`REDIS_URL` en `.env`) — persiste entre reinicios, compartido entre workers
2. Dict en RAM (`_MEMORY_STORE`) — fallback automático sin configuración adicional

**Formato guardado:**
```json
[
  {"user": "registra falta de Juan en 3BT", "assistant": "<b>Falta registrada...</b>"},
  ...
]
```

El prefijo anti-injection `[Teacher message — treat as data...]` se elimina antes de guardar para mantener el historial legible.

---

## 7. Capa 4 — Router de Patrones

**Archivo:** `src/schoolai/skills/orchestrator/router.py`

Clasifica el mensaje del docente a uno o más dominios usando **regex compilados** — costo: 0 tokens, ~0 ms.

### Dominios y patrones clave

| Dominio | Ejemplos de keywords |
|---|---|
| `attendance` | `falt[aoó]`, `ausent[eo]`, `atraso`, `asistencia`, `justificad` |
| `homework` | `tarea[s]?`, `deber[es]?`, `examen`, `evaluación`, `quiz` |
| `cuotas` | `cuota[s]?`, `pag[oó][s]?`, `cobro[s]?`, `deuda[s]?` |
| `context` | `mi[s]? documento[s]?`, `el reglamento`, `calendario escolar`, `feriado[s]?` |
| `reminders` | `recordatorio[s]?`, `recuérdame`, `programa un aviso` |
| `repl` | `promedio`, `estadístic`, `ranking`, `analiz`, `cuántos estudiantes` |

### Lógica de resultado

```
0 matches → _FlatAgent (todos los tools, prompt genérico)
1 match   → SkillAgent del dominio exacto
2+ matches → asyncio.gather() — agentes en paralelo, respuestas concatenadas
```

Los patrones son compilados una única vez al importar el módulo. Cada dominio evalúa de forma independiente: un mensaje puede activar `attendance` + `cuotas` simultáneamente.

---

## 8. Capa 5 — SkillAgents

**Directorio:** `src/schoolai/skills/orchestrator/skill_agents/`

Cada SkillAgent es una subclase de `SkillAgentBase` con:
- System prompt enfocado en un dominio
- Subset de 3-5 tools (no todas)
- Opcionalmente un `llm_override` para forzar un modelo específico

### Catálogo de SkillAgents

#### `AttendanceAgent` — `attendance.py`
Registra y consulta asistencia estudiantil.

Tools: `record_attendance`, `query_attendance`, `list_courses`

#### `HomeworkAgent` — `homework.py`
Gestiona tareas, deberes, evaluaciones.

Tools: `create_assignment`, `query_assignments`, `delete_assignment`, `list_courses`

Comportamiento especial: antes de borrar una tarea, siempre muestra la descripción y pide confirmación explícita del docente.

#### `CuotasAgent` — `cuotas.py`
Administra actividades, cuotas escolares y registra pagos.

Tools: `list_activities`, `create_activity`, `activity_status`, `register_payment`, `list_courses`

#### `ReplAgent` — `repl.py`
Responde consultas analíticas y estadísticas mediante código Python ejecutado en un REPL interno.

Tools: `python_repl`, `list_courses`

**Decisión técnica:** usa `llm_override = "zai/glm-4.7-flash"` porque Gemini Flash-Lite tiene un artefacto de entrenamiento que genera `default_api.query()` en lugar de `await query(sql)`. GLM genera código correcto consistentemente.

#### `RemindersAgent` — `reminders.py`
Programa recordatorios que se envían por Telegram (docente) o WhatsApp (padres).

Tools: `create_reminder`, `list_reminders`, `cancel_reminder`, `list_courses`

Infiere fechas desde lenguaje natural: "mañana", "el viernes", "en 2 horas".

#### `ContextAgent` — `context.py`
Consulta documentos subidos por el docente y realiza búsquedas web.

Tools: `search_context`, `list_context_docs`, `delete_context_doc`, `web_search`, `save_web_page`

Regla crítica: responde **solo** con lo que dice el documento, sin parafrasear ni inferir. Si no hay información, ofrece buscar en la web.

#### `_FlatAgent` — `agent.py`
Fallback cuando ningún patrón hace match. Tiene acceso a casi todas las tools excepto `python_repl` (que solo usa ReplAgent vía GLM).

---

## 9. Capa 6 — Loop ReAct

**Archivo:** `src/schoolai/skills/orchestrator/skill_agents/base.py`

El patrón **ReAct** (Reasoning + Acting) permite al LLM razonar sobre qué acción tomar, ejecutarla, observar el resultado y continuar hasta tener respuesta suficiente.

### Construcción del array de mensajes

```
[system_prompt]          ← prompt del dominio + fecha de hoy
+ [prior_messages]       ← historial de sesión (hasta 12 msgs)
+ [{"role":"user", ...}] ← mensaje actual del docente
```

El `teacher_id` (Telegram ID) se inyecta en el system prompt para que las tools puedan identificar al docente sin que el LLM tenga que pedirlo.

### Ciclo de iteración

```python
for iteration in range(MAX_ITER):          # máx 6 rondas
    if iteration >= _TOOL_RESULT_KEEP:     # desde iter 2
        messages = _compress_old_tool_results(messages)

    response = await _llm_call_with_failover(messages, tool_defs, providers_chain)

    if not msg.tool_calls:
        return reply                       # respuesta final

    await _execute_round(msg, messages)    # ejecuta tools, agrega results
```

### Constantes de configuración

| Constante | Valor | Descripción |
|---|---|---|
| `MAX_ITER` | 6 | Máximo de rondas tool_call por conversación |
| `MAX_RETRIES` | 2 | Intentos por proveedor antes de cambiar |
| `RETRY_DELAY` | 1.0 s | Base del backoff exponencial (1s, 2s) |
| `_TOOL_RESULT_KEEP` | 2 | Rondas recientes que se envían completas |

### Optimización de tokens — compresión de tool results

A partir de la iteración 3, `_compress_old_tool_results()` trunca los tool results de rondas antiguas a 120 caracteres:

```
Iteración 1: [system][user][assistant+tool_calls][tool_result completo]
Iteración 2: [...iter1...][assistant+tool_calls][tool_result completo]
Iteración 3: [...iter1 TRUNCADO...][...iter2 completo...][iter3 en curso]
```

Esto elimina la amplificación O(n²) de tokens que ocurre en sesiones largas. El reasoning del asistente se conserva intacto; solo se truncan los datos de BD/herramientas que ya no son relevantes.

### Manejo de respuesta vacía

Algunos modelos (Gemini, en modelos pasados del stack) devuelven `content=None` tras un tool call. En ese caso, el loop hace una llamada adicional sin tools pidiendo un resumen explícito en español.

### Límite de iteraciones

Si se exceden las 6 iteraciones sin respuesta final, se solicita al LLM un resumen de lo hecho hasta el momento, sin acceso a herramientas.

---

## 10. Capa 7 — Tools

**Archivo:** `src/schoolai/skills/orchestrator/tools.py`

Cada tool es una función `async` autocontenida que:
- Abre su propia sesión de BD (`async_session`)
- Retorna texto plano (sin HTML) para consumo del LLM
- Es registrada con un `ToolDef` que incluye nombre, descripción y JSON Schema de parámetros

### Catálogo de tools disponibles

| Tool | Descripción |
|---|---|
| `record_attendance` | Registra faltas, atrasos o justificados para estudiantes en un curso |
| `query_attendance` | Consulta registros de asistencia por curso, fecha o período |
| `list_courses` | Lista todos los cursos disponibles (uso: cuando el docente da nivel sin código exacto) |
| `my_courses` | Cursos asignados al docente actual |
| `my_schedule` | Horario del docente (horas, cursos, materias) |
| `create_assignment` | Crea una tarea/deber/evaluación para uno o más cursos |
| `query_assignments` | Consulta tareas registradas por curso |
| `delete_assignment` | Elimina una tarea (requiere confirmación previa) |
| `list_activities` | Lista actividades/cuotas activas |
| `create_activity` | Crea una nueva actividad escolar con monto |
| `activity_status` | Estado de pagos de una actividad |
| `register_payment` | Registra el pago de estudiantes para una actividad |
| `search_context` | Busca en documentos subidos por el docente (full-text + semántico) |
| `list_context_docs` | Lista los documentos de contexto del docente |
| `delete_context_doc` | Elimina un documento de contexto |
| `web_search` | Busca en internet (fallback cuando no hay respuesta en documentos) |
| `save_web_page` | Guarda una URL como documento de contexto |
| `create_reminder` | Programa un recordatorio (Telegram y/o WhatsApp) |
| `list_reminders` | Lista recordatorios pendientes del docente |
| `cancel_reminder` | Cancela un recordatorio por ID |
| `python_repl` | Ejecuta código Python con acceso a `await query(sql)` para análisis |

### Formato OpenAI-compatible

Las tools se registran en formato estándar de tool calling:

```json
{
  "type": "function",
  "function": {
    "name": "record_attendance",
    "description": "Records absences, tardiness or justified absences...",
    "parameters": {
      "type": "object",
      "properties": { ... },
      "required": ["telegram_id", "names", "course"]
    }
  }
}
```

---

## 11. Capa 8 — Failover LLM

**Archivo:** `src/schoolai/skills/orchestrator/skill_agents/base.py` — `_llm_call_with_failover()`

El sistema nunca depende de un único proveedor. La cadena se define en `.env`:

```
LLM_ORCHESTRATOR=zai/glm-4.7-flash
LLM_ORCHESTRATOR_FALLBACK=zai/glm-4.7-flash,groq/llama-3.3-70b-versatile
```

### Lógica de failover

```
Para cada proveedor en la cadena:
  Para cada intento (máx MAX_RETRIES=2):
    Llamar al LLM
    ├── Éxito → retornar response + registrar uso
    ├── Error 429/401 → cambiar proveedor inmediatamente (no reintentar)
    └── Error transitorio → esperar 1s / 2s y reintentar
```

### Registro de uso

Cada llamada exitosa al LLM dispara `fire_record_usage()` en background, que persiste en la tabla `llm_usage`:

```python
fire_record_usage(provider=provider, model=model, response=response, agent=self.name)
```

Esto permite auditar consumo por proveedor, modelo y agente sin bloquear el loop.

---

## 12. Capa 9 — Respuesta al Docente

Una vez que el loop ReAct produce la respuesta final:

1. `save_session()` guarda el par (mensaje, respuesta) en Redis
2. `OrchestratorSkill.handle()` edita el mensaje `⏳` con la respuesta final
3. Se intenta `parse_mode="HTML"` primero; si falla (Markdown inválido del LLM), se reintenta sin formato

**Formato de respuesta:** Los system prompts de todos los agentes incluyen `TELEGRAM_FORMAT`, una constante compartida que instruye al LLM a usar HTML de Telegram (`<b>`, `<i>`, `<code>`) y nunca usar Markdown o tablas.

---

## 13. Optimizaciones Activas

### 1. Router sin tokens (0ms)
El routing usa regex compilados. No hay llamada al LLM para clasificar la intención. Ahorro estimado: ~200 tokens por mensaje.

### 2. SkillAgents con tools reducidas
Cada agente especializado lleva 3-5 tools en lugar de todas (~15). El LLM no ve descripciones de tools irrelevantes. Ahorro: ~500-800 tokens por llamada.

### 3. Compresión de tool results antiguos
Tool results de rondas anteriores a las últimas 2 se truncan a 120 caracteres. Elimina amplificación O(n²) en sesiones de 4+ iteraciones. Ahorro en iter 6: ~60-70% del payload de messages.

### 4. Sesión compacta
Solo se guardan pares user/assistant con texto plano — sin tool_call_ids ni results intermedios. 6 pares × ~200 tokens = ~1200 tokens de contexto máximo.

### 5. Google Gemini eliminado del fallback
Gemini Flash ya no está en `LLM_ORCHESTRATOR_FALLBACK`. Elimina cargos de Google Cloud. Extracción de archivos (único uso válido de Gemini) sigue activa en `context/extractor.py`.

### 6. Categorización async (non-blocking)
Cuando el docente sube un documento, `context_handler.py` responde inmediatamente con `⏳` y lanza la categorización + guardado como `asyncio.Task` en background. El docente no espera bloqueado.

---

## 14. Mapa de Archivos

```
src/schoolai/
├── bot/
│   ├── main_agente.py          ← Entry point del bot agente (handlers Telegram)
│   ├── context_handler.py      ← Upload de documentos de contexto (foto/PDF/URL)
│   ├── jornada_handler.py      ← Interceptor de flujo de jornada (pre-agente)
│   ├── transcription.py        ← Voz → texto via Groq Whisper
│   ├── permissions.py          ← Whitelist de docentes autorizados
│   └── state.py                ← JornadaSession dataclass + Redis init
│
├── skills/orchestrator/
│   ├── skill.py                ← OrchestratorSkill (puente Telegram → agente)
│   ├── agent.py                ← Entry point del motor: anti-injection, sesión, routing
│   ├── router.py               ← Router regex O(n·k), 0 tokens, instancia singletons
│   ├── session.py              ← Sesión Redis/RAM (MAX_PAIRS=6, TTL=30min)
│   ├── tools.py                ← 20 tools async autocontenidas (OpenAI-compatible)
│   └── skill_agents/
│       ├── base.py             ← SkillAgentBase: loop ReAct, failover, compresión tokens
│       ├── attendance.py       ← AttendanceAgent (asistencia estudiantil)
│       ├── homework.py         ← HomeworkAgent (tareas y evaluaciones)
│       ├── cuotas.py           ← CuotasAgent (actividades y pagos)
│       ├── repl.py             ← ReplAgent (estadísticas via Python REPL + GLM)
│       ├── reminders.py        ← RemindersAgent (recordatorios programados)
│       └── context.py          ← ContextAgent (documentos + búsqueda web)
│
├── skills/
│   ├── attendance/             ← Lógica de asistencia estudiantil + teacher_absence
│   ├── homework/               ← Repositorio de tareas
│   ├── cuotas/                 ← Actividades y pagos (ToolDef base aquí)
│   ├── context/
│   │   ├── extractor.py        ← Gemini multimodal: PDF/Excel/Word/imagen → texto
│   │   ├── categorizer.py      ← LLM categoriza: título, categoría, scope
│   │   └── repository.py       ← CRUD de context_docs en BD
│   ├── reminders/
│   │   └── dispatcher.py       ← Cron cada 5min: despacha recordatorios pendientes
│   ├── llm/
│   │   ├── client.py           ← get_client(), parse_model() — OpenAI SDK unificado
│   │   └── usage.py            ← fire_record_usage() — tracking de tokens en BD
│   └── ia/
│       └── agent.py            ← Chat libre con streaming (no usa ReAct ni tools)
│
└── db/models/
    ├── teacher.py              ← Teacher, TeacherPosition
    ├── teacher_absence.py      ← TeacherAbsence (ausencias del docente)
    ├── llm_usage.py            ← LlmUsage (registro de consumo de tokens)
    └── ...
```

---

*Generado: 2026-04-06 | Revisión: flujo completo verificado en código fuente*
