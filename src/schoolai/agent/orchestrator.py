"""
Router — Python puro. Selecciona el DomainController según el dominio del TaskSpec.
Sin LLM.
"""
from __future__ import annotations

from schoolai.gateway.schemas import TaskSpec

from .domains.attendance import AttendanceController
from .domains.base import BaseDomainController
from .domains.cuotas import CuotasController
from .domains.general import GeneralController
from .domains.homework import HomeworkController
from .domains.reports import ReportsController

_CONTROLLERS: dict[str, BaseDomainController] = {
    "attendance": AttendanceController(),
    "homework": HomeworkController(),
    "cuotas": CuotasController(),
    "reports": ReportsController(),
    "general": GeneralController(),
}


def route(task: TaskSpec) -> BaseDomainController:
    return _CONTROLLERS.get(task.domain, _CONTROLLERS["general"])
