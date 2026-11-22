import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from src.domain.errors import AIServiceUnavailableError
from src.presentation.api.sse import AI_UNAVAILABLE_DETAIL

logger = logging.getLogger(__name__)


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AIServiceUnavailableError)
    async def ai_unavailable(request: Request, exc: AIServiceUnavailableError):
        # O detalhe técnico vai só para o log; o cliente recebe uma mensagem genérica.
        logger.error("Serviço de IA indisponível: %s", exc)
        return JSONResponse(
            status_code=503,
            content={"detail": AI_UNAVAILABLE_DETAIL},
        )

    @app.exception_handler(Exception)
    async def unexpected(request: Request, exc: Exception):
        logger.exception("Erro não tratado em %s %s", request.method, request.url.path)
        return JSONResponse(status_code=500, content={"detail": "Erro interno do servidor."})
