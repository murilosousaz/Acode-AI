"""Portas (contratos) para serviços de IA.

Os casos de uso dependem apenas destes Protocols; a implementação concreta
(Ollama) fica na camada de infraestrutura.
"""

from typing import Dict, List, Protocol


class EmbeddingGenerator(Protocol):
    async def generate_embeddings(self, texts: List[str]) -> List[List[float]]:
        """Gera um vetor por texto, na mesma ordem da entrada."""
        ...


class ChatCompleter(Protocol):
    async def generate_chat_completion(
        self, messages: List[Dict[str, str]], temperature: float = 0.3
    ) -> str:
        """Gera a resposta do assistente a partir de uma lista de mensagens."""
        ...
