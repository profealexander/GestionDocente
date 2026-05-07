"""
Domain Router — Python puro. Selecciona el DomainController según el dominio del TaskSpec.
Sin LLM. Parte del Agent Runtime v2 (Gateway → Domain Router → Planner → Executor → Synthesizer).
"""
from __future__ import annotations

from schoolai.gateway.schemas import TaskSpec

from .domains.attendance import AttendanceController
from .domains.base import BaseDomainController
from .domains.general import GeneralController
from .domains.homework import HomeworkController
from .domains.reports import ReportsController

_CONTROLLERS: dict[str, BaseDomainController] = {
    "attendance": AttendanceController(),
    "homework": HomeworkController(),
    "reports": ReportsController(),
    "general": GeneralController(),
}


def route(task: TaskSpec) -> BaseDomainController:
    return _CONTROLLERS.get(task.domain, _CONTROLLERS["general"])
