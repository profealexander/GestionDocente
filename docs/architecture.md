# Arquitectura técnica — SchoolAI

---

## Visión general

SchoolAI tiene dos procesos independientes que comparten la misma base de datos PostgreSQL:

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
│  handlers.py → extractor/llm.py → action_handler.py             │
│       │              │                    │                      │
│       │         ZhipuAI GLM          skills/                     │
│       │         (extractor)          attendance/                 │
│       │                              homework/                   │
│       │                              query/                      │
│       │                              ia/                         │
│       └──────────────────────────────┴──── asyncpg ──┐           │
└──────────────────────────────────────────────────────┼──────────┘
                                                        │
                                          ┌─────────────▼──────────┐
                                          │   PostgreSQL            │
                                          │   schoolai DB           │
                                          └─────────────┬──────────┘
                                                        │
┌──────────────────────────────────────────────────────┼──────────┐
│                       API (proceso 2)                 │          │
│  FastAPI · Uvicorn · asyncpg                          │          │
│                                                       │          │
│  GET /grades  GET /subjects  GET /students ───────────┘          │
│  GET /homework  PATCH /homework  GET /attendance                 │
│                                                                  │
│  Swagger UI: /docs    ReDoc: /redoc                              │
└─────────────────────────────────────────────────────────────────┘
```

---

## Flujo de un mensaje

```
Usuario escribe:
"Faltaron Carlos y Pedro de 2bt"
        │
        ▼
handlers.py · handle_text()
  - valida usuario en allowed_user_ids
  - carga historial de conversación (últimos 6 turnos)
        │
        ▼
extractor/llm.py · extract()
  - envía mensaje + historial al modelo GLM-4.5-air
  - prompt en inglés, respuesta JSON
  - parsea JSON → ExtractionResult
  {
    intent: "attendance",
    data: AttendanceExtract(
      names=["Carlos", "Pedro"],
      course="2bt",
      date="today",
      status="absent",
      complete=True
    )
  }
        │
        ▼
action_handler.py · handle_extraction()
  - rutea por intent → _handle_attendance()
  - resuelve "2bt" → grade_id via course_abbrev_map
  - fuzzy match: "Carlos" → "Carlos Mendoza (id=42)"
                 "Pedro"  → ambiguo (2 resultados)
  - guarda F para Carlos, reporta ambigüedad para Pedro
        │
        ▼
Telegram reply (HTML):
"✅ Registrado:
  • Carlos Mendoza — ausente
⚠️ Ambiguo:
  • Pedro: Pedro López / Pedro García"
```

---

## Flujo de mensaje de voz

```
Usuario envía audio
        │
        ▼
handlers.py · handle_voice()
  - descarga archivo OGG de Telegram
  - llama Groq API (whisper-large-v3)
  - obtiene transcripción de texto
  - continúa igual que un mensaje de texto
```

---

## Flujo cuando falta el curso

```
Usuario: "Registrar tarea de inglés: traducir el texto"
        │
        ▼
extractor: HomeworkExtract(course=None, complete=False)
        │
        ▼
action_handler: _handle_homework()
  - detecta complete=False
  - guarda estado pendiente en memory cache (TTL 60 min)
  - muestra teclado inline con los 15 cursos
        │
        ▼ usuario toca "3BT"
handle_act_callback()
  - recupera estado pendiente
  - inyecta course="3bt"
  - reprocesa como si el mensaje original lo incluyera
        │
        ▼
flujo normal → guarda tarea
```

---

## Componentes

### Bot (`src/schoolai/bot/`)

| Archivo | Responsabilidad |
|---|---|
| `main.py` | Arranque, registro de handlers, post_init hook |
| `handlers.py` | Entry point: texto y voz → `_dispatch()` |
| `action_handler.py` | Ruteo por intent, persistencia, respuestas |
| `query_handler.py` | Ejecuta consultas y formatea salida |
| `attendance_handler.py` | Callbacks de asistencia |
| `help_handler.py` | Sistema de ayuda con callbacks |
| `db_handler.py` | Panel de base de datos |
| `state.py` | Caché en memoria con TTL (sesiones pendientes) |
| `transcription.py` | Integración Groq para audio |

### Skills (`src/schoolai/skills/`)

| Módulo | Descripción |
|---|---|
| `extractor/` | LLM GLM-4.5-air, parseo de JSON, mapa de cursos |
| `homework/` | Repositorio de tareas, detección regex de cursos/materias |
| `attendance/` | Fuzzy matching de nombres, servicio de persistencia |
| `query/` | Resolución de consultas, formateo HTML/tablas |
| `ia/` | Chat IA general con GLM-4.7 |

### API (`src/schoolai/api/`)

FastAPI con 5 recursos de solo lectura (excepto PATCH homework):

| Recurso | Endpoints |
|---|---|
| Grades | `GET /grades/` |
| Subjects | `GET /subjects/` |
| Students | `GET /students/`, `GET /students/{id}` |
| Homework | `GET /homework/`, `GET /homework/{id}`, `PATCH /homework/{id}` |
| Attendance | `GET /attendance/` |

---

## Modelos de base de datos

```
people                          grades
──────────────────────          ──────────────────────
id                              id
first_name                      name (TERCERO BT, etc.)
last_name                       sort_order
national_id                     level      (inicial|egb|bachillerato)
role                            sublevel   (basica_superior|etc.)
telegram_handle
                                subjects
students                        ──────────────────────
──────────────────────          id
id                              area
person_id ──► people            name
grade_id  ──► grades            sublevel (basica|bachillerato)
section
status (active|inactive)

homework                        attendance
──────────────────────          ──────────────────────
id                              id
homework (text)                 student_id ──► students
grade_id    ──► grades          date
subject_id  ──► subjects        status (F|AT|J)
sequence_num                    notes
trimester_num                   recorded_by
submission_date
delivery_date
is_open

homework_submissions
──────────────────────
id
homework_id ──► homework
student_id  ──► students
status (missing|late|partial)
reported_at
```

---

## Servicio de IA

### Extractor (GLM-4.5-air)

- **Propósito**: clasificar intenciones y extraer entidades de mensajes en español
- **Prompt**: en inglés (~38 líneas, ~223 tokens)
- **Parámetros**: `temperature=0.1`, `top_p=0.2`, `max_tokens=500`, `timeout=30s`
- **Contexto**: últimos 6 mensajes del historial (3 turnos)
- **Salida**: JSON estricto con `intent` + datos según tipo

**Intenciones detectadas:**

| Intent | Trigger | Datos extraídos |
|---|---|---|
| `attendance` | alguien faltó/llegó tarde | names, course, date, status |
| `homework` | registrar nueva tarea | description, course, subject, delivery_date |
| `homework_report` | alguien no entregó | names, homework_ref, course, subject, status |
| `query` | consultar/reportar datos | query_type, courses[], period |
| `chat` | pregunta general | — |

### Chat IA (GLM-4.7)

- **Propósito**: responder preguntas pedagógicas generales
- **Restricción explícita**: no inventa datos escolares; redirige a comandos
- **Parámetros**: `temperature=0.7`, `top_p=0.9`, `timeout=120s`
- **Salida**: streaming en Telegram (actualiza el mensaje cada 20 caracteres)

---

## Mapa de cursos (abreviaciones)

Cargado al arrancar el bot desde la tabla `grades`:

```python
{
  "i1": 1,   "i2": 2,   "prep": 3,
  "2egb": 4, "3egb": 5, "4egb": 6,
  "5egb": 7, "6egb": 8, "7egb": 9,
  "8egb": 10,"9egb": 11,"10egb": 12,
  "1bt": 13, "2bt": 14, "3bt": 15,
}
```

El extractor retorna estas abreviaciones. El `action_handler` las resuelve a
`grade_id` sin tocar la base de datos en cada mensaje.

---

## Estado de sesión

El bot mantiene un caché en memoria (no Redis, no DB) para estados pendientes:

```python
# state.py
_pending: dict[int, PendingState]  # user_id → estado

class PendingState:
    intent: str
    data: dict
    created_at: datetime  # TTL = 60 minutos
```

Un job de limpieza corre cada 10 minutos y elimina estados expirados.
Al reiniciar el bot, los estados pendientes se pierden (diseño intencional).

---

## Logging

Configurado con `loguru`:

```
logs/
  schoolai_2026-03-15.log      # rotación diaria
  schoolai_2026-03-14.log.gz   # comprimidos (retención 30 días)
```

Niveles:
- `DEBUG`: respuestas raw del LLM, detalles de SQL (si `DEBUG=true`)
- `INFO`: mensajes recibidos, intenciones detectadas, acciones completadas
- `WARNING`: JSON no encontrado en respuesta LLM, matches ambiguos
- `ERROR`: excepciones, errores de API — enviados también por Telegram al admin

---

## Configuración del entorno

```
schoolai-bot  →  schoolai.bot.main:run      # polling largo
schoolai-dev  →  schoolai.bot.dev:run       # recarga en caliente
schoolai-api  →  schoolai.api.runner:run    # uvicorn
```

Stack de producción:
- Python 3.13 (pinned con `uv python pin 3.13`)
- uvloop (async loop de alto rendimiento, instalado con `uvicorn[standard]`)
- asyncpg (driver async nativo de PostgreSQL)
- Pydantic v2 (validación y settings)

---

## Decisiones de diseño

**¿Por qué LLM para extracción en lugar de regex/FSM?**
Los mensajes de docentes tienen variación lingüística alta (abreviaciones,
errores, nombres de cursos mal escritos). El LLM maneja todos estos casos
con un solo prompt, sin mantenimiento de reglas. El modelo pequeño (4.5-air)
es suficiente para clasificación y extracción estructurada.

**¿Por qué el prompt del extractor está en inglés?**
El modelo GLM responde mejor a instrucciones en inglés, especialmente para
formato JSON estricto. Las respuestas al usuario siguen en español.

**¿Por qué estado en memoria y no en DB?**
Los estados pendientes son efímeros (máximo 60 minutos, típicamente segundos).
Escribirlos en DB añadiría complejidad sin beneficio práctico en este contexto
de un solo docente por sesión.

**¿Por qué `post_init` en lugar de `asyncio.run()`?**
`asyncio.run()` crea y destruye su propio event loop. Al llamarlo antes del
arranque de PTB, las conexiones DB quedan vinculadas a ese loop destruido,
causando `RuntimeError: Event loop is closed`. Con `post_init`, la carga
del mapa de cursos ocurre dentro del event loop de PTB.

**¿Por qué abreviaciones en el LLM en lugar de nombres completos?**
Reducir el contexto: la lista completa de 15 nombres en el prompt ocupa ~200
tokens. Con abreviaciones (`i1, i2, prep, 2egb...3bt`) son ~30 tokens.
Además, el mapeo abbrev→grade_id es O(1) en memoria.
