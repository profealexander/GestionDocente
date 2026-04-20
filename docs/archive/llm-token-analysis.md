# Análisis de consumo LLM — SchoolAI

**Fecha:** 2026-04-06 (análisis inicial) · **Actualizado:** 2026-04-19 (stack migrado)  
**Objetivo:** Identificar fuentes de cargos en Gemini API y oportunidades de optimización de tokens

---

## 1. Modelos actualmente en uso (2026-04-19)

| Variable config | Modelo | Proveedor | Costo |
|---|---|---|---|
| `llm_extractor` | `gemini-3.1-flash-lite-preview` | Google AI Studio | ✅ gratis (500 RPD) |
| `llm_router` | `gemini-3.1-flash-lite-preview` | Google AI Studio | ✅ gratis (500 RPD) |
| `llm_chat` | `groq/compound-beta` | Groq | ✅ gratis (web search) |
| `llm_chat_fallback` | `groq/qwen/qwen3-32b` | Groq | ✅ gratis |
| `llm_orchestrator` | `moonshotai/kimi-k2-instruct` | Groq | ✅ gratis |
| `llm_orchestrator_fallback` | `deepseek-chat → deepseek-reasoner → gpt-oss-120b → mistral-large` | DeepSeek/Groq/Mistral | ⚠️ DeepSeek pago ($0.28/$0.42/1M) si se activa |

**Stack mayormente gratuito.** Solo incurre costo si el orchestrator falla 3 veces y llega a DeepSeek, o si llega al fallback final Mistral Large.

---

## 2. Mapa de puntos de llamada LLM (8 en total)

| # | Archivo | Función | Línea | Modelo | Registra en llm_usage |
|---|---|---|---|---|---|
| 1 | `orchestrator/agent.py` | `run()` | 94 | orchestrator | ✅ Sí |
| 2 | `orchestrator/skill_agents/base.py` | `SkillAgent.run()` | 233 | orchestrator | ✅ Sí |
| 3 | `llm/tool_caller.py` | `call_groq_tools()` | 19 | llm_extractor | ✅ Sí |
| 4 | `bot/router.py` | `classify()` | 25 | llm_router | ❌ No |
| 5 | `ia/agent.py` | `chat()` | 20 | llm_chat | ❌ No |
| 6 | `context/extractor.py` | `extract_from_file()` | 39 | google multimodal | ❌ No |
| 7 | `context/categorizer.py` | `categorize()` | 39 | orchestrator | ❌ No |
| 8 | `api/routers/dev.py` | `/api/v1/dev/run-llm` | 85 | user-defined | ❌ No |

**Brecha:** 5 de 8 puntos (62%) no registran en `llm_usage`.
El 40% del consumo real es invisible en métricas.

---

## 3. Tamaño de system prompts por agente

| Agente | Tokens estimados | Archivo |
|---|---|---|
| FlatAgent (orchestrator principal) | ~318 tokens | `orchestrator/agent.py:37-63` |
| RemindersAgent | ~147 tokens | `skill_agents/reminders.py:7-28` |
| CuotasAgent | ~133 tokens | `skill_agents/cuotas.py:7-26` |
| AttendanceAgent | ~109 tokens | `skill_agents/attendance.py:7-27` |
| HomeworkAgent | ~101 tokens | `skill_agents/homework.py:7-26` |
| IA Chat (fallback) | ~99 tokens | `ia/agent.py:11-17` |
| ContextAgent | ~95 tokens | `skill_agents/context.py:7-31` |
| REPL Agent | ~79 tokens | `orchestrator/repl.py:12-35` |
| Router clasificador | ~37 tokens | `bot/router.py:10-22` |
| Categorizador documentos | ~175 tokens | `context/categorizer.py:15-36` |
| File extractor | ~37 tokens | `context/extractor.py:30-36` |
| **TOTAL base (todos los agentes)** | **~1,230 tokens** | — |

---

## 4. Flujo del Orchestrator y amplificación de tokens

```
orchestrator/agent.py:94 → run(user_id, text)
  │
  ├─ Anti-injection wrapper (línea 107)
  ├─ Load session: hasta 6 pares previos (línea 108)    ← historial completo
  ├─ Pattern routing por regex → 0 tokens (línea 111)
  │     ├─ 0 matches → FlatAgent (318 tokens system)
  │     ├─ 1 match   → SkillAgent especializado (79-147 tokens)
  │     └─ N matches → asyncio.gather en paralelo
  ├─ ReAct loop: hasta 6 iteraciones (MAX_ITER = 6)     ← amplificación 6x
  └─ Save session: últimos 6 pares (línea 133)
```

**Ejemplo consumo por sesión (AttendanceAgent, 4 turnos):**

| Turno | Tokens entrada | Tokens salida | Acumulado |
|---|---|---|---|
| 1 | ~500 | ~150 | 650 |
| 2 | ~460 (+60 historial) | ~50 | 1,160 |
| 3 | ~570 (+120 historial) | ~100 | 1,830 |
| 4 | ~680 (+180 historial) | ~150 | 2,660 |

**TOTAL sesión típica: ~2,200-2,700 tokens** por usuario por conversación.

**Configuración de historial:**
- Orchestrator: máximo **6 pares** (12 mensajes) — `session.py:34`
- IA Skill: máximo **10 pares** (20 mensajes) — `history.py:6` — **solo en RAM, se pierde al reiniciar**
- TTL sesión: 1,800 segundos (30 minutos)

---

## 5. Problemas identificados

### 🔴 Crítico

**P1 — Fallback activa Gemini Flash (de pago) antes que Groq**
- Archivo: `config.py:37`
- `llm_orchestrator_fallback = "google/gemini-2.5-flash,zai/glm-4.7-flash,groq/llama-3.3-70b-versatile"`
- Cuando flash-lite falla, el primer intento es Gemini Flash (cobro por token)
- Fix: cambiar orden a `"zai/glm-4.7-flash,groq/llama-3.3-70b-versatile"`
- **Esfuerzo: 1 línea. Elimina cargos inmediatos.**

**P2 — Context extractor sin límite de tamaño de archivo**
- Archivo: `context/extractor.py:39`
- Manda archivos completos en base64 inline al LLM
- Un PDF de 100MB puede generar 30-40 millones de tokens en una sola llamada
- Sin validación de tamaño antes de enviar
- **Riesgo: una sola llamada puede generar un cargo enorme**

**P3 — 5 puntos de llamada sin rastreo en llm_usage**
- `bot/router.py:47`, `ia/agent.py:57`, `context/extractor.py:69`, `context/categorizer.py:65`, `api/routers/dev.py:108`
- Imposible saber cuánto consumen realmente
- **Esfuerzo: 1 línea por punto (5 líneas total)**

### 🟡 Alto impacto

**P4 — Router llama al LLM en cada mensaje**
- Archivo: `bot/router.py:25`
- Cada mensaje recibido genera una llamada LLM para clasificar intent
- El orchestrator ya hace routing por regex (0 tokens) — lógica duplicada
- Fix: invertir orden — regex primero, LLM solo si no hay match
- **Ahorro estimado: 80-90% de las llamadas del router**

**P5 — Historial completo se manda en cada iteración del ReAct loop**
- Archivo: `skill_agents/base.py:272-283`
- El loop interno (hasta 6 iteraciones) incluye el historial completo en cada llamada
- Genera efecto 6x en sesiones complejas
- Fix: pasar solo el historial relevante al contexto de la iteración

**P6 — Categorizador de documentos bloquea con LLM innecesariamente**
- Archivo: `context/categorizer.py:39`
- Una llamada LLM síncrona al cargar cada documento
- Bloquea la respuesta al usuario mientras espera
- Fix: hacer async en background, retornar defaults inmediatamente

### 🟢 Optimización

**P7 — Sin prompt caching activado**
- System prompts > 1,024 tokens se benefician del caching de Gemini
- Los agentes mandan el mismo system prompt en cada llamada sin cachear
- Fix: activar `cache_control` en headers de la API de Gemini
- **Ahorro: ~80% del costo de tokens de entrada en system prompts**

**P8 — Schema SQL repetido en cada turno del REPL**
- Archivo: `skill_agents/repl.py:23-31`
- El schema de la BD se incluye en cada turno (79 tokens fijos)
- Candidato ideal para prompt caching

---

## 6. Estado de llm_usage (tabla de métricas)

La tabla `llm_usage` está bien diseñada:

```python
# db/models/llm_usage.py
ts               # timestamp automático
provider         # "groq", "google", "zai"
model            # nombre exacto del modelo
agent            # "attendance", "homework", "orchestrator"
prompt_tokens    # tokens de entrada
completion_tokens # tokens de salida
cached_tokens    # tokens que vinieron de caché
```

**Quién registra:** `SkillAgentBase._llm_call_with_failover()` y `call_groq_tools()`  
**Quién NO registra:** router, chat IA, extractor de archivos, categorizador, endpoint dev

---

## 7. Plan de acción por prioridad

### Inmediato (sin riesgo, máximo impacto)

| Acción | Archivo | Esfuerzo | Impacto |
|---|---|---|---|
| Quitar `gemini-2.5-flash` del fallback | `config.py:37` | 1 línea | Elimina cargos Google |
| Límite de tamaño en context extractor | `context/extractor.py:39` | ~5 líneas | Protección contra picos |
| Registrar tokens en los 5 puntos faltantes | 5 archivos | 1 línea c/u | Visibilidad completa |

### Corto plazo (1-2 semanas)

| Acción | Archivos | Esfuerzo | Ahorro |
|---|---|---|---|
| Invertir lógica router (regex → LLM) | `bot/router.py` | ~10 líneas | 80-90% llamadas router |
| Categorizador async en background | `context/categorizer.py` | ~20 líneas | Mejora UX + menos bloqueos |

### Mediano plazo (1 mes)

| Acción | Archivos | Esfuerzo | Ahorro |
|---|---|---|---|
| Activar prompt caching Gemini | `llm/client.py` | ~15 líneas | ~80% en system prompts |
| Optimizar historial en ReAct loop | `skill_agents/base.py` | ~30 líneas | Hasta 6x en sesiones largas |

### Largo plazo (arquitectura)

| Acción | Descripción | Ahorro |
|---|---|---|
| Gemini Files API | Subir archivos una vez, referenciar por ID en lugar de base64 inline | 90%+ en documentos |
| Embedding + vector search | Retrieval para documentos grandes, LLM solo para síntesis final | Escalabilidad |

---

## 8. Resumen ejecutivo

El proyecto tiene buena base (historial limitado, rastreo parcial, routing por regex), pero hay **3 problemas que generan cargos reales ahora mismo:**

1. El fallback llama a Gemini Flash (de pago) antes que Groq — **fix: 1 línea**
2. El context extractor no tiene límite de tamaño — **riesgo de cargo enorme en una sola llamada**
3. El router LLM llama en cada mensaje aunque el orchestrator ya hace lo mismo gratis — **desperdicio del 80-90%**

Con solo los cambios inmediatos se eliminan los cargos actuales de Google. Las optimizaciones de mediano plazo pueden reducir el consumo total en un 50-70%.
