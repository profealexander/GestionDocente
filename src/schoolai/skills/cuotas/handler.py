"""Re-exports de los sub-handlers de cuotas.

main.py y skill.py importan desde aquí — sin cambios en los callers.
"""

from schoolai.skills.cuotas.handler_create import (
    handle_add_grade_callback,
    handle_create,
    handle_cuota_add_callback,
    handle_cuota_addall_callback,
    handle_cuota_done_callback,
    handle_cuota_names_text,
    handle_cuota_pick_callback,
)
from schoolai.skills.cuotas.handler_edit import handle_edit
from schoolai.skills.cuotas.handler_pago import (
    handle_cuota_pago_callback,
    handle_pago,
)
from schoolai.skills.cuotas.handler_query import (
    handle_cuota_sel_callback,
    handle_export,
    handle_list,
    handle_query,
)

__all__ = [
    # create
    "handle_create",
    "handle_cuota_add_callback",
    "handle_cuota_pick_callback",
    "handle_cuota_addall_callback",
    "handle_cuota_done_callback",
    "handle_cuota_names_text",
    "handle_add_grade_callback",
    # edit
    "handle_edit",
    # pago
    "handle_pago",
    "handle_cuota_pago_callback",
    # query
    "handle_list",
    "handle_query",
    "handle_export",
    "handle_cuota_sel_callback",
]
