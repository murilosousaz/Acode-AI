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


# Até este número de palavras, a pergunta pode ser "de acompanhamento" ("e a
# aceleração?", "dê um exemplo", "explique melhor"): sozinha ela não diz sobre o
# que é, então a busca também considera o assunto da pergunta anterior.
FOLLOW_UP_MAX_WORDS = 6
FOLLOW_UP_CONTEXT_MAX_CHARS = 500


class PromptBuilderService:
    """Serviço de domínio responsável por montar o prompt enviado ao modelo,
    isolando essa regra de negócio dos casos de uso da camada de aplicação."""

    @staticmethod
    def build_retrieval_query(history: Iterable[Dict[str, str]], question: str) -> str:
        """Texto de busca que inclui o assunto da conversa.

        Perguntas curtas de acompanhamento não têm assunto próprio: vetorizadas
        sozinhas, recuperam trechos aleatórios. Para elas, devolve a pergunta
        precedida da última pergunta do aluno. Perguntas longas (ou a primeira da
        conversa) já se bastam e voltam inalteradas.

        Como uma pergunta curta também pode ser um assunto novo, o chamador deve
        buscar com a pergunta pura E com esta, e mesclar (`merge_ranked_chunks`).
        """
        if len(question.split()) > FOLLOW_UP_MAX_WORDS:
            return question

        previous = next(
            (m["content"] for m in reversed(list(history)) if m.get("role") == "user"),
            None,
        )
        if not previous or not previous.strip():
            return question
        return f"{previous.strip()[:FOLLOW_UP_CONTEXT_MAX_CHARS]}\n{question}"

    @staticmethod
    def merge_ranked_chunks(result_lists: Iterable[List[DocumentChunk]], limit: int) -> List[DocumentChunk]:
        """Une resultados de várias buscas: remove trechos repetidos (fica o de
        maior score) e devolve os `limit` mais relevantes. Em empate, mantém a
        ordem de chegada, que dá preferência à primeira busca da lista."""

        def score(chunk: DocumentChunk) -> float:
            return chunk.metadata.get("score") or 0.0

        best: Dict[str, DocumentChunk] = {}
        for chunks in result_lists:
            for chunk in chunks:
                key = chunk.chunk_id or chunk.content
                if key not in best or score(chunk) > score(best[key]):
                    best[key] = chunk
        return sorted(best.values(), key=score, reverse=True)[:limit]

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
