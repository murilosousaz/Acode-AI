from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Response
from fastapi.responses import StreamingResponse

from src.app.dtos.chat_dto import QuestionInput
from src.bootstrap import Container
from src.presentation.api.deps import enforce_rate_limit, get_container
from src.presentation.api.schemas import ChatRequest, ChatResponse, HistoryResponse, MessageOut, SourceOut
from src.presentation.api.sse import sse_response

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post(
    "/messages",
    response_model=ChatResponse,
    summary="Envia uma dúvida ao tutor",
    dependencies=[Depends(enforce_rate_limit)],
)
async def send_message(body: ChatRequest, container: Container = Depends(get_container)) -> ChatResponse:
    session_id = body.session_id or uuid4()
    result = await container.answer_question.execute(
        QuestionInput(
            session_id=str(session_id),
            question=body.question,
            subject=body.subject.value if body.subject else None,
        )
    )
    return ChatResponse(
        session_id=session_id,
        answer=result.answer,
        sources=[SourceOut(**vars(s)) for s in result.sources],
    )


@router.post(
    "/messages/stream",
    summary="Envia uma dúvida e recebe a resposta em streaming (SSE)",
    description=(
        "Mesma entrada de `POST /messages`. A resposta é `text/event-stream` com os eventos "
        "`meta` (session_id e fontes), `token` (pedaços do texto), `done` ou `error`. "
        "Erros de validação, limite de perguntas (429) e falha na busca vêm como HTTP normal, "
        "antes do início do stream."
    ),
    response_class=StreamingResponse,
    responses={200: {"content": {"text/event-stream": {}}}},
    dependencies=[Depends(enforce_rate_limit)],
)
async def stream_message(body: ChatRequest, container: Container = Depends(get_container)) -> StreamingResponse:
    session_id = body.session_id or uuid4()
    answer = await container.answer_question.stream(
        QuestionInput(
            session_id=str(session_id),
            question=body.question,
            subject=body.subject.value if body.subject else None,
        )
    )
    return sse_response(str(session_id), answer)


@router.get("/sessions/{session_id}", response_model=HistoryResponse, summary="Histórico da conversa")
async def get_history(session_id: UUID, container: Container = Depends(get_container)) -> HistoryResponse:
    session = await container.get_history.execute(str(session_id))
    return HistoryResponse(
        session_id=session_id,
        messages=[MessageOut(role=m.role, content=m.content, timestamp=m.timestamp) for m in session.messages],
    )


@router.delete("/sessions/{session_id}", status_code=204, summary="Apaga o histórico da conversa")
async def clear_history(session_id: UUID, container: Container = Depends(get_container)) -> Response:
    await container.clear_history.execute(str(session_id))
    return Response(status_code=204)
