"""Raiz de composição: monta repositórios, adaptadores e casos de uso."""

from dataclasses import dataclass
from typing import Awaitable, Callable, Dict

from src.app.use_cases.answer_student_question import AnswerStudentQuestionUseCase
from src.app.use_cases.chat_history import ClearChatHistoryUseCase, GetChatHistoryUseCase
from src.app.use_cases.ingest_educational_material import IngestEducationalMaterialUseCase
from src.infrastructure.adapters.ollama_adapter import OllamaAdapter
from src.infrastructure.adapters.rate_limiter import SlidingWindowRateLimiter
from src.infrastructure.config.settings import Settings
from src.infrastructure.database.mongodb.mongo_chat_repo import MongoChatRepository
from src.infrastructure.database.mongodb.mongo_document_repo import MongoDocumentRepository


@dataclass
class Container:
    settings: Settings
    answer_question: AnswerStudentQuestionUseCase
    ingest_material: IngestEducationalMaterialUseCase
    get_history: GetChatHistoryUseCase
    clear_history: ClearChatHistoryUseCase
    rate_limiter: SlidingWindowRateLimiter
    # Verificações usadas por GET /health/ready: cada uma levanta exceção se falhar.
    readiness_checks: Dict[str, Callable[[], Awaitable[None]]]


async def build_container(settings: Settings, db) -> Container:
    doc_repo = MongoDocumentRepository(db)
    chat_repo = MongoChatRepository(db)
    await chat_repo.ensure_indexes()

    ollama = OllamaAdapter(
        base_url=settings.OLLAMA_BASE_URL,
        chat_model=settings.OLLAMA_CHAT_MODEL,
        embedding_model=settings.OLLAMA_EMBEDDING_MODEL,
        embedding_dimensions=settings.EMBEDDING_DIMENSIONS,
        max_tokens=settings.OLLAMA_MAX_TOKENS,
        timeout=settings.OLLAMA_TIMEOUT_SECONDS,
    )

    async def ping_mongo() -> None:
        await db.command("ping")

    return Container(
        settings=settings,
        answer_question=AnswerStudentQuestionUseCase(doc_repo, chat_repo, ollama, ollama),
        ingest_material=IngestEducationalMaterialUseCase(doc_repo, ollama),
        get_history=GetChatHistoryUseCase(chat_repo),
        clear_history=ClearChatHistoryUseCase(chat_repo),
        rate_limiter=SlidingWindowRateLimiter(
            requests_limit=settings.RATE_LIMIT_REQUESTS,
            window_seconds=settings.RATE_LIMIT_WINDOW_SECONDS,
        ),
        readiness_checks={"mongodb": ping_mongo, "ollama": ollama.ping},
    )
