import logging

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = logging.getLogger(__name__)

INTERNAL_ERROR_DETAIL = "Erro interno do servidor."


class UnhandledErrorMiddleware:
    """Converte exceções não tratadas em um 500 JSON *dentro* da cadeia do CORS.

    O Starlette responde exceções genéricas pelo `ServerErrorMiddleware`, que fica
    FORA do `CORSMiddleware`: o 500 sai sem `Access-Control-Allow-Origin` e o
    navegador só mostra "Failed to fetch", escondendo o erro do frontend.

    Ordem: `add_middleware` coloca o último adicionado na camada mais externa.
    Portanto este middleware deve ser adicionado ANTES do CORSMiddleware.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        response_started = False

        async def tracking_send(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, receive, tracking_send)
        except Exception:
            logger.exception("Erro não tratado em %s %s", scope.get("method"), scope.get("path"))
            if response_started:
                # Não dá para trocar uma resposta já iniciada (ex.: streaming).
                raise
            response = JSONResponse({"detail": INTERNAL_ERROR_DETAIL}, status_code=500)
            await response(scope, receive, send)
