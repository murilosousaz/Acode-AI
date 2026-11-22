import asyncio
import logging
import os
from typing import List, Optional

from langchain_text_splitters import RecursiveCharacterTextSplitter

from src.domain.ports import EmbeddingGenerator
from src.domain.repositories.document_repository import DocumentRepository
from src.domain.service.chunk_factory import build_chunks
from src.infrastructure.adapters.pymupdf_adapter import PyMuPDFAdapter

logger = logging.getLogger(__name__)


class IngestEducationalMaterialUseCase:
    def __init__(
        self,
        doc_repo: DocumentRepository,
        embedding_generator: EmbeddingGenerator,
        chunk_size: int = 800,
        chunk_overlap: int = 150,
    ):
        self.doc_repo = doc_repo
        self.embedding_generator = embedding_generator
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=["\n\n", "\n", ". ", " ", ""],
        )

    def _extract_and_split(self, pdf_path: str) -> List[str]:
        # Trabalho de CPU (PyMuPDF + splitter): roda em thread separada para
        # não travar o event loop da API enquanto processa um PDF grande.
        raw_text = PyMuPDFAdapter.extract_text_from_pdf(pdf_path)
        if not raw_text.strip():
            return []
        return self.text_splitter.split_text(raw_text)

    async def execute(
        self,
        pdf_path: str,
        subject: str,
        title: str,
        source_name: Optional[str] = None,
    ) -> int:
        """Ingere um PDF e devolve a quantidade de chunks gravados.

        `source_name` é o nome original do arquivo (em uploads, `pdf_path` é
        um arquivo temporário sem significado); por padrão usa o basename.
        """
        if not os.path.exists(pdf_path):
            raise FileNotFoundError(f"Arquivo não encontrado: {pdf_path}")

        text_chunks = await asyncio.to_thread(self._extract_and_split, pdf_path)
        if not text_chunks:
            logger.warning("PDF '%s' não retornou texto extraível (pode ser digitalizado/imagem).", title)
            return 0

        logger.info("'%s': %d chunks extraídos, gerando embeddings...", title, len(text_chunks))
        embeddings = await self.embedding_generator.generate_embeddings(text_chunks)

        source = source_name or os.path.basename(pdf_path)
        documents = build_chunks(
            text_chunks,
            embeddings,
            title=title,
            subject=subject,
            source_file=source,
            embedding_model=self.embedding_generator.embedding_model,
            document_prefix=self.embedding_generator.document_prefix,
        )

        # Reingerir o mesmo material substitui os chunks antigos (só depois de
        # os embeddings novos estarem prontos, para não perder dados se falhar).
        removed = await self.doc_repo.delete_by_source(title, source)
        if removed:
            logger.info("'%s': %d chunks antigos substituídos.", title, removed)

        inserted_ids = await self.doc_repo.save_chunks(documents)
        return len(inserted_ids)
