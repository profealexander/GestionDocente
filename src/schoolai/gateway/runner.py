"""Entry point for the Gateway HTTP service (puerto 8001, separado de la API v1)."""
import uvicorn

from schoolai.config import settings
from schoolai.logging import setup_logging


def run() -> None:
    setup_logging("gateway")
    uvicorn.run(
        "schoolai.gateway.app:app",
        host=settings.api_host,
        port=8001,
        reload=settings.debug,
        log_config=None,  # desactiva el log_config de uvicorn — loguru toma el control
    )


if __name__ == "__main__":
    run()
