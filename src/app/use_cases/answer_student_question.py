import logging
from typing import Optional

from src.domain.entities.chat_session import Message
from src.domain.repositories.document_repository import DocumentRepository
from src.domain.repositories.chat_repository import ChatRepository
from src.domain.service.prompt_builder_service import PromptBuilderService
from src.infrastructure.adapters.openai_adapter import OpenAIAdapter

logger = logging.getLogger(__name__)

NO_CONTEXT_MESSAGE = (
    "Não encontrei informações sobre esse tema no meu banco de dados de "
    "estudos. Tente especificar a matéria ou reformular a pergunta."
)


class AnswerStudentQuestionUseCase:
    def __init__(
        self,
        doc_repo: DocumentRepository,
        chat_repo: ChatRepository,
        openai_adapter: OpenAIAdapter,
        chat_model: str = "gpt-4o-mini",
        embedding_model: str = "text-embedding-3-small",
        top_k: int = 4,
    ):
        self.doc_repo = doc_repo
        self.chat_repo = chat_repo
        self.openai_adapter = openai_adapter
        self.chat_model = chat_model
        self.embedding_model = embedding_model
        self.top_k = top_k

    async def execute(self, user_id: str, question: str, subject: Optional[str] = None) -> str:
        # 1. Recupera o histórico de conversas do aluno
        session = await self.chat_repo.get_session(user_id)

        # 2. Gera embedding e busca chunks relevantes no MongoDB
        query_vectors = await self.openai_adapter.generate_embeddings(
            [question], model=self.embedding_model
        )
        relevant_chunks = await self.doc_repo.search_similar_chunks(
            query_vector=query_vectors[0],
            top_k=self.top_k,
            subject=subject,
        )

        if not relevant_chunks:
            return NO_CONTEXT_MESSAGE

        # 3. Monta o contexto e as mensagens (regra de domínio isolada no
        # PromptBuilderService, fora da camada de aplicação).
        context_text = PromptBuilderService.build_context(relevant_chunks)
        history = [{"role": msg.role, "content": msg.content} for msg in session.messages]
        messages = PromptBuilderService.build_messages(history, context_text, question)

        # 4. Chama o modelo de chat
        response = await self.openai_adapter.client.chat.completions.create(
            model=self.chat_model,
            messages=messages,
            temperature=0.3,
        )

        answer_text = response.choices[0].message.content.strip()

        # 5. Salva as mensagens no histórico
        await self.chat_repo.add_message(user_id, Message(role="user", content=question))
        await self.chat_repo.add_message(user_id, Message(role="assistant", content=answer_text))

        return answer_text
