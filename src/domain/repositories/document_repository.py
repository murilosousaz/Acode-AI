from abc import ABC, abstractmethod
from typing import List
from src.domain.entities.document import Chunk

class DocumentRepository(ABC):
    @abstractmethod
    async def save_chunks(self, chunks: List[Chunk]) -> int:
        """Salva uma lista de chunks vetorializados no banco de dados."""
        pass

    @abstractmethod
    async def search_similar_chunks(
        self, query_vector: List[float], top_k: int = 5, subject: str | None = None
    ) -> List[Chunk]:
        """Realiza busca por similaridade vetorial."""
        pass