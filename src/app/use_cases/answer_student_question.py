import asyncio
import logging
from dataclasses import dataclass
from typing import AsyncIterator, Dict, List, Optional

from src.app.dtos.chat_dto import AnswerDTO, AnswerStream, QuestionInput, SourceDTO
from src.domain.entities.chat_session import Message
from src.domain.entities.document import DocumentChunk
from src.domain.ports import ChatCompleter, EmbeddingGenerator
from src.domain.repositories.chat_repository import ChatRepository
from src.domain.repositories.document_repository import DocumentRepository
from src.domain.service.prompt_builder_service import PromptBuilderService

logger = logging.getLogger(__name__)

NO_CONTEXT_MESSAGE = (
    "Não encontrei informações sobre esse tema no meu banco de dados de "
    "estudos. Tente especificar a matéria ou reformular a pergunta."
)

PROMPT_HISTORY_LIMIT = 10
EXCERPT_MAX_CHARS = 240


@dataclass(frozen=True)
class _Prepared:
    chunks: List[DocumentChunk]
    messages: Optional[List[Dict[str, str]]]  # None = nenhum trecho relevante


class AnswerStudentQuestionUseCase:
    def __init__(
        self,
        doc_repo: DocumentRepository,
        chat_repo: ChatRepository,
        embedding_generator: EmbeddingGenerator,
        chat_completer: ChatCompleter,
        top_k: int = 4,
    ):
        self.doc_repo = doc_repo
        self.chat_repo = chat_repo
        self.embedding_generator = embedding_generator
        self.chat_completer = chat_completer
        self.top_k = top_k

    async def execute(self, query: QuestionInput) -> AnswerDTO:
        prepared = await self._prepare(query)
        if prepared.messages is None:
            return AnswerDTO(session_id=query.session_id, answer=NO_CONTEXT_MESSAGE, sources=[])

        # Resposta do modelo de chat
        answer_text = await self.chat_completer.generate_chat_completion(prepared.messages, temperature=0.3)
        await self._save_exchange(query, answer_text)

        return AnswerDTO(
            session_id=query.session_id,
            answer=answer_text,
            sources=[self._to_source(c) for c in prepared.chunks],
        )

    async def stream(self, query: QuestionInput) -> AnswerStream:
        """Igual a `execute`, mas a resposta chega aos pedaços.

        A busca nos materiais acontece aqui, ANTES de devolver; assim, uma falha
        (ex.: Mongo fora do ar) ainda vira um erro HTTP normal. Falhas do modelo
        aparecem ao consumir `tokens`.
        """
        prepared = await self._prepare(query)

        if prepared.messages is None:
            async def no_context() -> AsyncIterator[str]:
                yield NO_CONTEXT_MESSAGE

            return AnswerStream(session_id=query.session_id, sources=[], tokens=no_context())

        async def tokens() -> AsyncIterator[str]:
            parts: List[str] = []
            async for piece in self.chat_completer.stream_chat_completion(prepared.messages, temperature=0.3):
                parts.append(piece)
                yield piece
            # Só chega aqui se o modelo terminou: resposta interrompida não entra no histórico.
            await self._save_exchange(query, "".join(parts).strip())

        return AnswerStream(
            session_id=query.session_id,
            sources=[self._to_source(c) for c in prepared.chunks],
            tokens=tokens(),
        )

    # ------------------------------------------------------------------ passos comuns
    async def _prepare(self, query: QuestionInput) -> "_Prepared":
        # 1. Histórico recente da conversa
        session = await self.chat_repo.get_session(query.session_id, limit=PROMPT_HISTORY_LIMIT)
        history = [{"role": m.role, "content": m.content} for m in session.messages]

        # 2. Busca vetorial dos chunks relevantes. Uma pergunta curta de acompanhamento
        # ("e a aceleração?") não tem assunto sozinho, então também se busca com a
        # pergunta anterior junto; os resultados das duas buscas são mesclados por score.
        retrieval_query = PromptBuilderService.build_retrieval_query(history, query.question)
        texts = [query.question] if retrieval_query == query.question else [query.question, retrieval_query]
        vectors = await self.embedding_generator.generate_embeddings(texts, purpose="query")
        result_lists = await asyncio.gather(
            *(
                self.doc_repo.search_similar_chunks(query_vector=v, top_k=self.top_k, subject=query.subject)
                for v in vectors
            )
        )
        chunks = PromptBuilderService.merge_ranked_chunks(result_lists, self.top_k)
        if not chunks:
            return _Prepared(chunks=[], messages=None)

        # 3. Prompt (regra de domínio isolada no PromptBuilderService)
        context_text = PromptBuilderService.build_context(chunks)
        messages = PromptBuilderService.build_messages(history, context_text, query.question)
        return _Prepared(chunks=chunks, messages=messages)

    async def _save_exchange(self, query: QuestionInput, answer_text: str) -> None:
        """Persiste a troca (pergunta + resposta) de uma vez só."""
        await self.chat_repo.add_messages(
            query.session_id,
            [
                Message(role="user", content=query.question),
                Message(role="assistant", content=answer_text),
            ],
        )

    @staticmethod
    def _to_source(chunk: DocumentChunk) -> SourceDTO:
        excerpt = " ".join(chunk.content.split())
        if len(excerpt) > EXCERPT_MAX_CHARS:
            excerpt = excerpt[: EXCERPT_MAX_CHARS - 1].rstrip() + "…"
        return SourceDTO(
            title=chunk.metadata.get("title", "Material"),
            subject=chunk.metadata.get("subject", "Geral"),
            excerpt=excerpt,
            score=chunk.metadata.get("score"),
        )
