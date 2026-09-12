import os
from typing import List
from langchain_text_splitters import RecursiveCharacterTextSplitter

from src.domain.entities.document import DocumentChunk
from src.domain.repositories.document_repository import DocumentRepository
from src.infrastructure.adapters.pymupdf_adapter import PyMuPDFAdapter
from src.infrastructure.adapters.openai_adapter import OpenAIAdapter

class IngestEducationalMaterialUseCase:
    def __init__(
        self,
        doc_repo: DocumentRepository,
        openai_adapter: OpenAIAdapter,
        chunk_size: int = 800,
        chunk_overlap: int = 150
    ):
        self.doc_repo = doc_repo
        self.openai_adapter = openai_adapter
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=["\n\n", "\n", ". ", " ", ""]
        )

    async def execute(self, pdf_path: str, subject: str, title: str) -> int:
        if not os.path.exists(pdf_path):
            raise FileNotFoundError(f"Arquivo não encontrado: {pdf_path}")

        # 1. Extração de texto via PyMuPDF
        raw_text = PyMuPDFAdapter.extract_text_from_pdf(pdf_path)
        if not raw_text.strip():
            return 0

        # 2. Divisão em chunks
        text_chunks = self.text_splitter.split_text(raw_text)

        # 3. Geração de Embeddings
        embeddings = await self.openai_adapter.generate_embeddings(text_chunks)

        # 4. Construção das entidades de domínio
        documents_to_insert: List[DocumentChunk] = []
        for i, (chunk, vector) in enumerate(zip(text_chunks, embeddings)):
            doc = DocumentChunk(
                content=chunk,
                embedding=vector,
                metadata={
                    "title": title,
                    "subject": subject,
                    "chunk_index": i,
                    "source_path": pdf_path
                }
            )
            documents_to_insert.append(doc)

        # 5. Persistência no banco
        inserted_ids = await self.doc_repo.save_chunks(documents_to_insert)
        return len(inserted_ids)