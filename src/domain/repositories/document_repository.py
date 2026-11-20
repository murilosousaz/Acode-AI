from abc import ABC, abstractmethod
from typing import List, Optional

from src.domain.entities.document import DocumentChunk


class DocumentRepository(ABC):
    @abstractmethod
    async def save_chunks(self, chunks: List[DocumentChunk]) -> List[str]:
        """Salva uma lista de chunks vetorizados no banco de dados.

        Retorna a lista de IDs gerados para os documentos inseridos.
        """
        raise NotImplementedError

    @abstractmethod
    async def search_similar_chunks(
        self,
        query_vector: List[float],
        top_k: int = 5,
        subject: Optional[str] = None,
    ) -> List[DocumentChunk]:
        """Realiza busca por similaridade vetorial (kNN) nos chunks armazenados."""
        raise NotImplementedError
