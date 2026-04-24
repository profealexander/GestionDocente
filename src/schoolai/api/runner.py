import uvicorn

from schoolai.config import settings
from schoolai.logging import setup_logging


def run() -> None:
    setup_logging("api")
    uvicorn.run(
        "schoolai.api.main:app",
        host=settings.api_host,
        port=settings.effective_api_port,
        reload=settings.debug,
        log_config=None,  # desactiva el log_config de uvicorn — loguru toma el control
    )
