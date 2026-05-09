"""FastAPI entry point."""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import approvals, audit, auth, projects, tasks, users, webhooks
from app.config import get_settings
from app.core.database import close_mongo_connection, connect_to_mongo
from app.core.logger import logger, setup_logging


@asynccontextmanager
async def lifespan(_: FastAPI):
    setup_logging()
    settings = get_settings()
    logger.info("Starting {} (env={})", settings.app_name, settings.environment)
    await connect_to_mongo()
    yield
    await close_mongo_connection()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description="AI-powered engineering operator accessible from WhatsApp.",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/")
    async def root():
        return {
            "name": settings.app_name,
            "version": "0.1.0",
            "status": "ok",
            "docs": "/docs",
        }

    @app.get("/healthz")
    async def healthz():
        return {"status": "ok"}

    api_prefix = settings.api_prefix
    app.include_router(auth.router, prefix=api_prefix)
    app.include_router(users.router, prefix=api_prefix)
    app.include_router(projects.router, prefix=api_prefix)
    app.include_router(tasks.router, prefix=api_prefix)
    app.include_router(approvals.router, prefix=api_prefix)
    app.include_router(audit.router, prefix=api_prefix)
    app.include_router(webhooks.router, prefix=api_prefix)

    return app


app = create_app()
