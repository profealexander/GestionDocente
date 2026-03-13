import uvicorn

from schoolai.config import settings


def run() -> None:
    uvicorn.run(
        "schoolai.api.main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.debug,
    )
