"""Entry point for the Gateway HTTP service (puerto 8001, separado de la API v1)."""
import uvicorn

from schoolai.config import settings


def run() -> None:
    uvicorn.run(
        "schoolai.gateway.app:app",
        host=settings.api_host,
        port=8001,
        reload=settings.debug,
    )


if __name__ == "__main__":
    run()
