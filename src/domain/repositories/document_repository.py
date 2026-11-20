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

    @abstractmethod
    async def source_exists(self, source_file: str) -> bool:
        """Indica se já existem chunks gravados para o arquivo de origem."""
        raise NotImplementedError

    @abstractmethod
    async def delete_by_source(self, title: str, source_file: str) -> int:
        """Apaga os chunks de um material (mesmo título e arquivo de origem).

        Usado para que reingerir um PDF substitua os chunks antigos em vez de
        duplicá-los. Retorna quantos chunks foram apagados.
        """
        raise NotImplementedError
