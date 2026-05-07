# Plan: Corrección de Documentación y Bugs Pendientes

**Fecha:** 2026-05-05
**Origen:** Auditoría completa docs vs código

---

## Fase 1 — Corregir CLAUDE.md (inconsistencias con el código)

### 1.1 Actualizar prioridades de skills
- [ ] Corregir HomeworkSkill: 20 → 30
- [ ] Corregir QuerySkill: 30 → 40
- [ ] Agregar HWReportSkill (p=20), CuotaSkill (p=35), HWEditSkill (p=40), OrchestratorSkill (p=50)

**Archivo:** `CLAUDE.md` sección "v1 — Pipeline de dispatch"

### 1.2 Actualizar llm_extractor
- [ ] Cambiar primary de `mistral/mistral-medium-latest` a `groq/openai/gpt-oss-120b`
- [ ] Documentar fallback `mistral/mistral-medium-latest`

**Archivo:** `CLAUDE.md` sección "LLM stack"

### 1.3 Agregar executor.py a la tabla de módulos del Agent Runtime
- [ ] Añadir fila: `agent/executor.py` — Ejecuta cada tool step (Python puro)

**Archivo:** `CLAUDE.md` sección "Agent Runtime (v2)"

### 1.4 Marcar migración homework a Google Sheets como "NO iniciada"
- [ ] Actualizar sección "Homework backend" indicando que los archivos repository_base/db/sheets/factory NO existen aún

**Archivo:** `CLAUDE.md` sección "Homework backend"

---

## Fase 2 — Corregir docstrings obsoletos en código

### 2.1 `agent/synthesizer.py:4`
- [ ] Cambiar `"Uses llm_router (gemini-flash-lite)"` → `"Uses llm_synthesizer"`

### 2.2 `skills/llm/usage.py:8`
- [ ] Actualizar ejemplo de `gemini-2.5-flash-lite` al modelo actual

### 2.3 `skills/context/extractor.py:60,77`
- [ ] Reemplazar hardcode `model="gemini-3.1-flash-lite-preview"` por el modelo actual del config o documentar que es un fallback legacy

### 2.4 `skills/llm/structured.py:69`
- [ ] Actualizar docstring de `google/gemini-3.1-flash-lite-preview` al modelo actual

---

## Fase 3 — Resolver bugs pendientes de auditoría

### 3.1 Eliminar alias `call_groq_tools` (issue 4.6)
- [ ] Migrar 4 callers a `call_extractor_tools`:
  - `skills/homework/tools.py`
  - `skills/attendance/tools.py`
  - `skills/cuotas/tools.py`
  - `skills/query/tools.py`
- [ ] Eliminar alias de `skills/llm/tool_caller.py:112`

### 3.2 Eliminar dead code `start_attendance()` (issue 5.1)
- [ ] Eliminar función de `bot/attendance_handler.py:35`

### 3.3 Resolver entry points `schoolai.channels` (issue 5.2)
- [ ] Opción A: Crear un loader en `bot/channels/__init__.py` que use `importlib.metadata.entry_points`
- [ ] Opción B: Eliminar los entry points de `pyproject.toml` si no se van a usar
- **Decisión pendiente con el usuario**

---

## Fase 4 — Actualizar documento de auditoría

### 4.1 Actualizar `docs/audit-fixes-2026-04-24.md`
- [ ] Marcar issues 2.3, 2.4, 4.2, 4.3, 4.5 como RESUELTOS
- [ ] Corregir issues 2.3 (CORS) y 5.1 (`get_session`) como incorrectos
- [ ] Actualizar estado de issues 4.6, 5.1, 5.2, 3.4

---

## Orden de ejecución

1. Fase 1 (docs) → sin riesgo, solo texto
2. Fase 2 (docstrings) → sin riesgo, solo comentarios
3. Fase 3.1 (alias rename) → bajo riesgo, rename mecánico
4. Fase 3.2 (dead code) → bajo riesgo, eliminación limpia
5. Fase 3.3 (channels) → requiere decisión
6. Fase 4 (actualizar auditoría) → sin riesgo
