import logging
from typing import List, Optional

from motor.motor_asyncio import AsyncIOMotorDatabase

from src.domain.entities.document import DocumentChunk
from src.domain.repositories.document_repository import DocumentRepository

logger = logging.getLogger(__name__)


class MongoDocumentRepository(DocumentRepository):
    """Implementação da persistência de chunks usando MongoDB Atlas Vector Search.

    Requer um índice de busca vetorial chamado "vector_index" na coleção
    (ver scripts/create_vector_index.py) para que `search_similar_chunks`
    funcione via agregação $vectorSearch.
    """

    def __init__(
        self,
        db: AsyncIOMotorDatabase,
        collection_name: str = "document_chunks",
        vector_index_name: str = "vector_index",
    ):
        self.collection = db[collection_name]
        self.vector_index_name = vector_index_name

    async def save_chunks(self, chunks: List[DocumentChunk]) -> List[str]:
        if not chunks:
            return []

        documents = [
            {
                "content": chunk.content,
                "embedding": chunk.embedding,
                "metadata": chunk.metadata,
            }
            for chunk in chunks
        ]

        result = await self.collection.insert_many(documents)
        logger.info("Inseridos %d chunks na coleção '%s'.", len(result.inserted_ids), self.collection.name)
        return [str(_id) for _id in result.inserted_ids]

    async def search_similar_chunks(
        self,
        query_vector: List[float],
        top_k: int = 5,
        subject: Optional[str] = None,
    ) -> List[DocumentChunk]:
        vector_search_stage = {
            "$vectorSearch": {
                "index": self.vector_index_name,
                "path": "embedding",
                "queryVector": query_vector,
                # Buscar um universo maior de candidatos que o top_k final
                # melhora a qualidade do ranking (recomendação do MongoDB).
                "numCandidates": max(top_k * 20, 100),
                "limit": top_k,
            }
        }

        if subject:
            vector_search_stage["$vectorSearch"]["filter"] = {
                "metadata.subject": subject
            }

        pipeline = [
            vector_search_stage,
            {
                "$project": {
                    "content": 1,
                    "metadata": 1,
                    "score": {"$meta": "vectorSearchScore"},
                }
            },
        ]

        try:
            cursor = self.collection.aggregate(pipeline)
            results = await cursor.to_list(length=top_k)
        except Exception:
            logger.exception("Falha ao executar busca vetorial no MongoDB.")
            raise

        return [
            DocumentChunk(
                content=doc.get("content", ""),
                embedding=[],  # não é necessário retornar o vetor para o consumidor
                metadata=doc.get("metadata", {}) | {"score": doc.get("score")},
                chunk_id=str(doc.get("_id")),
            )
            for doc in results
        ]
