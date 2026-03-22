# Arquitectura técnica — SchoolAI

---

## Visión general

SchoolAI tiene dos procesos independientes (bot + API) que comparten PostgreSQL y Redis:

```
┌─────────────────────────────────────────────────────────────────┐
│                        USUARIO (docente)                         │
│                    Telegram (texto o voz)                        │
└────────────────────────────┬────────────────────────────────────┘
                             │ HTTPS polling
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                       BOT (proceso 1)                            │
│  python-telegram-bot 21.x · async · uvloop                      │
│                                                                  │
│  main.py → handlers.py → SkillRegistry → Skill → Tools          │
│                │               │            │        │           │
│           _DbFlowFilter    detect_all()  extractor  service.py   │
│           (estado activo)  + Planner    (regex)    (DB ops)      │
│                                │                                  │
│                         LLM fallback (Groq)                      │
│                         solo si regex falla                      │
│                                                                  │
│  Modo Jornada (bot-dev):                                         │
│    jornada_handler.py · schedule_handler.py · position_handler  │
└──────────────────────────────────┬──────────────────────────────┘
                                   │
              ┌────────────────────┼────────────────────┐
              │                    │                     │
   ┌──────────▼──────────┐  ┌──────▼──────┐   ┌────────▼────────┐
   │   PostgreSQL         │  │   Redis     │   │   Groq API      │
   │   schoolai DB        │  │  (estado    │   │  Whisper (voz)  │
   │                      │  │  RAM+TTL)   │   │  LLM fallback   │
   └──────────┬──────────┘  └─────────────┘   └─────────────────┘
              │
┌─────────────▼───────────────────────────────────────────────────┐
│                       API (proceso 2)                            │
│  FastAPI · Uvicorn · asyncpg · JWT (PyJWT HS256)                 │
│                                                                  │
│  POST /auth/token            ← pública (obtiene JWT)            │
│  GET  /grades  /subjects     ← públicas (catálogos)             │
│  GET  /students              ← protegida (Bearer JWT)           │
│  GET  /homework  PATCH /...  ← protegida                        │
│  GET  /attendance            ← protegida                        │
│  GET/POST /cuotas/...        ← protegida                        │
│                                                                  │
│  Swagger UI: /docs    ReDoc: /redoc                             │
└─────────────────────────────────────────────────────────────────┘
```

---

## Dos modos de bot

| | Modo Libre | Modo Jornada |
|---|---|---|
| Token | `TELEGRAM_BOT_TOKEN` | `TELEGRAM_BOT_TOKEN_DEV` |
| Comando | `schoolai-bot` | `schoolai-bot-dev` |
| Función | Registro libre de asistencia/tareas/cuotas | Guía hora a hora del día escolar |
| Extra | — | `/jornada`, notificación 07:00, contexto automático por período |

---

## Pipeline de un mensaje (Skill Registry)

```
Usuario escribe: "Faltaron Carlos y Pedro de 2bt"
       │
       ▼
bot/main.py — MessageHandler
  _DbFlowFilter: ¿hay estado activo para este user?
  ├── SÍ → _handle_db_or_schedule_text()
  │         (schedule / position / cuota number input)
  └── NO → handle_text() → _dispatch()
       │
       ▼
handlers.py — _dispatch()
  Capas de intercepción:
  1. Jornada triggers (solo modo jornada)
  2. resolve_selection_text() — selección pendiente
  3. handle_wa_setup_text() — setup WhatsApp
  4. handle_cuota_names_text() — input numérico de cuotas
       │
       ▼
skills/registry.py — detect_all(text)
  Itera skills en orden de prioridad:
  1. AttendanceSkill.matches(text)?  ← keywords O(1) + patterns regex
  2. HWReportSkill.matches(text)?
  3. HomeworkSkill.matches(text)?
  4. QuerySkill.matches(text)?
  5. CuotaSkill.matches(text)?
  └── [] vacío → ChatSkill (fallback LLM)
       │
       ├── 1 skill → handle() directo
       └── 2+ skills → Planner (skills/planner.py)
                         split por " y " / ";" / ","
                         asigna fragmento a cada skill
       │
       ▼
skill.handle(update, user_id, text)
  1. extractor regex (<1ms) — extract_prefilter / extract_fallback
  2. LLM fallback (Groq, ~500ms) — solo si regex devuelve None
  3. handle_extraction() → DB → respuesta Telegram
```

---

## Skills registradas

| Orden | Skill | Intent | Detección |
|---|---|---|---|
| 1 | AttendanceSkill | `attendance` | keywords: faltó, atraso, ausente… |
| 2 | HWReportSkill | `homework_report` | keywords: no entregó, cumplimiento… |
| 3 | HomeworkSkill | `homework` | keywords: tarea, deber, examen… |
| 4 | QuerySkill | `query` | trigger explícito + dominio |
| 5 | CuotaSkill | `cuota` | keywords: cuota, actividad, pago… |
| 6 | ChatSkill | `chat` | fallback — siempre al final |

---

## Tools Registry (por skill)

Cada skill expone tools Python puras (sin Telegram) para:
- Ejecución directa desde handlers
- Formato Groq para LLM fallback (`.to_groq()`)
- Reutilización futura en orquestador

```
skills/cuotas/tools.py      create_actividad, list_actividades, register_pago,
                            get_estado_actividad, export_reporte, add_students_from_course

skills/attendance/tools.py  mark_attendance, query_attendance

skills/homework/tools.py    create_homework, report_missing

skills/query/tools.py       query_attendance, query_homework
```

LLM fallback unificado en `skills/llm/tool_caller.py`:
```
texto → Groq (llama-3.1-8b-instant) con tool definitions
      → tool_name + args
      → ExtractionResult / CuotaExtract
```

---

## Flujo Modo Jornada

```
07:00 — job_morning_notify (asyncio.gather — paralelo)
  - busca teachers con horario del día
  - envía mensaje con primer período a cada docente

Docente toca "📅 Jornada" o escribe "j"
  - jornada_handler.py detecta período activo por hora
  - muestra teclado: "Aquí" / "Saltar" / "Pausar"

Docente confirma llegada (Aquí)
  - JornadaSession.status = "active"
  - grade_id + subject_id inyectados en contexto

Docente registra: "Faltó Recalde"
  - _dispatch() detecta jornada activa
  - get_jornada_context() añade grade+subject al extraction
  - sin necesidad de especificar el curso

Al finalizar todos los períodos
  - status = "done"
  - teclado: "Recorrer desde inicio" / "Seleccionar período"
```

---

## Componentes

### Bot (`src/schoolai/bot/`)

| Archivo | Responsabilidad |
|---|---|
| `main.py` | Arranque, registro de handlers/callbacks, post_init |
| `handlers.py` | Entry point texto/voz → `_dispatch()` con capas de intercepción |
| `action_handler.py` | Ruteo por intent, persistencia, respuestas |
| `attendance_handler.py` | Callbacks de asistencia (selección de grado) |
| `jornada_handler.py` | Modo Jornada: flujo hora a hora, notificación matutina |
| `schedule_handler.py` | Registro de horario del docente |
| `position_handler.py` | Registro de cargos institucionales |
| `db_handler.py` | Panel de base de datos `/db` |
| `whatsapp_handler.py` | Setup y envío de notificaciones WhatsApp (Green API) |
| `notif_handler.py` | Generación y envío de documentos PDF |
| `help_handler.py` | Sistema de ayuda inline |
| `mode.py` | Flag de módulo "libre" \| "jornada" |
| `state.py` | Estado dual L1(RAM)+L2(Redis) con TTL, todos los flows |
| `transcription.py` | Groq Whisper para mensajes de voz |

### Skills (`src/schoolai/skills/`)

| Módulo | Descripción |
|---|---|
| `registry.py` | SkillRegistry: register(), detect(), detect_all() |
| `planner.py` | Divide texto multi-intent en fragmentos por skill |
| `base.py` | BaseSkill: matches() con keywords O(1) + patterns regex |
| `attendance/` | Skill + tools + matcher fuzzy + service |
| `homework/` | Skill + tools + detector + repository |
| `query/` | Skill + tools + extracción de períodos/cursos |
| `cuotas/` | Skill + tools + handlers (create/pago/query) + service + exporter |
| `ia/` | ChatSkill: chat IA general con streaming (Groq 70B) |
| `llm/` | Cliente unificado OpenAI-compatible + tool_caller compartido |
| `utils/` | normalize(), extract_rules, schema, keyboards |
| `documents/` | Generación de documentos PDF/notificaciones |
| `whatsapp/` | Integración Green API |

### Cuotas (`src/schoolai/skills/cuotas/`)

| Archivo | Responsabilidad |
|---|---|
| `skill.py` | CuotaSkill: detección + routing + LLM fallback |
| `extractor.py` | Regex sin LLM: detecta action (create/pago/query/export/list) |
| `tools.py` | 6 tools Python + llm_fallback(Groq) + ToolDef.to_groq() |
| `handler.py` | Re-export de los 3 sub-handlers |
| `handler_create.py` | Creación de actividad + callbacks post-creación (add/pick/addall/done) |
| `handler_pago.py` | Registro de pagos + callback pago |
| `handler_query.py` | Consultas, estado, export Excel |
| `_helpers.py` | _get_teacher_id compartido |
| `service.py` | CRUD en DB (Actividad, ActividadParticipante, ActividadPago) |
| `exporter.py` | Generación Excel con openpyxl |

### API (`src/schoolai/api/`)

| Archivo | Descripción |
|---|---|
| `auth.py` | create_access_token, get_current_user dependency |
| `routers/auth.py` | POST /auth/token |
| `routers/homework.py` | GET/PATCH /homework |
| `routers/attendance.py` | GET /attendance |
| `routers/students.py` | GET /students |
| `routers/grades.py` | GET /grades |
| `routers/subjects.py` | GET /subjects |
| `routers/cuotas.py` | GET/POST /cuotas/actividades, /participantes, /pagos |

---

## Modelos de base de datos

```
people                          grades
──────────────────────          ──────────────────────
id                              id
first_name                      name (TERCERO BT, etc.)
last_name                       sort_order
national_id                     level      (inicial|egb|bachillerato)
telegram_handle                 sublevel   (basica_superior|etc.)

students                        subjects
──────────────────────          ──────────────────────
id                              id
person_id ──► people            area       (Ciencias Naturales, etc.)
grade_id  ──► grades            name       (Física, Matemáticas, etc.)
section                         sublevel   (basica|bachillerato)
is_active

teachers                        schedules
──────────────────────          ──────────────────────
id                              id
person_id  ──► people           teacher_id ──► teachers
telegram_id (BigInteger)        day_of_week (0=Lun..4=Vie)
is_active                       period_num
                                start_time / end_time
teacher_positions               grade_id   ──► grades
──────────────────────          subject_id ──► subjects
id
teacher_id ──► teachers         homework
position_type                   ──────────────────────
grade_id   ──► grades           id
is_active                       homework (text)
                                grade_id    ──► grades
attendance                      subject_id  ──► subjects
──────────────────────          sequence_num / trimester_num
id                              submission_date / delivery_date
student_id ──► students         is_open
date
status (F|AT|J)                 homework_submissions
                                ──────────────────────
actividades                     id
──────────────────────          homework_id ──► homework
id                              student_id  ──► students
nombre                          status (missing|late|partial)
monto
teacher_id ──► teachers         actividad_participantes
is_active                       ──────────────────────
                                id
actividad_pagos                 actividad_id ──► actividades
──────────────────────          student_id   ──► students
id                              total_pagado
participante_id                 is_complete
monto
notas
```

---

## Auth JWT

```
POST /auth/token
  Body: { telegram_id: int, api_key: str }
  → valida api_key == settings.api_secret
  → resuelve role desde teacher_positions (cargo)
  → devuelve { access_token, token_type: "bearer", role, expires_in }

Authorization: Bearer <jwt>
  → get_current_user() verifica firma HS256
  → devuelve { telegram_id, role }

Roles: superadmin | admin | secretaria | teacher
Cargos habilitantes admin: rector, vicerrector, coordinador, inspector
Config: JWT_SECRET_KEY, API_SECRET, JWT_EXPIRE_HOURS=24
```

---

## Estado de sesión (RAM + Redis)

```
L1 (RAM)   — dict por user_id, proceso-local, acceso inmediato
L2 (Redis) — pickle serializado, sobrevive reinicios del bot

Claves Redis:
  db:{uid}     → DbFlow             TTL 3600s
  sch:{uid}    → ScheduleFlow       TTL 3600s
  pos:{uid}    → PositionFlow       TTL 3600s
  att:{uid}    → PendingAttendance  TTL 3600s
  sel:{uid}    → PendingSelection   TTL 3600s
  cuota:{uid}  → PendingCuotaCreate TTL 3600s
  jor:{uid}    → JornadaSession     TTL 86400s (dura todo el día)

RAM only (no Redis, TTL por cleanup job c/10min):
  _pending_pagos  → CuotaExtract pendiente de selección de actividad

Si REDIS_URL no configurado → solo L1 (válido para desarrollo).
```

---

## LLM — Groq

```python
# config.py
llm_extractor = "groq/llama-3.1-8b-instant"   # fallback extractor — rápido
llm_chat      = "groq/llama-3.3-70b-versatile" # chat IA general — streaming
```

Estrategia por capas:
1. **Regex (<1ms, sin costo)** — cubre el 85-90% de mensajes estructurados
2. **LLM fallback (~500ms, costo mínimo)** — mensajes naturales/ambiguos
3. **ChatSkill (Groq 70B)** — conversación libre, solo si ninguna skill matchea

El fallback usa tool calling (función `call_groq_tools` en `skills/llm/tool_caller.py`):
- El modelo recibe tool definitions en formato OpenAI
- Elige la tool y extrae parámetros
- El resultado se mapea a `ExtractionResult` o `CuotaExtract`

---

## Logging

```
logs/
  schoolai_2026-03-21.log      # rotación diaria
  schoolai_2026-03-15.log.gz   # comprimidos (retención 30 días)
```

Niveles: `DEBUG` (detalle interno) · `INFO` (intenciones, acciones DB) · `WARNING` (ambigüedad, estado expirado) · `ERROR` (excepciones → Telegram admin)

---

## Configuración del entorno (.env)

```env
# Obligatorio
TELEGRAM_BOT_TOKEN=...
DATABASE_URL=postgresql+asyncpg://...
GROQ_API_KEY=...          # LLM fallback + transcripción de voz

# Modo Jornada
TELEGRAM_BOT_TOKEN_DEV=...

# API auth
JWT_SECRET_KEY=<32+ chars aleatorios>
API_SECRET=<clave compartida con PWA>
JWT_EXPIRE_HOURS=24

# Redis (opcional — recomendado en producción)
REDIS_URL=redis://localhost:6379/0

# Acceso
TELEGRAM_ALLOWED_USERS=123456789,987654321
ADMIN_TELEGRAM_ID=123456789

# LLM (opcional — override de modelos)
LLM_EXTRACTOR=groq/llama-3.1-8b-instant
LLM_CHAT=groq/llama-3.3-70b-versatile
```

---

## Decisiones de diseño

**¿Por qué Skill Registry en lugar de LLM para detección de intención?**
El LLM añadía ~500ms de latencia y costo en cada mensaje, incluyendo los simples como "faltó Pedro de 3bt". Con keywords O(1) + regex, el 90% de mensajes se resuelven en <1ms. El LLM queda reservado para los casos que el regex no puede manejar.

**¿Por qué Planner separado del Registry?**
El Registry solo detecta qué skills aplican. El Planner decide cómo dividir el texto cuando hay múltiples skills. Son responsabilidades distintas: el Registry es stateless y se ejecuta siempre; el Planner solo se activa en el ~5% de mensajes multi-intent.

**¿Por qué Tools Registry si el handler ya llama a service.py directamente?**
Las tools tienen metadata (nombre, descripción, JSON Schema) que se usa para el LLM fallback. También proveen una interfaz uniforme que el orquestador futuro puede usar sin conocer los internals de cada skill.

**¿Por qué handler.py dividido en 3 sub-handlers?**
El archivo original llegó a 712 líneas mezclando creación, pagos y consultas. La división facilita el mantenimiento: cada sub-handler tiene una sola responsabilidad y < 200 líneas.

**¿Por qué Redis opcional?**
La escuela puede no tener servidor Redis. Sin él el sistema funciona igual (solo RAM). Con él, los docentes no pierden su sesión de Jornada si el bot se reinicia durante el día escolar.

**¿Por qué HS256 y no RS256?**
Un solo servicio firma y verifica. No hay microservicios que necesiten verificar sin la clave privada. HS256 es suficiente y más simple.
