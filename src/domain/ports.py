"""Portas (contratos) para serviços de IA.

Os casos de uso dependem apenas destes Protocols; a implementação concreta
(Ollama) fica na camada de infraestrutura.
"""

from typing import AsyncIterator, Dict, List, Literal, Protocol

# "document": texto que vai para o banco (ingestão). "query": pergunta do aluno.
# Alguns modelos (ex.: nomic-embed-text) rendem mais com um prefixo diferente para cada papel.
EmbeddingPurpose = Literal["document", "query"]


class EmbeddingGenerator(Protocol):
    # Como os vetores são produzidos; gravado junto de cada chunk para detectar, depois,
    # material vetorizado com outra configuração.
    embedding_model: str
    query_prefix: str
    document_prefix: str

    async def generate_embeddings(
        self, texts: List[str], purpose: EmbeddingPurpose = "document"
    ) -> List[List[float]]:
        """Gera um vetor por texto, na mesma ordem da entrada."""
        ...


class ChatCompleter(Protocol):
    async def generate_chat_completion(
        self, messages: List[Dict[str, str]], temperature: float = 0.3
    ) -> str:
        """Gera a resposta do assistente a partir de uma lista de mensagens."""
        ...

    def stream_chat_completion(
        self, messages: List[Dict[str, str]], temperature: float = 0.3
    ) -> AsyncIterator[str]:
        """Como `generate_chat_completion`, mas devolve a resposta aos pedaços,
        conforme o modelo a escreve. Falhas levantam AIServiceUnavailableError."""
        ...
