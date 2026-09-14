import logging

from src.app.dtos.query_dto import QueryDTO
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
        embedding_adapter: OpenAIAdapter,
        chat_adapter: OpenAIAdapter,
        chat_model: str = "gpt-4o-mini",
        embedding_model: str = "text-embedding-3-small",
        embedding_dimensions: int | None = None,
        top_k: int = 4,
    ):
        self.doc_repo = doc_repo
        self.chat_repo = chat_repo
        # Dois adaptadores porque o provedor de embeddings (OpenAI) e o de
        # chat (ex.: DeepSeek) podem ser diferentes. Ambos implementam a
        # mesma interface (OpenAIAdapter), então cada um só é usado para o
        # método correspondente.
        self.embedding_adapter = embedding_adapter
        self.chat_adapter = chat_adapter
        self.chat_model = chat_model
        self.embedding_model = embedding_model
        # Tem que ser igual ao usado na ingestão — senão o vetor da
        # pergunta não tem a mesma dimensão dos chunks já gravados e a
        # busca no índice vetorial falha ou fica sem sentido.
        self.embedding_dimensions = embedding_dimensions
        self.top_k = top_k

    async def execute(self, query: QueryDTO) -> str:
        # 1. Recupera o histórico de conversas do aluno
        session = await self.chat_repo.get_session(query.user_id)

        # 2. Gera embedding e busca chunks relevantes no MongoDB
        query_vectors = await self.embedding_adapter.generate_embeddings(
            [query.question], model=self.embedding_model, dimensions=self.embedding_dimensions
        )
        relevant_chunks = await self.doc_repo.search_similar_chunks(
            query_vector=query_vectors[0],
            top_k=self.top_k,
            subject=query.subject,
        )

        if not relevant_chunks:
            return NO_CONTEXT_MESSAGE

        # 3. Monta o contexto e as mensagens (regra de domínio isolada no
        # PromptBuilderService, fora da camada de aplicação).
        context_text = PromptBuilderService.build_context(relevant_chunks)
        history = [{"role": msg.role, "content": msg.content} for msg in session.messages]
        messages = PromptBuilderService.build_messages(history, context_text, query.question)

        # 4. Chama o modelo de chat (encapsulado no adaptador, sem expor
        # detalhes do cliente da OpenAI à camada de aplicação)
        answer_text = await self.chat_adapter.generate_chat_completion(
            messages=messages,
            model=self.chat_model,
            temperature=0.3,
        )

        # 5. Salva as mensagens no histórico
        await self.chat_repo.add_message(query.user_id, Message(role="user", content=query.question))
        await self.chat_repo.add_message(query.user_id, Message(role="assistant", content=answer_text))

        return answer_text
