from typing import List
from src.domain.entities.chat_session import Message
from src.domain.repositories.document_repository import DocumentRepository
from src.domain.repositories.chat_repository import ChatRepository
from src.infrastructure.adapters.openai_adapter import OpenAIAdapter

class AnswerStudentQuestionUseCase:
    def __init__(
        self,
        doc_repo: DocumentRepository,
        chat_repo: ChatRepository,
        openai_adapter: OpenAIAdapter,
        model_name: str = "gpt-4o-mini"
    ):
        self.doc_repo = doc_repo
        self.chat_repo = chat_repo
        self.openai_adapter = openai_adapter
        self.model_name = model_name

    async def execute(self, user_id: str, question: str, subject: str | None = None) -> str:
        # 1. Recupera o histórico de conversas do aluno
        session = await self.chat_repo.get_session(user_id)

        # 2. Gera embedding e busca chunks no MongoDB
        query_vectors = await self.openai_adapter.generate_embeddings([question])
        relevant_chunks = await self.doc_repo.search_similar_chunks(
            query_vector=query_vectors[0],
            top_k=4,
            subject=subject
        )

        if not relevant_chunks:
            return " Não encontrei informações sobre esse tema no meu banco de dados de estudos. Tente especificar a matéria ou reformular a pergunta."

        # 3. Monta o contexto dos documentos
        context_text = "\n\n---\n\n".join(
            [f"[{c.metadata.get('title', 'Material')} - {c.metadata.get('subject', 'Geral')}]:\n{c.content}" for c in relevant_chunks]
        )

        # 4. Estrutura a lista de mensagens para a OpenAI (com histórico)
        system_prompt = (
            "Você é o AcodeAI, um tutor de IA didático, motivador e especialista em vestibulares (ENEM, FUVEST, etc.).\n"
            "Responda à dúvida do estudante de forma clara, objetiva e estruturada.\n\n"
            "REGRAS:\n"
            "1. Baseie-se APENAS no 'CONTEXTO' fornecido.\n"
            "2. Utilize o histórico da conversa para entender perguntas de acompanhamento.\n"
            "3. Destaque conceitos em **negrito** e use listas com marcadores quando apropriado."
        )

        messages = [{"role": "system", "content": system_prompt}]

        # Adiciona histórico anterior
        for msg in session.messages:
            messages.append({"role": msg.role, "content": msg.content})

        # Adiciona contexto e pergunta atual
        current_user_content = f"CONTEXTO DOS LIVROS/APOSTILAS:\n{context_text}\n\nDÚVIDA DO ESTUDANTE:\n{question}"
        messages.append({"role": "user", "content": current_user_content})

        # 5. Chama o modelo GPT
        response = await self.openai_adapter.client.chat.completions.create(
            model=self.model_name,
            messages=messages,
            temperature=0.3
        )

        answer_text = response.choices[0].message.content.strip()

        # 6. Salva as mensagens no histórico
        await self.chat_repo.add_message(user_id, Message(role="user", content=question))
        await self.chat_repo.add_message(user_id, Message(role="assistant", content=answer_text))

        return answer_text