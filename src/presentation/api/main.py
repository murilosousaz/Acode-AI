import logging
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.bootstrap import Container, build_container
from src.infrastructure.config.settings import settings
from src.infrastructure.database.mongodb.connection import (
    close_mongo_connection,
    connect_to_mongo,
    db_context,
)
from src.presentation.api.errors import register_exception_handlers
from src.presentation.api.routers import chat, documents, meta

API_PREFIX = "/api/v1"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


def create_app(container: Optional[Container] = None) -> FastAPI:
    """Fábrica da aplicação. Passar `container` (ex.: nos testes) pula a
    conexão com o MongoDB e usa as dependências fornecidas."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if container is not None:
            app.state.container = container
            yield
            return

        await connect_to_mongo()
        app.state.container = await build_container(settings, db_context.db)
        try:
            yield
        finally:
            await close_mongo_connection()

    app = FastAPI(
        title="AcodeAI API",
        description="Tutor de vestibular com RAG (MongoDB Vector Search + Ollama).",
        version="1.0.0",
        lifespan=lifespan,
    )

    cors_origins = container.settings.cors_origins if container else settings.cors_origins
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "X-API-Key"],
        expose_headers=["Retry-After"],
    )
    register_exception_handlers(app)

    app.include_router(meta.health_router)
    app.include_router(meta.api_router, prefix=API_PREFIX)
    app.include_router(chat.router, prefix=API_PREFIX)
    app.include_router(documents.router, prefix=API_PREFIX)
    return app


app = create_app()
