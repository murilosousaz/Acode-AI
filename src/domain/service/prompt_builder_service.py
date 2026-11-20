from typing import Dict, Iterable, List

from src.domain.entities.document import DocumentChunk

SYSTEM_PROMPT = (
    "Você é o AcodeAI, um tutor de IA didático, motivador e especialista em "
    "vestibulares (ENEM, FUVEST, etc.).\n"
    "Responda à dúvida do estudante de forma clara, objetiva e estruturada.\n\n"
    "REGRAS:\n"
    "1. Baseie-se APENAS no 'CONTEXTO' fornecido.\n"
    "2. Se o contexto não for suficiente para responder com segurança, diga "
    "isso claramente em vez de inventar informações.\n"
    "3. Utilize o histórico da conversa para entender perguntas de "
    "acompanhamento.\n"
    "4. Destaque conceitos em **negrito** e use listas com marcadores quando "
    "apropriado."
)


class PromptBuilderService:
    """Serviço de domínio responsável por montar o prompt enviado ao modelo,
    isolando essa regra de negócio dos casos de uso da camada de aplicação."""

    @staticmethod
    def build_context(chunks: Iterable[DocumentChunk]) -> str:
        return "\n\n---\n\n".join(
            f"[{c.metadata.get('title', 'Material')} - {c.metadata.get('subject', 'Geral')}]:\n{c.content}"
            for c in chunks
        )

    @staticmethod
    def build_messages(
        history: Iterable[Dict[str, str]],
        context_text: str,
        question: str,
    ) -> List[Dict[str, str]]:
        messages: List[Dict[str, str]] = [{"role": "system", "content": SYSTEM_PROMPT}]
        messages.extend(history)

        user_content = (
            f"CONTEXTO DOS LIVROS/APOSTILAS:\n{context_text}\n\n"
            f"DÚVIDA DO ESTUDANTE:\n{question}"
        )
        messages.append({"role": "user", "content": user_content})
        return messages
