"""bot/action — paquete de acción, reemplaza action_handler.py.

Re-exports públicos para retrocompatibilidad con importadores existentes.
Los callbacks se registran automáticamente al importar este paquete.
"""

from schoolai.bot.action.callbacks import (  # noqa: F401
    handle_act_callback,
    handle_act_confirm_callback,
    handle_course_action_callback,
)
from schoolai.bot.action.cache import pop_pending, store_pending  # noqa: F401
from schoolai.bot.action.dispatcher import handle_extraction  # noqa: F401
from schoolai.bot.action.selection import (  # noqa: F401
    handle_selection_callback,
    resolve_selection_text,
)
