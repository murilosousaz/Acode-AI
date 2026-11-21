"""Dublês de teste em Python puro (sem FastAPI/Mongo/Ollama).

Ficam separados do conftest.py para que os testes de caso de uso rodem sem
importar a aplicação web.
"""

from typing import Dict, List, Optional

from src.domain.entities.chat_session import ChatSession, Message
from src.domain.entities.document import DocumentChunk
from src.domain.errors import AIServiceUnavailableError
from src.domain.repositories.chat_repository import ChatRepository
from src.domain.repositories.document_repository import DocumentRepository


class FakeDocRepo(DocumentRepository):
    def __init__(self):
        self.saved: List[DocumentChunk] = []
        self.last_subject: Optional[str] = None

    async def save_chunks(self, chunks):
        self.saved.extend(chunks)
        return [str(i) for i in range(len(chunks))]

    async def source_exists(self, source_file):
        return any(c.metadata.get("source_file") == source_file for c in self.saved)

    async def delete_by_source(self, title, source_file):
        before = len(self.saved)
        self.saved = [
            c for c in self.saved
            if not (c.metadata.get("title") == title and c.metadata.get("source_file") == source_file)
        ]
        return before - len(self.saved)

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
        self.embed_calls: List[List[str]] = []

    async def generate_embeddings(self, texts):
        self.embed_calls.append(list(texts))
        if self.fail:
            raise AIServiceUnavailableError("ollama down")
        return [[0.1] * 4 for _ in texts]

    async def generate_chat_completion(self, messages, temperature=0.3):
        self.chat_calls.append(messages)
        return "A velocidade média é **Δs/Δt**."


class ScriptedDocRepo(FakeDocRepo):
    """Devolve, a cada busca, a próxima lista de `scripted` (na ordem das chamadas)."""

    def __init__(self, scripted: List[List[DocumentChunk]]):
        super().__init__()
        self.scripted = list(scripted)
        self.calls: List[Optional[str]] = []

    async def search_similar_chunks(self, query_vector, top_k=5, subject=None):
        self.calls.append(subject)
        return self.scripted[len(self.calls) - 1]


class ExplodingAI(FakeAI):
    """Falha com um erro inesperado (não tratado pela API) ao gerar a resposta."""

    async def generate_chat_completion(self, messages, temperature=0.3):
        raise RuntimeError("falha inesperada do modelo")


def chunk(content: str, score: float, chunk_id: Optional[str] = None, title: str = "Cinemática", subject: str = "Fisica"):
    return DocumentChunk(
        content=content,
        embedding=[],
        metadata={"title": title, "subject": subject, "score": score},
        chunk_id=chunk_id,
    )
