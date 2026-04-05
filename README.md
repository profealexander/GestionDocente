> *"He aquí, os digo estas cosas para que aprendáis sabiduría; para que sepáis que cuando os halláis al servicio de vuestros semejantes, solo estáis al servicio de vuestro Dios."*
> — [Mosíah 2:17](https://www.churchofjesuschrist.org/study/scriptures/bofm/mosiah/2?lang=spa)

# SchoolAI

> Asistente IA para docentes — registra asistencia, tareas y cuotas desde Telegram con lenguaje natural, sin formularios.

Un docente escribe "faltaron Juan y María en 3B" y el sistema lo guarda, genera reportes y notifica. Sin clics, sin formularios, sin apps que aprender.

**Stack:** Python · FastAPI · PostgreSQL (Docker) · Telegram · Groq · Gemini · Green API · SvelteKit

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.13+](https://img.shields.io/badge/python-3.13+-blue.svg)](https://www.python.org/)

**Repositorios:** [Backend (este repo)](https://github.com/profealexander/schoolai) · [PWA SvelteKit](https://github.com/profealexander/schoolai-web)

![Demo SchoolAI](docs/assets/demo.png)

---

## Por qué existe este proyecto

Los docentes pierden horas semanales en trabajo administrativo repetitivo. SchoolAI convierte ese trabajo en una conversación de Telegram: el docente habla, el sistema escucha y actúa.

- Registro de asistencia por voz o texto en segundos
- Creación de tareas para múltiples materias en un mensaje
- Control de cuotas y pagos de actividades
- Consultas en lenguaje natural ("¿quién debe tareas esta semana?")
- Comunicados masivos a docentes vía WhatsApp (texto o archivo adjunto)
- Reporte de fin de jornada por curso → aprobación del tutor → notificación automática a representantes
- Panel web PWA para directivos

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
| `TELEGRAM_BOT_TOKEN_AGENTE` | Token del bot Agente IA (Gemini + GLM) | — |
| `GOOGLE_API_KEY` | API key Google AI Studio — OrchestratorSkill primario (Gemini 2.5 Flash-Lite) | — |
| `ZAI_API_KEY` | API key Z.AI global — ReplAgent (GLM-4.7-Flash) + fallback orquestador | — |
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
| `LLM_ORCHESTRATOR` | Modelo orquestador primario (default: `google/gemini-2.5-flash-lite`) | — |
| `LLM_ORCHESTRATOR_FALLBACK` | Fallback automático, coma-separado (default: `google/gemini-2.5-flash,zai/glm-4.7-flash,groq/llama-3.3-70b-versatile`) | — |
| `API_HOST` | Host del servidor API (default: `0.0.0.0`) | — |
| `API_PORT` | Puerto del servidor API (default: `8000`) | — |
| `LOG_DIR` | Directorio de logs (default: `logs`) | — |

### Obtener tu ID de Telegram

Escríbele a [@userinfobot](https://t.me/userinfobot) y te responderá con tu ID numérico.

---

## Base de datos

### Con Docker (recomendado)

```bash
docker compose up -d
```

Levanta PostgreSQL 17 en `localhost:5432` con volumen persistente `schoolai_db`.

### Manual (sin Docker)

```bash
psql -U postgres -c "CREATE USER schoolai WITH PASSWORD '1234';"
psql -U postgres -c "CREATE DATABASE schoolai OWNER schoolai;"
```

### Migraciones

```bash
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

# Bot Agente IA (Gemini 2.5 Flash-Lite + GLM-4.7-Flash REPL, sin pipeline regex)
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
    │                           # homework, attendance, subject, cuota,
    │                           # context_document, reminder
    └── skills/                 # Sistema de skills (SkillRegistry + pipeline regex → Orchestrator → Chat)
        ├── registry.py         # SkillRegistry: detect() + detect_all()
        ├── planner.py          # Divide mensajes multi-intent por skill
        ├── base.py             # BaseSkill: priority + matches() keywords + regex
        ├── attendance/         # Skill (via_llm) + tools + matcher fuzzy
        ├── homework/           # Skill (via_llm) + tools + detector + repository + handler_edit
        ├── query/              # Skill + tools
        ├── cuotas/             # Skill + tools + handlers (create/pago/query/edit) + service
        ├── orchestrator/       # OrchestratorSkill + agent ReAct loop + 15+ tools
        │                       # SkillAgents: attendance, homework, cuotas, repl, reminders, context
        │                       # Router de patrones 0ms (6 dominios) + _FlatAgent fallback
        ├── context/            # ContextAgent: documentos institucionales + búsqueda web (DuckDuckGo)
        ├── reminders/          # RemindersAgent: recordatorios programados vía Telegram
        ├── ia/                 # ChatSkill con streaming (Groq 70B)
        ├── llm/                # Cliente unificado + tool_caller + providers (groq/google/zai)
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
| `/ayuda` | Ayuda completa del bot (9 categorías) |
| `/cancelar` | Cancela el flujo actual (incluyendo confirmaciones pendientes) |
| `/db` | Panel de base de datos (docentes, estudiantes, horarios, WhatsApp) |
| `/jornada` | Inicia el modo jornada manual |
| `/horario` | Consulta el horario del día por sección |
| `/contexto` | Gestiona documentos institucionales (normativas, circulares) |
| `/cron` | Lista jobs cron con sus horarios |
| `/cron morning_notify 07:30` | Cambia la hora del aviso matutino (solo admin) |

---

## WhatsApp (Green API)

SchoolAI usa [Green API](https://green-api.com/) para enviar y recibir mensajes de WhatsApp.

| Función | Descripción |
|---|---|
| Registro de número | Desde `/db → 📱 WhatsApp docente` en Telegram |
| Comunicado masivo | Escribe "comunicado para todos los docentes: ..." |
| Reporte de jornada | Al cerrar jornada, tutor aprueba → WhatsApp a representantes |
| Canal entrante | `POST /webhook/whatsapp` — docentes pueden escribir desde WhatsApp |

Requiere `GREEN_API_INSTANCE` y `GREEN_API_TOKEN` en `.env`.

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

## Contribuir

Las contribuciones son bienvenidas. Revisa los [issues abiertos](https://github.com/profealexander/schoolai/issues) — los marcados con `good first issue` son buenos puntos de entrada.

Para cambios grandes abre un issue primero para discutir la dirección.

```bash
# Fork + clone
git clone https://github.com/tu-usuario/schoolai
cd schoolai
uv sync

# Crea tu rama
git checkout -b feat/mi-mejora

# Verifica antes de hacer PR
uv run ruff check src/
uv run pytest
```

---

## Licencia

[MIT](LICENSE) — úsalo, modifícalo, distribúyelo libremente.

