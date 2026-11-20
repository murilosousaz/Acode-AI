import os

# Precisa vir antes de importar qualquer módulo de `src` (settings é instanciado no import).
os.environ.setdefault("MONGO_URI", "mongodb://test")

from typing import Dict, List, Optional  # noqa: E402

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from src.app.use_cases.answer_student_question import AnswerStudentQuestionUseCase  # noqa: E402
from src.app.use_cases.chat_history import ClearChatHistoryUseCase, GetChatHistoryUseCase  # noqa: E402
from src.app.use_cases.ingest_educational_material import IngestEducationalMaterialUseCase  # noqa: E402
from src.bootstrap import Container  # noqa: E402
from src.domain.entities.chat_session import ChatSession, Message  # noqa: E402
from src.domain.entities.document import DocumentChunk  # noqa: E402
from src.domain.errors import AIServiceUnavailableError  # noqa: E402
from src.domain.repositories.chat_repository import ChatRepository  # noqa: E402
from src.domain.repositories.document_repository import DocumentRepository  # noqa: E402
from src.infrastructure.adapters.rate_limiter import SlidingWindowRateLimiter  # noqa: E402
from src.infrastructure.config.settings import Settings  # noqa: E402
from src.presentation.api.main import create_app  # noqa: E402


class FakeDocRepo(DocumentRepository):
    def __init__(self):
        self.saved: List[DocumentChunk] = []
        self.last_subject: Optional[str] = None

    async def save_chunks(self, chunks):
        self.saved.extend(chunks)
        return [str(i) for i in range(len(chunks))]

    async def search_similar_chunks(self, query_vector, top_k=5, subject=None):
        self.last_subject = subject
        return [
            DocumentChunk(
                content="A velocidade média é a variação do espaço dividida pelo tempo. " * 10,
                embedding=[],
                metadata={"title": "Cinemática", "subject": "Fisica", "score": 0.91},
            )
        ]


class EmptyDocRepo(FakeDocRepo):
    async def search_similar_chunks(self, query_vector, top_k=5, subject=None):
        return []


class FakeChatRepo(ChatRepository):
    def __init__(self):
        self.data: Dict[str, List[Message]] = {}

    async def get_session(self, session_id, limit=None):
        msgs = self.data.get(session_id, [])
        return ChatSession(session_id, msgs[-limit:] if limit else list(msgs))

    async def add_messages(self, session_id, messages):
        self.data.setdefault(session_id, []).extend(messages)

    async def clear_history(self, session_id):
        self.data.pop(session_id, None)


class FakeAI:
    def __init__(self, fail: bool = False):
        self.fail = fail
        self.chat_calls: List[List[Dict[str, str]]] = []

    async def generate_embeddings(self, texts):
        if self.fail:
            raise AIServiceUnavailableError("ollama down")
        return [[0.1] * 4 for _ in texts]

    async def generate_chat_completion(self, messages, temperature=0.3):
        self.chat_calls.append(messages)
        return "A velocidade média é **Δs/Δt**."


def make_container(
    doc_repo=None, ai=None, admin_key="secret", rate_limit=100, max_upload_mb=1, readiness=None
) -> Container:
    doc_repo = doc_repo or FakeDocRepo()
    chat_repo = FakeChatRepo()
    ai = ai or FakeAI()
    settings = Settings(
        MONGO_URI="mongodb://test",
        ADMIN_API_KEY=admin_key,
        MAX_UPLOAD_MB=max_upload_mb,
        CORS_ALLOW_ORIGINS="http://front.test",
        _env_file=None,
    )

    async def ok():
        return None

    return Container(
        settings=settings,
        answer_question=AnswerStudentQuestionUseCase(doc_repo, chat_repo, ai, ai),
        ingest_material=IngestEducationalMaterialUseCase(doc_repo, ai),
        get_history=GetChatHistoryUseCase(chat_repo),
        clear_history=ClearChatHistoryUseCase(chat_repo),
        rate_limiter=SlidingWindowRateLimiter(requests_limit=rate_limit, window_seconds=60),
        readiness_checks=readiness or {"mongodb": ok, "ollama": ok},
    )


@pytest.fixture
def client_factory():
    clients = []

    def _make(**kwargs) -> TestClient:
        c = TestClient(create_app(make_container(**kwargs)), raise_server_exceptions=False)
        c.__enter__()
        clients.append(c)
        return c

    yield _make
    for c in clients:
        c.__exit__(None, None, None)


@pytest.fixture
def client(client_factory) -> TestClient:
    return client_factory()
