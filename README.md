# SchoolAI

Asistente escolar para docentes vía Telegram + API REST.
Permite registrar tareas, asistencia, cuotas de actividades y consultar reportes mediante lenguaje natural.

---

## Requisitos

- Python 3.13+
- PostgreSQL 14+
- [uv](https://docs.astral.sh/uv/) (gestor de paquetes)
- Cuenta [Groq](https://console.groq.com/) — LLM fallback + transcripción de voz
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
| `TELEGRAM_BOT_TOKEN` | Token del bot de Telegram (modo libre) | ✅ |
| `TELEGRAM_ALLOWED_USERS` | IDs de Telegram separados por coma (ej. `123456,789012`) | ✅ |
| `GROQ_API_KEY` | API key de Groq — LLM fallback + transcripción de voz | ✅ |
| `TELEGRAM_BOT_TOKEN_DEV` | Token del bot de Telegram (modo jornada) | — |
| `JWT_SECRET_KEY` | Clave secreta JWT (32+ caracteres) | ✅ para API |
| `API_SECRET` | Clave compartida con la PWA para obtener tokens | ✅ para API |
| `JWT_EXPIRE_HOURS` | Duración del token JWT en horas (default: `24`) | — |
| `REDIS_URL` | URL de Redis (ej. `redis://localhost:6379/0`) — recomendado en producción | — |
| `ADMIN_TELEGRAM_ID` | Tu ID de Telegram para recibir alertas de error | — |
| `LLM_EXTRACTOR` | Modelo Groq para fallback de extracción (default: `groq/llama-3.1-8b-instant`) | — |
| `LLM_CHAT` | Modelo Groq para chat IA (default: `groq/llama-3.3-70b-versatile`) | — |
| `API_HOST` | Host del servidor API (default: `0.0.0.0`) | — |
| `API_PORT` | Puerto del servidor API (default: `8000`) | — |
| `LOG_DIR` | Directorio de logs (default: `logs`) | — |

### Obtener tu ID de Telegram

Escríbele a [@userinfobot](https://t.me/userinfobot) y te responderá con tu ID numérico.

---

## Base de datos

```bash
# Crear base de datos
psql -U postgres -c "CREATE USER schoolai WITH PASSWORD '1234';"
psql -U postgres -c "CREATE DATABASE schoolai OWNER schoolai;"

# Ejecutar migraciones
uv run alembic upgrade head
```

Los grados (15 niveles) y materias se cargan con las migraciones.

---

## Ejecución

```bash
# Bot modo libre (producción)
uv run schoolai-bot

# Bot modo jornada (desarrollo/segundo token)
uv run schoolai-dev

# API REST
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
│   └── versions/               # Archivos de migración secuenciales
├── docs/
│   ├── architecture.md         # Arquitectura técnica detallada
│   └── user-guide.md           # Guía de uso para docentes
└── src/schoolai/
    ├── config.py               # Configuración (pydantic-settings)
    ├── bot/                    # Bot de Telegram
    │   ├── main.py             # Arranque y registro de handlers/callbacks
    │   ├── handlers.py         # Entrada de mensajes → _dispatch()
    │   ├── action_handler.py   # Procesamiento de intenciones → DB
    │   ├── state.py            # Estado de sesión RAM+Redis con TTL
    │   ├── jornada_handler.py  # Modo Jornada: flujo hora a hora
    │   ├── attendance_handler.py
    │   ├── schedule_handler.py
    │   ├── position_handler.py
    │   ├── db_handler.py
    │   ├── whatsapp_handler.py
    │   ├── notif_handler.py
    │   ├── help_handler.py
    │   └── transcription.py    # Groq Whisper para mensajes de voz
    ├── api/                    # API REST (FastAPI)
    │   ├── main.py
    │   ├── auth.py             # JWT HS256
    │   ├── schemas.py
    │   └── routers/            # auth, grades, subjects, students,
    │                           # homework, attendance, cuotas
    ├── db/                     # Capa de base de datos
    │   ├── connection.py       # Sesión async SQLAlchemy
    │   └── models/             # ORM: grade, student, teacher, homework,
    │                           # attendance, subject, cuota, notification…
    └── skills/                 # Sistema de skills
        ├── registry.py         # SkillRegistry: detect() + detect_all()
        ├── planner.py          # Divide mensajes multi-intent por skill
        ├── base.py             # BaseSkill: matches() keywords + regex
        ├── attendance/         # Skill + tools + matcher fuzzy
        ├── homework/           # Skill + tools + detector + repository
        ├── query/              # Skill + tools
        ├── cuotas/             # Skill + tools + handlers + service + exporter
        ├── ia/                 # ChatSkill con streaming (Groq 70B)
        ├── llm/                # Cliente unificado + tool_caller compartido
        ├── documents/          # Generación de documentos PDF
        ├── whatsapp/           # Integración Green API
        └── utils/              # normalize, extract_rules, schema, keyboards
```

---

## Comandos disponibles (bot)

Ver [`docs/user-guide.md`](docs/user-guide.md) para la guía completa.

| Comando | Descripción |
|---|---|
| `/start` | Saludo inicial |
| `/ayuda` | Muestra la ayuda del bot |
| `/cancelar` | Cancela el flujo actual |
| `/db` | Accede al panel de base de datos |
| `/jornada` | Inicia el modo jornada manual |

---

## API REST

Ver documentación interactiva en `/docs` (Swagger UI) o `/redoc`.

| Método | Ruta | Descripción |
|---|---|---|
| POST | `/auth/token` | Obtener JWT |
| GET | `/grades/` | Lista todos los grados |
| GET | `/subjects/` | Lista materias |
| GET | `/students/` | Lista estudiantes |
| GET | `/homework/` | Lista tareas |
| PATCH | `/homework/{id}` | Cierra una tarea |
| GET | `/attendance/` | Lista registros de asistencia |
| GET | `/cuotas/actividades/` | Lista actividades/cuotas |
| POST | `/cuotas/actividades/` | Crea una actividad |
| POST | `/cuotas/actividades/{id}/participantes` | Agrega participantes |
| POST | `/cuotas/actividades/{id}/pagos` | Registra un pago |

---

## Desarrollo

```bash
# Tests
uv run pytest

# Linter
uv run ruff check src/

# Nueva migración
uv run alembic revision --autogenerate -m "descripcion"
uv run alembic upgrade head
```

---

## Logs

Directorio configurado en `LOG_DIR` (default: `logs/`):
- Rotación diaria, retención 30 días, compresión `.gz`
- Nivel `INFO` en consola, `DEBUG` en archivo
- Si `ADMIN_TELEGRAM_ID` configurado, los errores se envían por Telegram

---

## Acceso directo Windows (WSL)

Crea un archivo `.lnk` con:
- **Target**: `C:\Windows\System32\wsl.exe`
- **Arguments**: `-e /home/edwin8600/.local/bin/uv run --project /home/edwin8600/schoolai schoolai-dev`
