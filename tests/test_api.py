import uuid

import pymupdf

from tests.conftest import EmptyDocRepo, FakeAI, FakeDocRepo

API = "/api/v1"


def make_pdf(text: str = "Cinemática: velocidade média e aceleração. " * 30) -> bytes:
    doc = pymupdf.open()
    page = doc.new_page()
    page.insert_textbox(pymupdf.Rect(40, 40, 550, 800), text, fontsize=11)
    data = doc.tobytes()
    doc.close()
    return data


# ---------------------------------------------------------------- meta
def test_liveness(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_readiness_ok_and_failing(client_factory):
    assert client_factory().get("/health/ready").json()["status"] == "ready"

    async def boom():
        raise RuntimeError("down")

    async def ok():
        return None

    r = client_factory(readiness={"mongodb": ok, "ollama": boom}).get("/health/ready")
    assert r.status_code == 503
    assert r.json()["checks"] == {"mongodb": "ok", "ollama": "unavailable"}


def test_subjects(client):
    data = client.get(f"{API}/subjects").json()
    assert {"value": "Fisica", "label": "Física"} in data
    assert len(data) == 8


# ---------------------------------------------------------------- chat
def test_chat_creates_session_and_history_roundtrip(client):
    r = client.post(f"{API}/chat/messages", json={"question": "O que é velocidade média?", "subject": "Fisica"})
    assert r.status_code == 200
    body = r.json()
    sid = body["session_id"]
    uuid.UUID(sid)
    assert "Δs/Δt" in body["answer"]
    assert body["sources"][0]["title"] == "Cinemática"
    assert body["sources"][0]["score"] == 0.91
    assert len(body["sources"][0]["excerpt"]) <= 240

    hist = client.get(f"{API}/chat/sessions/{sid}").json()
    assert [m["role"] for m in hist["messages"]] == ["user", "assistant"]
    assert hist["messages"][0]["content"] == "O que é velocidade média?"

    # segunda pergunta na mesma sessão: o histórico entra no prompt
    r2 = client.post(f"{API}/chat/messages", json={"question": "E a aceleração?", "session_id": sid})
    assert r2.json()["session_id"] == sid
    assert len(client.get(f"{API}/chat/sessions/{sid}").json()["messages"]) == 4

    assert client.delete(f"{API}/chat/sessions/{sid}").status_code == 204
    assert client.get(f"{API}/chat/sessions/{sid}").json()["messages"] == []


def test_chat_passes_subject_filter_and_history_to_prompt():
    from fastapi.testclient import TestClient
    from src.presentation.api.main import create_app
    from tests.conftest import make_container

    repo, ai = FakeDocRepo(), FakeAI()
    with TestClient(create_app(make_container(doc_repo=repo, ai=ai))) as c:
        sid = c.post(f"{API}/chat/messages", json={"question": "Q1", "subject": "Fisica"}).json()["session_id"]
        c.post(f"{API}/chat/messages", json={"question": "Q2", "session_id": sid})
    assert repo.last_subject is None  # segunda pergunta sem filtro
    roles = [m["role"] for m in ai.chat_calls[1]]
    assert roles == ["system", "user", "assistant", "user"]


def test_chat_without_context_is_not_saved(client_factory):
    c = client_factory(doc_repo=EmptyDocRepo())
    body = c.post(f"{API}/chat/messages", json={"question": "algo"}).json()
    assert "Não encontrei" in body["answer"] and body["sources"] == []
    assert c.get(f"{API}/chat/sessions/{body['session_id']}").json()["messages"] == []


def test_chat_validation(client):
    post = lambda **b: client.post(f"{API}/chat/messages", json=b)  # noqa: E731
    assert post(question="").status_code == 422
    assert post(question="   ").status_code == 422
    assert post(question="x" * 2001).status_code == 422
    assert post(question="ok", subject="Culinaria").status_code == 422
    assert post(question="ok", session_id="não-é-uuid").status_code == 422
    assert client.get(f"{API}/chat/sessions/abc").status_code == 422


def test_chat_rate_limit(client_factory):
    c = client_factory(rate_limit=2)
    for _ in range(2):
        assert c.post(f"{API}/chat/messages", json={"question": "oi"}).status_code == 200
    r = c.post(f"{API}/chat/messages", json={"question": "oi"})
    assert r.status_code == 429
    assert int(r.headers["Retry-After"]) >= 1


def test_ai_unavailable_returns_503_without_leaking_details(client_factory):
    r = client_factory(ai=FakeAI(fail=True)).post(f"{API}/chat/messages", json={"question": "oi"})
    assert r.status_code == 503
    assert "ollama down" not in r.text


# ---------------------------------------------------------------- documents
def upload(c, content=None, name="Fisica_Cinematica.pdf", headers=None, subject="Fisica", title="Cinemática"):
    return c.post(
        f"{API}/documents",
        files={"file": (name, content if content is not None else make_pdf(), "application/pdf")},
        data={"subject": subject, "title": title},
        headers=headers if headers is not None else {"X-API-Key": "secret"},
    )


def test_upload_requires_admin_key(client_factory):
    c = client_factory()
    assert upload(c, headers={}).status_code == 401
    assert upload(c, headers={"X-API-Key": "errada"}).status_code == 401
    assert upload(client_factory(admin_key=""), headers={"X-API-Key": "x"}).status_code == 503


def test_upload_pdf_ok(client_factory):
    repo = FakeDocRepo()
    c = client_factory(doc_repo=repo)
    r = upload(c)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["subject"] == "Fisica" and body["filename"] == "Fisica_Cinematica.pdf"
    assert body["chunks_created"] == len(repo.saved) > 0
    meta = repo.saved[0].metadata
    assert meta["source_file"] == "Fisica_Cinematica.pdf" and "/tmp" not in str(meta)


def test_reupload_replaces_chunks_instead_of_duplicating(client_factory):
    repo = FakeDocRepo()
    c = client_factory(doc_repo=repo)
    first = upload(c).json()["chunks_created"]
    assert upload(c).status_code == 201
    assert len(repo.saved) == first


def test_upload_rejections(client_factory):
    c = client_factory(max_upload_mb=1)
    assert upload(c, content=b"isto nao e pdf").status_code == 415
    assert upload(c, content=b"").status_code in (400, 415, 422)
    assert upload(c, content=b"%PDF-1.4\n" + b"0" * (2 * 1024 * 1024)).status_code == 413
    assert upload(c, subject="Culinaria").status_code == 422
    # PDF válido porém sem texto (página em branco)
    blank = pymupdf.open()
    blank.new_page()
    assert upload(c, content=blank.tobytes()).status_code == 422


# ---------------------------------------------------------------- CORS
def test_cors_preflight(client):
    r = client.options(
        f"{API}/chat/messages",
        headers={"Origin": "http://front.test", "Access-Control-Request-Method": "POST",
                 "Access-Control-Request-Headers": "content-type"},
    )
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == "http://front.test"
    bad = client.options(
        f"{API}/chat/messages",
        headers={"Origin": "http://evil.test", "Access-Control-Request-Method": "POST"},
    )
    assert "access-control-allow-origin" not in bad.headers
