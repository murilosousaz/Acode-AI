import logging
import os
from typing import List

from langchain_text_splitters import RecursiveCharacterTextSplitter

from src.domain.entities.document import DocumentChunk
from src.domain.repositories.document_repository import DocumentRepository
from src.infrastructure.adapters.pymupdf_adapter import PyMuPDFAdapter
from src.infrastructure.adapters.openai_adapter import OpenAIAdapter

logger = logging.getLogger(__name__)


class IngestEducationalMaterialUseCase:
    def __init__(
        self,
        doc_repo: DocumentRepository,
        openai_adapter: OpenAIAdapter,
        embedding_model: str = "text-embedding-3-small",
        chunk_size: int = 800,
        chunk_overlap: int = 150,
    ):
        self.doc_repo = doc_repo
        self.openai_adapter = openai_adapter
        self.embedding_model = embedding_model
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=["\n\n", "\n", ". ", " ", ""],
        )

    async def execute(self, pdf_path: str, subject: str, title: str) -> int:
        if not os.path.exists(pdf_path):
            raise FileNotFoundError(f"Arquivo não encontrado: {pdf_path}")

        # 1. Extração de texto via PyMuPDF
        raw_text = PyMuPDFAdapter.extract_text_from_pdf(pdf_path)
        if not raw_text.strip():
            logger.warning("PDF '%s' não retornou texto extraível (pode ser digitalizado/imagem).", pdf_path)
            return 0

        # 2. Divisão em chunks
        text_chunks = self.text_splitter.split_text(raw_text)
        if not text_chunks:
            return 0

        # 3. Geração de embeddings
        embeddings = await self.openai_adapter.generate_embeddings(
            text_chunks, model=self.embedding_model
        )

        # 4. Construção das entidades de domínio
        documents_to_insert: List[DocumentChunk] = [
            DocumentChunk(
                content=chunk,
                embedding=vector,
                metadata={
                    "title": title,
                    "subject": subject,
                    "chunk_index": i,
                    "source_path": pdf_path,
                },
            )
            for i, (chunk, vector) in enumerate(zip(text_chunks, embeddings))
        ]

        # 5. Persistência no banco
        inserted_ids = await self.doc_repo.save_chunks(documents_to_insert)
        return len(inserted_ids)
