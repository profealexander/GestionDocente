# SchoolAI

Asistente escolar para docentes vía Telegram + API REST.
Permite registrar tareas, asistencia y consultar reportes mediante lenguaje natural.

---

## Requisitos

- Python 3.13+
- PostgreSQL 14+
- [uv](https://docs.astral.sh/uv/) (gestor de paquetes)
- Cuenta Zhipu AI (GLM) — extracción de intenciones y chat IA
- Cuenta Groq — transcripción de voz (opcional)
- Bot de Telegram creado con [@BotFather](https://t.me/BotFather)

---

## Instalación

```bash
git clone <repo>
cd schoolai
uv sync
```

---

## Configuración

Copia el archivo de ejemplo y edita tus valores:

```bash
cp .env.example .env
```

| Variable | Descripción | Requerida |
|---|---|---|
| `DATABASE_URL` | URL de conexión PostgreSQL (`postgresql+asyncpg://user:pass@host/db`) | ✅ |
| `TELEGRAM_BOT_TOKEN` | Token del bot de Telegram | ✅ |
| `TELEGRAM_ALLOWED_USERS` | IDs de Telegram separados por coma (ej. `123456,789012`) | ✅ |
| `GLM_API_KEY` | API key de [Zhipu AI](https://open.bigmodel.cn/) | ✅ |
| `GLM_MODEL` | Modelo GLM para chat IA (default: `glm-4.7`) | — |
| `GROQ_API_KEY` | API key de Groq para transcripción de voz | — |
| `ADMIN_TELEGRAM_ID` | Tu ID de Telegram para recibir alertas de error | — |
| `API_HOST` | Host del servidor API (default: `0.0.0.0`) | — |
| `API_PORT` | Puerto del servidor API (default: `8000`) | — |
| `LOG_DIR` | Directorio de logs (default: `logs`) | — |
| `DEBUG` | Modo debug con SQL logging (default: `false`) | — |

### Obtener tu ID de Telegram

Escríbele a [@userinfobot](https://t.me/userinfobot) y te responderá con tu ID numérico.

---

## Base de datos

### Crear la base de datos

```bash
psql -U postgres -c "CREATE USER schoolai WITH PASSWORD '1234';"
psql -U postgres -c "CREATE DATABASE schoolai OWNER schoolai;"
```

### Ejecutar migraciones

```bash
uv run alembic upgrade head
```

### Poblar catálogos iniciales

Los grados (15 niveles) y materias se cargan con las migraciones. Para agregar
estudiantes, carga los datos directamente en las tablas `people` y `students`.

---

## Ejecución

### Bot de Telegram

```bash
# Producción
uv run schoolai-bot

# Desarrollo (recarga automática)
uv run schoolai-dev
```

### API REST

```bash
uv run schoolai-api
```

La API queda disponible en `http://localhost:8000`.
Documentación interactiva: `http://localhost:8000/docs`

---

## Estructura del proyecto

```
schoolai/
├── .env                        # Variables de entorno (no subir a git)
├── pyproject.toml              # Dependencias y scripts
├── alembic/                    # Migraciones de base de datos
│   └── versions/               # 8 archivos de migración
├── docs/                       # Documentación
│   ├── architecture.md         # Arquitectura técnica
│   └── user-guide.md           # Guía de usuario (docente)
└── src/schoolai/
    ├── config.py               # Configuración (pydantic-settings)
    ├── bot/                    # Bot de Telegram
    │   ├── main.py             # Arranque y registro de handlers
    │   ├── handlers.py         # Manejo de mensajes de texto y voz
    │   ├── action_handler.py   # Procesamiento de intenciones
    │   ├── query_handler.py    # Consultas y reportes
    │   ├── attendance_handler.py
    │   ├── help_handler.py
    │   ├── db_handler.py
    │   ├── state.py            # Estado de sesión en memoria (TTL 60 min)
    │   └── transcription.py   # Transcripción de voz con Groq
    ├── api/                    # API REST (FastAPI)
    │   ├── main.py             # App FastAPI
    │   ├── schemas.py          # Modelos Pydantic de respuesta
    │   └── routers/            # Endpoints por recurso
    │       ├── grades.py       # GET /grades
    │       ├── subjects.py     # GET /subjects
    │       ├── homework.py     # GET/PATCH /homework
    │       ├── students.py     # GET /students
    │       └── attendance.py   # GET /attendance
    ├── db/                     # Capa de base de datos
    │   ├── connection.py       # Sesión async SQLAlchemy
    │   └── models/             # Modelos ORM
    │       ├── grade.py
    │       ├── student.py
    │       ├── homework.py
    │       ├── homework_submission.py
    │       ├── attendance.py
    │       ├── subject.py
    │       └── person.py
    └── skills/                 # Módulos de habilidades IA
        ├── extractor/          # Extracción de intenciones (GLM 4.5-air)
        ├── homework/           # Registro y consulta de tareas
        ├── attendance/         # Registro de asistencia con fuzzy matching
        ├── query/              # Formateo de reportes HTML/tablas
        └── ia/                 # Chat IA general (GLM 4.7)
```

---

## Comandos disponibles (bot)

Ver [`docs/user-guide.md`](docs/user-guide.md) para la guía completa.

| Comando | Descripción |
|---|---|
| `/ayuda` | Muestra la ayuda del bot |
| `/cancelar` | Cancela el flujo actual |
| `/db` | Accede al panel de base de datos |

---

## API REST

Ver documentación interactiva en `/docs` (Swagger UI) o `/redoc`.

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/grades/` | Lista todos los grados |
| GET | `/subjects/` | Lista materias (filtrable por nivel) |
| GET | `/students/` | Lista estudiantes (filtrable por grado y estado) |
| GET | `/students/{id}` | Obtiene un estudiante |
| GET | `/homework/` | Lista tareas (filtrable por grado, materia, estado) |
| GET | `/homework/{id}` | Obtiene una tarea |
| PATCH | `/homework/{id}` | Cierra una tarea |
| GET | `/attendance/` | Lista registros de asistencia |

---

## Logs

Los logs se guardan en el directorio configurado en `LOG_DIR` (default: `logs/`).

- Rotación diaria, retención 30 días, compresión `.gz`
- Nivel `INFO` en archivo, `DEBUG` en consola en modo desarrollo
- Si `ADMIN_TELEGRAM_ID` está configurado, los errores se envían por Telegram

---

## Acceso directo Windows (WSL)

Para crear un acceso directo en el escritorio de Windows que levante el bot:

1. Crea un archivo `SchoolAI Bot.lnk` apuntando a:
   - **Target**: `C:\Windows\System32\wsl.exe`
   - **Arguments**: `-e /home/edwin8600/.local/bin/uv run --project /home/edwin8600/schoolai schoolai-dev`

---

## Desarrollo

```bash
# Linter
uv run ruff check src/

# Tests
uv run pytest

# Nueva migración
uv run alembic revision --autogenerate -m "descripcion"
uv run alembic upgrade head
```
