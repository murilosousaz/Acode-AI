from typing import List, Sequence

from src.domain.entities.document import DocumentChunk


def build_chunks(
    texts: Sequence[str],
    vectors: Sequence[List[float]],
    *,
    title: str,
    subject: str,
    source_file: str,
    embedding_model: str,
    document_prefix: str,
) -> List[DocumentChunk]:
    """Monta os chunks a gravar, registrando COMO foram vetorizados.

    O registro (`embedding_model` e `embedding_document_prefix`) permite avisar quando o
    prefixo/modelo configurado hoje difere do usado na ingestão (ver
    CheckEmbeddingCompatibilityUseCase).
    """
    if len(texts) != len(vectors):
        raise ValueError(f"{len(texts)} textos, mas {len(vectors)} vetores.")
    return [
        DocumentChunk(
            content=text,
            embedding=vector,
            metadata={
                "title": title,
                "subject": subject,
                "chunk_index": i,
                "source_file": source_file,
                "embedding_model": embedding_model,
                "embedding_document_prefix": document_prefix,
            },
        )
        for i, (text, vector) in enumerate(zip(texts, vectors))
    ]
