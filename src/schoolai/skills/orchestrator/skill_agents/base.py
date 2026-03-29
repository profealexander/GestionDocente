"""SkillAgentBase — loop ReAct genérico y reutilizable para skill agents.

Cada SkillAgent es una unidad autónoma con:
  - Su propio system prompt (enfocado en un dominio)
  - Su lista de tools (3-5 tools en vez de todas)
  - El mismo loop ReAct (patrón NanoBot / ReAct)

Uso en Fase 2+:
    class AttendanceAgent(SkillAgentBase):
        name = "attendance"
        system_prompt_template = "You are an attendance expert..."

        @property
        def tools(self):
            return ATTENDANCE_TOOLS

    reply = await AttendanceAgent().run(text, prior_messages)

Failover / Retry:
  - Cadena de proveedores: LLM_ORCHESTRATOR → LLM_ORCHESTRATOR_FALLBACK (coma-separado)
  - Por proveedor: hasta MAX_RETRIES intentos con backoff exponencial (1 s, 2 s)
  - Rate-limit (429) o auth (401): cambia proveedor inmediatamente
  - Error transitorio: reintenta en el mismo proveedor antes de cambiar
"""

from __future__ import annotations

import asyncio
import json
from datetime import date

from loguru import logger

# Instrucciones de formato Telegram HTML — compartidas por todos los SkillAgents
TELEGRAM_FORMAT = (
    "\n\nRESPONSE FORMAT (Telegram HTML):\n"
    "- Use <b>text</b> for bold and <i>text</i> for italics.\n"
    "- Use <code>text</code> for short values like course codes.\n"
    "- NEVER use Markdown (**bold**, _italic_, | tables |, # headings).\n"
    "- NEVER use tables. Use per-course blocks instead:\n"
    "  <b>3BT</b> — 2 tasks: #1 Philosophy, #2 Math\n"
    "  <b>2BT</b> — no tasks\n"
    "- Keep responses short. Do not use emoji."
)

MAX_ITER = 6       # máximo de rondas tool_call → resultado por conversación
MAX_RETRIES = 2    # intentos por proveedor antes de cambiar al siguiente
RETRY_DELAY = 1.0  # segundos base — backoff exponencial: 1 s, 2 s


# ── Helpers de failover ────────────────────────────────────────────────────────


def _build_providers_chain(settings) -> list[str]:
    """Construye la cadena de proveedores: primario + fallbacks."""
    chain = [settings.llm_orchestrator]
    if settings.llm_orchestrator_fallback:
        for entry in settings.llm_orchestrator_fallback.split(","):
            entry = entry.strip()
            if entry and entry not in chain:
                chain.append(entry)
    return chain


def _serialize_tool_calls(tool_calls) -> list[dict]:
    """Convierte tool_calls del SDK a dicts serializables para el historial."""
    return [
        {
            "id": tc.id,
            "type": tc.type or "function",  # Z.AI puede omitir el campo
            "function": {
                "name": tc.function.name,
                "arguments": tc.function.arguments,
            },
        }
        for tc in tool_calls
    ]


def _is_rate_limit_or_auth(error: Exception) -> bool:
    """True si el error indica rate-limit o autenticación fallida."""
    err = str(error).lower()
    return "429" in err or "401" in err or "rate limit" in err or "authentication" in err


async def _llm_call_with_failover(
    messages: list[dict],
    tool_defs: list[dict],
    providers_chain: list[str],
) -> object:
    """Llama al LLM con failover automático entre proveedores.

    Returns:
        Objeto response de la API (OpenAI-compatible).

    Raises:
        Exception: la última excepción registrada si todos los proveedores fallaron.
    """
    from schoolai.skills.llm import get_client, parse_model

    last_error: Exception | None = None

    for provider_model in providers_chain:
        provider, model = parse_model(provider_model)

        try:
            client = get_client(provider, timeout=90.0)
        except ValueError as e:
            logger.debug(f"[skill_agent] proveedor '{provider}' no disponible (sin clave): {e}")
            continue

        for attempt in range(MAX_RETRIES):
            # tools=None y tool_choice=None cuando no hay tools (ej: llamada de resumen)
            has_tools = bool(tool_defs)

            def _call(msgs=messages, m=model, c=client, td=tool_defs, ht=has_tools):
                kwargs = {"model": m, "messages": msgs, "temperature": 0}
                if ht:
                    kwargs["tools"] = td
                    kwargs["tool_choice"] = "auto"
                return c.chat.completions.create(**kwargs)

            try:
                response = await asyncio.to_thread(_call)
                if provider_model != providers_chain[0] or attempt > 0:
                    logger.info(
                        f"[skill_agent] respondió {provider_model} "
                        f"(intento {attempt + 1}, primario={providers_chain[0]})"
                    )
                return response

            except Exception as e:  # noqa: BLE001
                last_error = e

                if _is_rate_limit_or_auth(e):
                    logger.warning(
                        f"[skill_agent] {provider}: rate-limit/auth — cambiando proveedor"
                    )
                    break  # no reintentar en este proveedor

                if attempt < MAX_RETRIES - 1:
                    delay = RETRY_DELAY * (2**attempt)
                    logger.warning(
                        f"[skill_agent] {provider} error transitorio "
                        f"(intento {attempt + 1}/{MAX_RETRIES}): {e} — "
                        f"reintentando en {delay:.0f}s"
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.warning(
                        f"[skill_agent] {provider} agotó {MAX_RETRIES} intentos: {e}"
                    )

    raise last_error or RuntimeError("Todos los proveedores LLM fallaron sin error registrado.")


# ── Base class ─────────────────────────────────────────────────────────────────


class SkillAgentBase:
    """Agente base con loop ReAct genérico.

    Subclasear para crear skill agents especializados:
      - Definir `name` y `system_prompt_template`
      - Sobreescribir `tools` property con las tools del dominio
      - Opcionalmente sobreescribir `_execute_tool` para lookup personalizado
      - Establecer `llm_override` para forzar un modelo específico como primario
    """

    name: str = "base"
    system_prompt_template: str = ""
    llm_override: str | None = None  # si se establece, se usa como modelo primario

    @property
    def tools(self) -> list:
        """Lista de ToolDef disponibles para este agente. Sobreescribir en subclases."""
        return []

    def get_system_prompt(self) -> str:
        """Retorna el system prompt con la fecha de hoy sustituida."""
        return self.system_prompt_template.format(today=date.today().isoformat())  # noqa: DTZ011

    async def _execute_tool(self, name: str, args: dict) -> str:
        """Ejecuta una tool por nombre.

        Implementación por defecto: busca en self.tools por nombre.
        Sobreescribir en subclases si se necesita lookup personalizado.
        """
        tools_by_name = {t.name: t for t in self.tools}
        tool = tools_by_name.get(name)
        if not tool or tool.fn is None:
            return f"Tool '{name}' not found."
        try:
            result = await tool.fn(**args)
            return str(result)
        except Exception as e:  # noqa: BLE001
            logger.error(f"[{self.name}] tool={name} error: {e}")
            return f"Error in '{name}': {e}"

    async def _execute_round(self, msg, messages: list[dict]) -> None:
        """Agrega el turno del asistente y ejecuta cada tool call al historial."""
        assistant_msg: dict = {"role": "assistant", "content": msg.content or ""}
        assistant_msg["tool_calls"] = _serialize_tool_calls(msg.tool_calls)
        messages.append(assistant_msg)

        names = [tc.function.name for tc in msg.tool_calls]
        logger.info(f"[{self.name}] tool_calls={names}")

        for tc in msg.tool_calls:
            try:
                args = json.loads(tc.function.arguments)
            except json.JSONDecodeError:
                args = {}
                logger.warning(
                    f"[{self.name}] JSON inválido en args de '{tc.function.name}': "
                    f"{tc.function.arguments!r}"
                )

            result = await self._execute_tool(tc.function.name, args)
            logger.debug(f"[{self.name}] tool={tc.function.name} → {result[:120]!r}")

            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result,
                }
            )

    async def run(
        self,
        text: str,
        prior_messages: list[dict] | None = None,
        teacher_id: int | None = None,
    ) -> str:
        """Ejecuta el loop ReAct y retorna la respuesta final.

        Args:
            text:           mensaje del docente (ya envuelto con anti-injection si aplica)
            prior_messages: historial previo de la sesión (pares user/assistant planos)
            teacher_id:     Telegram ID del docente — inyectado en el system prompt para
                            que el LLM lo pase a las tools my_courses / my_schedule.

        Returns:
            Texto final para enviar al usuario (sin HTML interno de tools).
        """
        from schoolai.config import settings

        base_chain = _build_providers_chain(settings)
        if self.llm_override:
            # Override es primario; el resto de la cadena queda como fallback
            providers_chain = [self.llm_override] + [p for p in base_chain if p != self.llm_override]
        else:
            providers_chain = base_chain
        tool_defs = [t.to_tool_dict() for t in self.tools]

        system_prompt = self.get_system_prompt()
        if teacher_id:
            system_prompt += (
                f"\n\nCurrent teacher Telegram ID: {teacher_id}. "
                "When calling 'my_courses' or 'my_schedule', always pass "
                f"telegram_id={teacher_id} exactly."
            )

        messages: list[dict] = (
            [{"role": "system", "content": system_prompt}]
            + (prior_messages or [])
            + [{"role": "user", "content": text}]
        )

        logger.debug(
            f"[{self.name}] run — proveedores={providers_chain} "
            f"tools={len(tool_defs)} contexto={len(prior_messages or []) // 2} par(es)"
        )

        for iteration in range(MAX_ITER):
            try:
                response = await _llm_call_with_failover(messages, tool_defs, providers_chain)
            except Exception as e:  # noqa: BLE001
                logger.error(f"[{self.name}] todos los proveedores fallaron (iter {iteration}): {e}")
                return (
                    "No se pudo conectar con el servicio de IA. "
                    "Verifica ZAI_API_KEY / GROQ_API_KEY en .env."
                )

            msg = response.choices[0].message

            if not msg.tool_calls:
                reply = (msg.content or "").strip()
                if reply:
                    logger.info(f"[{self.name}] respuesta final en iter={iteration}")
                    return reply
                # Gemini a veces devuelve content=None tras un tool call.
                # Pedimos resumen explícito sin tools.
                logger.debug(f"[{self.name}] content vacío en iter={iteration}, solicitando resumen")
                messages.append({"role": "assistant", "content": ""})
                messages.append({"role": "user", "content": "Resume el resultado anterior en español, de forma breve."})
                try:
                    summary_resp = await _llm_call_with_failover(messages, [], providers_chain)
                    return (summary_resp.choices[0].message.content or "").strip() or "Operación completada."
                except Exception as e:  # noqa: BLE001
                    return f"Operación completada. Error al generar resumen: {e}"

            await self._execute_round(msg, messages)

        # Excedió MAX_ITER — pedir resumen sin herramientas
        logger.warning(f"[{self.name}] excedió MAX_ITER={MAX_ITER}, solicitando resumen")
        messages.append(
            {"role": "user", "content": "Resume brevemente lo que hiciste hasta ahora."},
        )
        try:
            final_resp = await _llm_call_with_failover(messages, [], providers_chain)
            return (final_resp.choices[0].message.content or "").strip()
        except Exception as e:  # noqa: BLE001
            return f"Operación parcialmente completada. Error al generar resumen: {e}"
