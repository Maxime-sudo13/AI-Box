from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI

from app import __version__
from app.api import actions, advisor, audit, auth, companies, connectors, documents, finance, health, setup, users
from app.config import get_settings


@asynccontextmanager
async def lifespan(_: FastAPI):
    from app.connectors import scheduler

    scheduler.start()
    yield
    scheduler.stop()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        lifespan=lifespan,
        title="Business AI Box",
        version=__version__,
        docs_url="/api/docs" if settings.debug else None,
        redoc_url=None,
        openapi_url="/api/openapi.json" if settings.debug else None,
    )
    api = APIRouter(prefix="/api")
    for module in (health, setup, auth, companies, users, audit, documents, finance, advisor, actions, connectors):
        api.include_router(module.router)
    app.include_router(api)
    return app


app = create_app()
