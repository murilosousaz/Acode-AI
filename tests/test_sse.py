"""Protocolo SSE do streaming (`src/presentation/api/sse.py`).

Usa só Starlette + o caso de uso real com dublês: sem FastAPI, Mongo nem Ollama.
"""

import json

from starlette.applications import Starlette
from starlette.routing import Route
from starlette.testclient import TestClient

from src.app.dtos.chat_dto import QuestionInput
from src.app.use_cases.answer_student_question import NO_CONTEXT_MESSAGE, AnswerStudentQuestionUseCase
from src.presentation.api.sse import AI_UNAVAILABLE_DETAIL, event_stream, format_event, sse_response
from tests.fakes import EmptyDocRepo, ExplodingAI, FakeAI, FakeChatRepo, FakeDocRepo, MidStreamFailAI
from tests.sse_helpers import parse_events


def make_app(doc_repo=None, ai=None, heartbeat=15.0):
    chat_repo = FakeChatRepo()
    ai = ai or FakeAI()
    use_case = AnswerStudentQuestionUseCase(doc_repo or FakeDocRepo(), chat_repo, ai, ai)

    async def stream(request):
        body = await request.json()
        answer = await use_case.stream(QuestionInput("s1", body["question"], body.get("subject")))
        return sse_response("s1", answer, heartbeat)

    app = Starlette(routes=[Route("/stream", stream, methods=["POST"])])
    return TestClient(app), chat_repo


def post(client, question="O que é velocidade média?"):
    return client.post("/stream", json={"question": question})


# ---------------------------------------------------------------- formato
def test_event_order_and_payloads():
    client, chat_repo = make_app()
    response = post(client)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["cache-control"] == "no-cache"
    assert response.headers["x-accel-buffering"] == "no"

    events = parse_events(response.text)
    assert [name for name, _ in events] == ["meta", "token", "token", "token", "done"]
    meta = events[0][1]
    assert meta["session_id"] == "s1"
    assert meta["sources"][0] == {
        "title": "Cinemática",
        "subject": "Fisica",
        "excerpt": meta["sources"][0]["excerpt"],
        "score": 0.91,
    }
    assert [d["text"] for n, d in events if n == "token"] == FakeAI.PIECES
    assert events[-1] == ("done", {})
    assert len(chat_repo.data["s1"]) == 2  # a troca foi gravada ao final


def test_unicode_and_line_breaks_survive_the_wire():
    class Poet(FakeAI):
        PIECES = ["Olá, ação!\n\n", "- item **um**\n", "linha com \"aspas\" e \\ barra"]

    client, _ = make_app(ai=Poet())
    tokens = [d["text"] for n, d in parse_events(post(client).text) if n == "token"]
    assert tokens == Poet.PIECES


def test_format_event_is_a_single_data_line():
    frame = format_event("token", {"text": "a\nb"})
    assert frame == 'event: token\ndata: {"text": "a\\nb"}\n\n'


# ---------------------------------------------------------------- sem contexto
def test_no_context_is_sent_as_one_token_without_sources():
    client, chat_repo = make_app(doc_repo=EmptyDocRepo())
    events = parse_events(post(client).text)
    assert [n for n, _ in events] == ["meta", "token", "done"]
    assert events[0][1]["sources"] == []
    assert events[1][1]["text"] == NO_CONTEXT_MESSAGE
    assert chat_repo.data == {}


# ---------------------------------------------------------------- falhas no meio
def test_model_failure_midway_sends_error_event_without_done_or_history():
    client, chat_repo = make_app(ai=MidStreamFailAI(after=2))
    response = post(client)

    assert response.status_code == 200  # o status já tinha sido enviado
    events = parse_events(response.text)
    assert [n for n, _ in events] == ["meta", "token", "token", "error"]
    assert events[-1][1] == {"status": 503, "detail": AI_UNAVAILABLE_DETAIL}
    assert "ollama down" not in response.text  # detalhe técnico fica no log
    assert chat_repo.data == {}


def test_unexpected_failure_midway_sends_generic_500_event():
    client, chat_repo = make_app(ai=ExplodingAI())
    events = parse_events(post(client).text)
    assert [n for n, _ in events] == ["meta", "error"]
    assert events[-1][1] == {"status": 500, "detail": "Erro interno do servidor."}
    assert "falha inesperada" not in json.dumps(events)
    assert chat_repo.data == {}


# ---------------------------------------------------------------- heartbeat e desconexão
def test_heartbeat_comments_keep_the_connection_alive_during_long_silences():
    client, _ = make_app(ai=FakeAI(piece_delay=0.25), heartbeat=0.05)
    response = post(client)
    assert response.text.count(": ping\n\n") >= 3
    # e os eventos continuam íntegros
    assert [d["text"] for n, d in parse_events(response.text) if n == "token"] == FakeAI.PIECES
    assert parse_events(response.text)[-1][0] == "done"


async def test_closing_the_stream_early_saves_nothing():
    """Cliente desconectou no meio: o gerador é fechado e a resposta parcial não vai para o histórico."""
    chat_repo = FakeChatRepo()
    ai = FakeAI(piece_delay=0.01)
    use_case = AnswerStudentQuestionUseCase(FakeDocRepo(), chat_repo, ai, ai)
    answer = await use_case.stream(QuestionInput("s1", "pergunta"))

    frames = event_stream("s1", answer, heartbeat=0.5)
    assert (await frames.__anext__()).startswith("event: meta")
    assert (await frames.__anext__()).startswith("event: token")
    await frames.aclose()

    assert chat_repo.data == {}
