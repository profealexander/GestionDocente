"""Generic edit flow: list → pick → edit field / toggle boolean."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Generic, TypeVar

from loguru import logger
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode

M = TypeVar("M")

_REDIS_TTL = 3600


@dataclass
class FieldDef:
    """An editable text field."""
    key: str          # identifier used in callback_data
    label: str        # displayed in button & success message (e.g. "Descripción")
    prompt: str       # what to ask the user (e.g. "nueva descripción de la tarea")
    # async (text: str, session) -> dict of kwargs to pass to update_fn
    # OR str error message to show the user.
    # If None: kwargs = {key: text} (raw text stored directly)
    parse_fn: Callable | None = None


@dataclass
class ToggleDef:
    """A boolean toggle field."""
    field: str        # DB field name
    label_on: str     # button label when field is True  (e.g. "🔒 Cerrar")
    label_off: str    # button label when field is False (e.g. "🔓 Abrir")


class EditFlow(Generic[M]):
    """
    Reusable edit flow for any DB model.

    Usage:
        flow = EditFlow(
            prefix="hw_edit",
            model_class=Homework,
            fields=[FieldDef("homework", "Descripción", "nueva descripción"), ...],
            toggles=[ToggleDef("is_open", "🔒 Cerrar", "🔓 Abrir")],
            summary_fn=_hw_summary,
            list_fn=list_open_homework,   # async (session, **kw) -> list[M]
            update_fn=update_homework,    # async (session, entity_id, **kw) -> M|None
            list_item_fn=lambda hw: f"#{hw.sequence_num} — ...",
        ).register()
    """

    def __init__(
        self,
        prefix: str,
        model_class: type,
        fields: list[FieldDef],
        toggles: list[ToggleDef],
        summary_fn: Callable[[M], str],
        list_fn: Callable,
        update_fn: Callable,
        list_label: str = "¿Qué deseas editar?",
        list_item_fn: Callable[[M], str] | None = None,
    ) -> None:
        from schoolai.bot.state_store import StateStore

        self._prefix = prefix
        self._model = model_class
        self._fields = {f.key: f for f in fields}
        self._toggles = {t.field: t for t in toggles}
        self._summary_fn = summary_fn
        self._list_fn = list_fn
        self._update_fn = update_fn
        self._list_label = list_label
        self._list_item_fn = list_item_fn or (lambda e: f"ID {e.id}")
        self._store: StateStore = StateStore(f"{prefix}_pending")

    # ── keyboard builders ─────────────────────────────────────────────────────

    def _edit_keyboard(self, entity: M) -> InlineKeyboardMarkup:
        rows: list[list] = []
        buttons = [
            InlineKeyboardButton(
                f.label,
                callback_data=f"{self._prefix}_field:{entity.id}:{f.key}",
            )
            for f in self._fields.values()
        ]
        rows.extend(buttons[i : i + 2] for i in range(0, len(buttons), 2))
        for t in self._toggles.values():
            current = getattr(entity, t.field, False)
            label = t.label_on if current else t.label_off
            rows.append(
                [
                    InlineKeyboardButton(
                        label,
                        callback_data=f"{self._prefix}_toggle:{entity.id}:{t.field}",
                    ),
                ],
            )
        return InlineKeyboardMarkup(rows)

    def _pick_keyboard(self, entities: list[M]) -> InlineKeyboardMarkup:
        return InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        self._list_item_fn(e),
                        callback_data=f"{self._prefix}_pick:{e.id}",
                    ),
                ]
                for e in entities
            ],
        )

    # ── entry point ───────────────────────────────────────────────────────────

    async def handle_entry(
        self,
        update,
        user_id: int,
        entity_id: int | None = None,
        **filter_kwargs: Any,
    ) -> None:
        """Called from skill: show specific entity or selection list."""
        from schoolai.db.connection import get_db_session

        async with get_db_session() as session:
            if entity_id is not None:
                entity = await session.get(self._model, entity_id)
                if entity:
                    await update.message.reply_text(
                        self._summary_fn(entity),
                        parse_mode=ParseMode.MARKDOWN,
                        reply_markup=self._edit_keyboard(entity),
                    )
                    return
            entities = await self._list_fn(session, **filter_kwargs)

        if not entities:
            await update.message.reply_text("No hay elementos para editar.")
            return

        await update.message.reply_text(
            self._list_label,
            reply_markup=self._pick_keyboard(entities),
        )

    # ── registration ──────────────────────────────────────────────────────────

    def register(self) -> "EditFlow[M]":
        """Register all callbacks + text interceptor. Returns self."""
        from schoolai.bot.callback_router import callback_router
        from schoolai.bot.text_interceptors import text_interceptors
        from schoolai.db.connection import get_db_session

        prefix = self._prefix
        model = self._model
        fields = self._fields
        toggles = self._toggles
        summary_fn = self._summary_fn
        edit_keyboard = self._edit_keyboard
        update_fn = self._update_fn
        store = self._store

        @callback_router.register(f"{prefix}_pick:")
        async def _pick(update, context) -> None:
            entity_id = int(update.callback_query.data.split(":")[1])
            await update.callback_query.answer()
            async with get_db_session() as session:
                entity = await session.get(model, entity_id)
            if not entity:
                await update.callback_query.edit_message_text("No encontrado.")
                return
            await update.callback_query.edit_message_text(
                summary_fn(entity),
                parse_mode=ParseMode.MARKDOWN,
                reply_markup=edit_keyboard(entity),
            )

        @callback_router.register(f"{prefix}_field:")
        async def _field(update, context) -> None:
            parts = update.callback_query.data.split(":")
            entity_id, field_key = int(parts[1]), parts[2]
            await update.callback_query.answer()
            user_id = update.effective_user.id
            fdef = fields.get(field_key)
            if not fdef:
                return
            async with get_db_session() as session:
                entity = await session.get(model, entity_id)
            if not entity:
                return
            store.set(user_id, {"entity_id": entity_id, "field_key": field_key})
            await update.callback_query.edit_message_text(
                f"Escribe el/la {fdef.prompt}:",
                parse_mode=ParseMode.MARKDOWN,
            )

        @callback_router.register(f"{prefix}_toggle:")
        async def _toggle(update, context) -> None:
            parts = update.callback_query.data.split(":")
            entity_id, toggle_field = int(parts[1]), parts[2]
            await update.callback_query.answer()
            toggle = toggles.get(toggle_field)
            if not toggle:
                return
            async with get_db_session() as session:
                entity = await session.get(model, entity_id)
                if not entity:
                    await update.callback_query.edit_message_text("No encontrado.")
                    return
                new_val = not getattr(entity, toggle_field)
                entity = await update_fn(session, entity_id, **{toggle_field: new_val})
            if entity:
                await update.callback_query.edit_message_text(
                    summary_fn(entity),
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=edit_keyboard(entity),
                )

        @text_interceptors.register(priority=10, name=f"{prefix}_text")
        async def _text(update, user_id: int) -> bool:
            state = store.get(user_id)
            if not state:
                return False
            text_input = update.message.text.strip()
            fdef = fields.get(state["field_key"])
            if not fdef:
                store.clear(user_id)
                return False
            store.clear(user_id)

            if fdef.parse_fn:
                async with get_db_session() as session:
                    result = await fdef.parse_fn(text_input, session)
                if isinstance(result, str):
                    await update.message.reply_text(result, parse_mode=ParseMode.MARKDOWN)
                    return True
                kwargs = result
            else:
                kwargs = {fdef.key: text_input}

            async with get_db_session() as session:
                entity = await update_fn(session, state["entity_id"], **kwargs)

            if entity:
                logger.info(
                    f"[edit_flow:{prefix}] field={state['field_key']} "
                    f"entity={state['entity_id']} user={user_id}",
                )
                await update.message.reply_text(
                    f"✅ *{fdef.label}* actualizado.\n\n{summary_fn(entity)}",
                    parse_mode=ParseMode.MARKDOWN,
                    reply_markup=edit_keyboard(entity),
                )
            return True

        return self
