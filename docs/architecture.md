# Arquitectura técnica — SchoolAI

---

## Visión general

SchoolAI tiene dos procesos independientes (bot + API) que comparten PostgreSQL y Redis:

```
┌─────────────────────────────────────────────────────────────────┐
│                         USUARIO (docente)                        │
│                    Telegram (texto o voz)                        │
└────────────────────────────┬────────────────────────────────────┘
                             │ HTTPS polling
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│                       BOT (proceso 1)                            │
│  python-telegram-bot 21.x · async · uvloop                      │
│                                                                  │
│  handlers.py → extractor/llm.py → rules.py → action_handler.py  │
│       │              │               │               │           │
│       │         LLM extractor    fallback        skills/         │
│       │         (glm-4-flash)   rule-based       attendance/     │
│       │                                          homework/       │
│       │                                          query/          │
│       │                                          ia/             │
│       └──────────────────────────────────────────┴─── asyncpg ──┤
│                                                                  │
│  Modo Jornada (bot-dev):                                         │
│    jornada_handler.py · schedule_handler.py · position_handler  │
└──────────────────────────────────┬──────────────────────────────┘
                                   │
              ┌────────────────────┼────────────────────┐
              │                    │                     │
   ┌──────────▼──────────┐  ┌──────▼──────┐   ┌────────▼────────┐
   │   PostgreSQL         │  │   Redis     │   │   LLM APIs      │
   │   schoolai DB        │  │  (estado    │   │  ZhipuAI GLM    │
   │                      │  │  persistente│   │  Groq Whisper   │
   └──────────┬──────────┘  │  opcional)  │   │  (configurable) │
              │              └─────────────┘   └─────────────────┘
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
| Función | Registro libre de asistencia/tareas | Guía hora a hora del día escolar |
| Extra | — | `/jornada`, notificación 06:00, contexto automático |

---

## Flujo de un mensaje

```
Usuario escribe:
"Faltaron Carlos y Pedro de 2bt"
        │
        ▼
handlers.py · handle_text()
  - valida usuario en allowed_user_ids
  - carga historial (últimos 6 turnos)
        │
        ▼
extractor/llm.py · extract()
  - envía al modelo GLM-4-flash
  - parsea JSON → ExtractionResult
  - si falla (sin JSON tras retry) → devuelve None
        │
        ▼ (si result is None)
extractor/rules.py · extract_fallback()
  - regex sobre "faltaron", "llegó tarde", etc.
  - extrae nombres + curso + status
  - devuelve None si no está seguro (mensaje de error al usuario)
        │
        ▼
action_handler.py · handle_extraction()
  - rutea por intent → _handle_attendance()
  - resuelve "2bt" → grade_id via course_abbrev_map
  - fuzzy match nombres → IDs de estudiantes
  - guarda en DB
        │
        ▼
Telegram reply:
"✅ Carlos Mendoza — ausente
 ⚠️ Pedro: Pedro López / Pedro García  (selecciona)"
```

---

## Flujo Modo Jornada

```
06:00 — job_morning_notify (asyncio.gather — paralelo)
  - busca teachers con horario del día
  - envía mensaje con primer período a cada docente

Docente toca "📅 Jornada" o escribe "j"
  - jornada_handler.py detecta período activo por hora
  - muestra teclado: "Aquí" / "Saltar" / "Pausar"

Docente confirma llegada (Aquí)
  - JornadaSession.status = "active"
  - grade_id + subject_id inyectados en contexto

Docente registra: "Faltó Recalde"
  - handlers._dispatch() detecta jornada activa
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
| `main.py` | Arranque, registro de handlers, post_init (Redis + course_map) |
| `handlers.py` | Entry point: texto y voz → `_dispatch()`, fallback rule-based |
| `action_handler.py` | Ruteo por intent, persistencia, respuestas |
| `query_handler.py` | Ejecuta consultas y formatea salida |
| `attendance_handler.py` | Callbacks de asistencia (grade selection) |
| `jornada_handler.py` | Modo Jornada: flujo hora a hora, notificación matutina |
| `schedule_handler.py` | Registro de horario del docente |
| `position_handler.py` | Registro de cargos institucionales del docente |
| `db_handler.py` | Panel de base de datos |
| `permissions.py` | get_access_level(telegram_id) → superadmin/admin/secretaria/teacher |
| `mode.py` | Flag de módulo "libre" \| "jornada" |
| `state.py` | Estado dual L1(RAM)+L2(Redis), TTL, JornadaSession |
| `transcription.py` | Integración Groq Whisper para audio |

### Skills (`src/schoolai/skills/`)

| Módulo | Descripción |
|---|---|
| `extractor/llm.py` | LLM extractor, parseo JSON, mapa de cursos |
| `extractor/rules.py` | Fallback rule-based: regex para asistencia/tarea sin LLM |
| `extractor/schema.py` | Dataclasses: ExtractionResult, AttendanceExtract, etc. |
| `homework/` | Repositorio de tareas |
| `attendance/` | Fuzzy matching de nombres, servicio de persistencia |
| `query/` | Resolución de consultas, formateo HTML/tablas |
| `ia/` | Chat IA general con streaming |
| `db/schedule_parser.py` | Parser texto libre "07:00-08:30 3BT Matemáticas" |
| `db/schedule_service.py` | CRUD de schedules y teachers |
| `db/position_service.py` | CRUD de cargos institucionales |
| `llm/` | Cliente LLM unificado (OpenAI-compatible, multi-provider) |
| `utils/text.py` | normalize() con lru_cache |

### API (`src/schoolai/api/`)

| Archivo | Descripción |
|---|---|
| `auth.py` | create_access_token, get_current_user dependency |
| `routers/auth.py` | POST /auth/token |
| `routers/homework.py` | GET/PATCH /homework (protegido) |
| `routers/attendance.py` | GET /attendance (protegido) |
| `routers/students.py` | GET /students (protegido) |
| `routers/grades.py` | GET /grades (público) |
| `routers/subjects.py` | GET /subjects (público) |

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
status (active|inactive)

teachers                        schedules
──────────────────────          ──────────────────────
id                              id
person_id  ──► people           teacher_id ──► teachers
telegram_id (BigInteger)        day_of_week (0=Lun..4=Vie)
is_active                       period_num
                                start_time / end_time
teacher_positions               grade_id   ──► grades
──────────────────────          subject_id ──► subjects
id                              is_active
teacher_id ──► teachers
position_type                   homework
  (tutor|jefe_area|             ──────────────────────
   jefe_subnivel|               id
   comision|cargo)              homework (text)
grade_id   ──► grades (nullable)grade_id    ──► grades
subnivel (nullable)             subject_id  ──► subjects
area (nullable)                 sequence_num / trimester_num
detail (nullable)               submission_date / delivery_date
is_active                       is_open

attendance                      homework_submissions
──────────────────────          ──────────────────────
id                              id
student_id ──► students         homework_id ──► homework
date                            student_id  ──► students
status (F|AT|J)                 status (missing|late|partial)
notes                           reported_at
recorded_by
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

## Estado de sesión (Redis + in-memory)

```
L1 (RAM) — dict por user_id, proceso-local, rápido
L2 (Redis) — pickle serializado, sobrevive reinicios del bot

Claves Redis:
  db:{uid}   → DbFlow          TTL 3600s
  sch:{uid}  → ScheduleFlow    TTL 3600s
  pos:{uid}  → PositionFlow    TTL 3600s
  att:{uid}  → PendingAttendance  TTL 3600s
  sel:{uid}  → PendingSelection   TTL 3600s
  jor:{uid}  → JornadaSession     TTL 86400s (dura todo el día)

Si REDIS_URL no configurado → sólo L1 (comportamiento anterior).
```

---

## LLM multi-provider

```python
# settings.py
llm_extractor = "zhipu/glm-4-flash"    # intención + entidades
llm_chat      = "zhipu/glm-4.5-air"    # chat IA general
llm_router    = "zhipu/glm-4-flash"    # clasificador

# format: "provider/model"
# providers: zhipu, mistral, deepseek, moonshot, nvidia,
#            minimax, openrouter, openai, groq
```

Fallback extractor (sin LLM):
- `extractor/rules.py` — detecta faltó/tarde/justificado + nombre + curso con regex
- Activa cuando `extract()` devuelve None (fallo de red o JSON inválido)
- Devuelve None si el texto es ambiguo (evita falsos positivos)

---

## Logging

```
logs/
  schoolai_2026-03-16.log      # rotación diaria
  schoolai_2026-03-15.log.gz   # comprimidos (retención 30 días)
```

Niveles: DEBUG (raw LLM) · INFO (intenciones, acciones) · WARNING (ambigüedad) · ERROR (excepciones → Telegram admin)

---

## Configuración del entorno (.env)

```env
# Obligatorio
TELEGRAM_BOT_TOKEN=...
DATABASE_URL=postgresql+asyncpg://...
ZHIPU_API_KEY=...

# Modo Jornada
TELEGRAM_BOT_TOKEN_DEV=...

# Audio
GROQ_API_KEY=...

# API auth
JWT_SECRET_KEY=<32+ chars aleatorios>
API_SECRET=<clave compartida con PWA>
JWT_EXPIRE_HOURS=24

# Redis (opcional)
REDIS_URL=redis://localhost:6379/0

# Acceso
TELEGRAM_ALLOWED_USERS=123456789,987654321
ADMIN_TELEGRAM_ID=123456789
```

---

## Decisiones de diseño

**¿Por qué LLM + fallback rule-based?**
El LLM maneja la variación lingüística alta (abreviaciones, errores, nombres de cursos). El fallback garantiza que fallos de red o cuota no bloqueen al docente para los casos más comunes (ausencias simples).

**¿Por qué Redis opcional?**
La escuela puede no tener servidor Redis. Sin él el sistema funciona igual. Con él, los docentes no pierden su sesión de Jornada si el bot se reinicia durante el día escolar.

**¿Por qué HS256 y no RS256?**
Un solo servicio firma y verifica. No hay microservicios que necesiten verificar sin la clave privada. HS256 es suficiente y más simple.

**¿Por qué Docker más tarde?**
Durante desarrollo activo el rebuild de imágenes añade fricción sin valor. Se containeriza cuando el feature set sea estable y haya servidor de deploy.
