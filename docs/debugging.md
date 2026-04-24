# Guía de Debugging — SchoolAI v2

Referencia rápida para probar y depurar el stack v2 en `schoolai2/`.

---

## 1. Arrancar servicios

```bash
cd ~/schoolai2

# Base de datos (compartida con v1, DB separada)
docker ps | grep schoolai-db   # verificar que corre

# Gateway v2 (puerto 8001)
uv run schoolai-gateway

# Frontend (puerto 5173)
cd ui && npm run dev

# CLI interactivo
uv run schoolai-cli
```

---

## 2. Verificar gateway

```bash
# Health check
curl http://localhost:8001/gateway/health
# Esperado: {"status":"ok","version":"2.0.0"}

# Clasificar mensaje (solo TaskSpec, sin ejecutar agente)
curl -X POST http://localhost:8001/gateway/classify \
  -H "Content-Type: application/json" \
  -d '{"channel":"cli","user_id":"5494482378","session_id":"test","text":"Falta Tatiana 3BT"}'
# Esperado: {"channel":"telegram","domain":"attendance","intent":"record","entities":["Tatiana","3BT"],...}

# Mensaje completo (normaliza + Agent Runtime)
curl -X POST http://localhost:8001/gateway/message \
  -H "Content-Type: application/json" \
  -d '{"channel":"cli","user_id":"5494482378","session_id":"test","text":"Faltas de hoy 3BT"}'
```

---

## 3. Probar WebSocket

```bash
# Requiere wscat: npm install -g wscat
wscat -c ws://localhost:8001/gateway/ws/5494482378
# Una vez conectado, escribe:
{"text": "Faltas de hoy 3BT"}
# Respuesta esperada: {"text":"...","domain":"attendance","intent":"query","session_id":"..."}
```

---

## 4. Probar CLI

```bash
uv run schoolai-cli
# Escribir: Faltas de hoy 3BT
# Escribir: Tarea de matemáticas para el viernes 2EGB
# Escribir: salir
```

---

## 5. Flujo completo a depurar

```
Mensaje → gateway/router.py (LLM #1: clasificación)
        → gateway/normalizer.py → TaskSpec
        → agent/orchestrator.py → DomainController
        → agent/planner.py (LLM #2: plan JSON)
        → agent/executor.py → _tools/ (DB)
        → agent/synthesizer.py (LLM #3: respuesta)
        → response
```

### Logs relevantes (nivel DEBUG)
```bash
# Activar logs DEBUG
LOG_LEVEL=DEBUG uv run schoolai-gateway

# Qué buscar:
[gateway] TaskSpec — domain=... intent=... entities=...
[loop] plan=[...tools...]
[executor] tool_name({params}) → output...
[loop] done in X.XXs
```

---

## 6. Casos de prueba por dominio

### Asistencia
```
"Falta Tatiana 3BT"                → domain=attendance, intent=record
"Faltas de hoy 3BT"                → domain=attendance, intent=query
"Tardanza Mario y Pedro 2EGB"      → domain=attendance, intent=record
```

### Tareas
```
"Tarea de matemáticas viernes 3BT" → domain=homework, intent=record
"Tareas pendientes 2EGB"           → domain=homework, intent=query
```

### Cuotas
```
"¿Cuánto debe Ana García?"         → domain=cuotas, intent=query
"Pagó Pedro 10 dólares excursión"  → domain=cuotas, intent=record
```

### Reportes
```
"Reporte de asistencia 3BT"        → domain=reports, intent=query
"PDF tareas 2EGB"                  → domain=reports, intent=query
```

---

## 7. Errores comunes

| Error | Causa probable | Fix |
|---|---|---|
| `AuthError: User X not authorized` | `user_id` no está en `TELEGRAM_ALLOWED_USERS` | Añadir al `.env` |
| `Unknown LLM provider` | API key ausente en `.env` | Verificar `GOOGLE_API_KEY` / `GROQ_API_KEY` |
| `Curso 'X' no encontrado` | Curso no existe en `schoolai_v2` DB | Verificar con `psql` |
| `JSON parse error` en planner | LLM devolvió texto en vez de JSON | Revisar modelo en `LLM_PLANNER` |
| WebSocket `4003 Unauthorized` | `user_id` no autorizado | Añadir a `TELEGRAM_ALLOWED_USERS` |

---

## 8. Consultas útiles a la DB

```bash
# Conectar a schoolai_v2
docker exec -it schoolai-db psql -U schoolai -d schoolai_v2

# Ver cursos disponibles
SELECT abbreviation, name FROM grades ORDER BY name;

# Ver alumnos de un curso
SELECT p.first_name, p.last_name FROM students s
JOIN people p ON s.person_id = p.id
JOIN grades g ON s.grade_id = g.id
WHERE g.abbreviation = '3bt' AND s.status = 'active';

# Ver asistencias de hoy
SELECT p.first_name, a.status, a.date FROM attendance a
JOIN students s ON a.student_id = s.id
JOIN people p ON s.person_id = p.id
WHERE a.date = CURRENT_DATE;
```

---

## 9. Variables de entorno clave (schoolai2/.env)

```
DATABASE_URL=postgresql+asyncpg://schoolai:1234@localhost:5432/schoolai_v2
GATEWAY_ENABLED=false          # true → bots Telegram también usan gateway
GOOGLE_API_KEY=...             # llm_router (gemini-flash-lite)
GROQ_API_KEY=...               # llm_planner (gpt-oss-120b) + llm_synthesizer (llama-4-scout) + voz
TELEGRAM_ALLOWED_USERS=5494482378
```
