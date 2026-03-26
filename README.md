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
| `TELEGRAM_BOT_TOKEN_JORNADA` | Token del bot Modo Jornada | — |
| `TELEGRAM_BOT_TOKEN_AGENTE` | Token del bot Agente IA (GLM-4.7-Flash) | — |
| `ZAI_API_KEY` | API key Z.AI global — OrchestratorSkill (GLM-4.7-Flash) | — |
| `JWT_SECRET_KEY` | Clave secreta JWT (32+ caracteres) | ✅ para API |
| `API_SECRET` | Clave compartida con la PWA para obtener tokens | ✅ para API |
| `JWT_EXPIRE_HOURS` | Duración del token JWT en horas (default: `24`) | — |
| `GREEN_API_INSTANCE` | ID de instancia Green API para WhatsApp entrante | — |
| `GREEN_API_TOKEN` | Token de instancia Green API | — |
| `REDIS_URL` | URL de Redis (ej. `redis://localhost:6379/0`) — recomendado en producción | — |
| `ADMIN_TELEGRAM_ID` | Tu ID de Telegram para recibir alertas de error | — |
| `SUPERVISED_MODE` | `true` → pide confirmación antes de toda escritura en DB (default: `false`) | — |
| `LLM_EXTRACTOR` | Modelo extractor (default: `groq/llama-3.1-8b-instant`) | — |
| `LLM_CHAT` | Modelo chat IA (default: `groq/llama-3.3-70b-versatile`) | — |
| `LLM_ORCHESTRATOR` | Modelo orquestador (default: `zai/glm-4.7-flash`) | — |
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
# Bot Modo Libre
uv run schoolai-bot

# Bot Modo Jornada
uv run schoolai-bot-jornada

# Bot Agente IA (GLM-4.7-Flash, sin pipeline regex)
uv run schoolai-bot-agente

# API REST
uv run schoolai-api
```

Con recarga automática durante desarrollo:

```bash
./dev-bot.sh           # Modo Libre
./dev-bot-jornada.sh   # Modo Jornada
./dev-bot-agente.sh    # Bot Agente
```

La API queda disponible en `http://localhost:8000`.
Documentación interactiva: `http://localhost:8000/docs`

---

## Estructura del proyecto

```
schoolai/
├── .env                        # Variables de entorno (no subir a git)
├── pyproject.toml              # Dependencias y entry points de skills/canales
├── alembic/                    # Migraciones de base de datos
│   └── versions/               # Archivos de migración secuenciales
├── docs/
│   ├── architecture.md         # Arquitectura técnica detallada
│   └── user-guide.md           # Guía de uso para docentes
└── src/schoolai/
    ├── config.py               # Configuración (pydantic-settings)
    ├── bot/                    # Bots de Telegram (tres entrypoints)
    │   ├── main.py             # Modo Libre/Jornada — pipeline completo
    │   ├── main_dev.py         # Entrypoint Modo Jornada (thin wrapper)
    │   ├── main_agente.py      # Bot Agente — directo a OrchestratorSkill
    │   ├── handlers.py         # Entrada de mensajes → _dispatch() + text_interceptors
    │   ├── action_handler.py   # Procesamiento de intenciones → DB + confirmación
    │   ├── state.py            # Estado de sesión RAM+Redis con TTL (todos los flows)
    │   ├── state_store.py      # StateStore genérico base
    │   ├── callback_router.py  # Router central de callbacks
    │   ├── text_interceptors.py # Chain de interceptores de texto por prioridad
    │   ├── edit_flow.py        # EditFlow genérico (list→pick→edit/toggle)
    │   ├── sop.py              # SOPEngine: tabla de transiciones (status, trigger)→handler
    │   ├── jornada_handler.py  # Modo Jornada: SOP Engine + notificación matutina
    │   ├── cron_service.py     # CronService: jobs persistentes en cron.json
    │   ├── cron_handler.py     # Comando /cron para administrar horarios
    │   ├── channels/           # Sistema de canales abstraído
    │   │   ├── base.py         # BaseChannel ABC + InboundMessage
    │   │   ├── telegram.py     # TelegramChannel
    │   │   └── whatsapp.py     # WhatsAppChannel + WhatsAppUpdate adapter
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
    │                           # homework, attendance, cuotas,
    │                           # whatsapp_webhook (POST /webhook/whatsapp)
    ├── db/                     # Capa de base de datos
    │   ├── connection.py       # Sesión async SQLAlchemy
    │   └── models/             # ORM: grade, student, teacher (+whatsapp_phone),
    │                           # homework, attendance, subject, cuota…
    └── skills/                 # Sistema de skills
        ├── registry.py         # SkillRegistry: detect() + detect_all()
        ├── planner.py          # Divide mensajes multi-intent por skill
        ├── base.py             # BaseSkill: priority + matches() keywords + regex
        ├── attendance/         # Skill (via_llm) + tools + matcher fuzzy
        ├── homework/           # Skill (via_llm) + tools + detector + repository + handler_edit
        ├── query/              # Skill + tools
        ├── cuotas/             # Skill + tools + handlers (create/pago/query/edit) + service
        ├── orchestrator/       # OrchestratorSkill + agent ReAct loop + 8 tools (GLM-4.7-Flash)
        ├── ia/                 # ChatSkill con streaming (Groq 70B)
        ├── llm/                # Cliente unificado + tool_caller + providers (groq/zai)
        ├── documents/          # Generación de documentos PDF
        ├── whatsapp/           # Integración Green API (saliente)
        └── utils/              # normalize, extract_rules, schema (via_llm), keyboards
```

---

## Comandos disponibles (bot)

Ver [`docs/user-guide.md`](docs/user-guide.md) para la guía completa.

| Comando | Descripción |
|---|---|
| `/start` | Saludo inicial |
| `/ayuda` | Muestra la ayuda del bot |
| `/cancelar` | Cancela el flujo actual (incluyendo confirmaciones pendientes) |
| `/db` | Accede al panel de base de datos |
| `/jornada` | Inicia el modo jornada manual |
| `/cron` | Lista jobs cron con sus horarios |
| `/cron morning_notify 07:30` | Cambia la hora del aviso matutino (solo admin) |

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
| POST | `/webhook/whatsapp` | Webhook Green API — mensajes entrantes WhatsApp |

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
