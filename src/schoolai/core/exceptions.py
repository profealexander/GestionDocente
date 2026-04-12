"""Excepciones personalizadas del proyecto SchoolAI."""


class SchoolAIError(Exception):
    """Excepción base para todos los errores de SchoolAI."""


class ToolExecutionError(SchoolAIError):
    """Error al ejecutar una tool del orchestrator."""


class ExternalServiceError(SchoolAIError):
    """Error en servicio externo (Redis, WhatsApp API, LLM API)."""
