import os

# Precisa vir antes de importar qualquer módulo de `src` (settings é instanciado no import).
os.environ.setdefault("MONGO_URI", "mongodb://test")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from src.app.use_cases.answer_student_question import AnswerStudentQuestionUseCase  # noqa: E402
from src.app.use_cases.chat_history import ClearChatHistoryUseCase, GetChatHistoryUseCase  # noqa: E402
from src.app.use_cases.ingest_educational_material import IngestEducationalMaterialUseCase  # noqa: E402
from src.bootstrap import Container  # noqa: E402
from src.infrastructure.adapters.rate_limiter import SlidingWindowRateLimiter  # noqa: E402
from src.infrastructure.config.settings import Settings  # noqa: E402
from src.presentation.api.main import create_app  # noqa: E402
from tests.fakes import (  # noqa: E402,F401  (reexportados: test_api.py importa daqui)
    EmptyDocRepo,
    ExplodingAI,
    FakeAI,
    FakeChatRepo,
    FakeDocRepo,
)


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
