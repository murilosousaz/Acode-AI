"""Server-Sent Events para a resposta do tutor em streaming.

Protocolo (`POST /api/v1/chat/messages/stream`, `Content-Type: text/event-stream`):

    event: meta    data: {"session_id": "...", "sources": [{title, subject, excerpt, score}]}
    event: token   data: {"text": "pedaço da resposta"}      (zero ou mais)
    event: done    data: {}                                    (fim normal)
    event: error   data: {"status": 503, "detail": "..."}     (falha no meio; sem `done`)

Linhas que começam com ":" são comentários (heartbeat) e devem ser ignoradas.
Erros ANTES do primeiro byte (422, 429, falha na busca...) seguem como respostas HTTP normais.

Este módulo só depende do Starlette, para ser testável sem o restante da aplicação.
"""

import asyncio
import json
import logging
from dataclasses import asdict
from typing import Any, AsyncIterator, Dict

from starlette.responses import StreamingResponse

from src.app.dtos.chat_dto import AnswerStream
from src.domain.errors import AIServiceUnavailableError
from src.presentation.api.middleware import INTERNAL_ERROR_DETAIL

logger = logging.getLogger(__name__)

AI_UNAVAILABLE_DETAIL = "O serviço de IA está indisponível no momento. Tente novamente em instantes."

# Proxies (nginx: 60 s) fecham conexões "mudas". Enquanto o modelo carrega pode haver
# um silêncio longo, então enviamos um comentário SSE de tempos em tempos.
HEARTBEAT_SECONDS = 15.0
_HEARTBEAT_FRAME = ": ping\n\n"
_HEARTBEAT = object()


def format_event(event: str, data: Dict[str, Any]) -> str:
    # json.dumps escapa quebras de linha, então "data" cabe sempre em uma única linha.
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


async def _with_heartbeat(source: AsyncIterator[str], interval: float) -> AsyncIterator[Any]:
    """Repassa os itens de `source`; a cada `interval` s sem novidade, emite `_HEARTBEAT`."""
    iterator = source.__aiter__()
    pending = asyncio.ensure_future(iterator.__anext__())
    try:
        while True:
            done, _ = await asyncio.wait({pending}, timeout=interval)
            if not done:
                yield _HEARTBEAT
                continue
            try:
                item = pending.result()
            except StopAsyncIteration:
                return
            yield item
            pending = asyncio.ensure_future(iterator.__anext__())
    finally:
        pending.cancel()


async def event_stream(session_id: str, answer: AnswerStream, heartbeat: float = HEARTBEAT_SECONDS) -> AsyncIterator[str]:
    yield format_event("meta", {"session_id": session_id, "sources": [asdict(s) for s in answer.sources]})
    try:
        async for piece in _with_heartbeat(answer.tokens, heartbeat):
            yield _HEARTBEAT_FRAME if piece is _HEARTBEAT else format_event("token", {"text": piece})
    except AIServiceUnavailableError as exc:
        # Igual ao handler HTTP: o detalhe técnico só vai para o log.
        logger.error("Serviço de IA indisponível durante o streaming: %s", exc)
        yield format_event("error", {"status": 503, "detail": AI_UNAVAILABLE_DETAIL})
    except Exception:
        logger.exception("Erro não tratado durante o streaming da resposta")
        yield format_event("error", {"status": 500, "detail": INTERNAL_ERROR_DETAIL})
    else:
        yield format_event("done", {})


def sse_response(session_id: str, answer: AnswerStream, heartbeat: float = HEARTBEAT_SECONDS) -> StreamingResponse:
    return StreamingResponse(
        event_stream(session_id, answer, heartbeat),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # nginx: não acumular a resposta antes de enviar
        },
    )
