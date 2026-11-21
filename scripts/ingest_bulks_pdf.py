import asyncio
import logging
import sys
from pathlib import Path

from src.infrastructure.config.settings import settings
from src.infrastructure.database.mongodb.connection import (
    connect_to_mongo,
    close_mongo_connection,
    db_context
)
from src.bootstrap import build_container
from src.infrastructure.database.mongodb.mongo_document_repo import MongoDocumentRepository
from src.domain.value_objects.subject import Subject

RAW_PDFS_DIR = Path("data/raw_pdfs")


async def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    # Por padrão pula PDFs já ingeridos (permite retomar após Ctrl+C/erro).
    # Use --force para reingerir tudo, substituindo os chunks antigos.
    force = "--force" in sys.argv

    await connect_to_mongo()

    container = await build_container(settings, db_context.db)
    use_case = container.ingest_material
    doc_repo = MongoDocumentRepository(db_context.db)

    pdf_files = list(RAW_PDFS_DIR.glob("*.pdf"))
    if not pdf_files:
        print(f" NENHUM arquivo .pdf encontrado na pasta '{RAW_PDFS_DIR}'. Cole os PDFs lá para ingerir.")
        await close_mongo_connection()
        return

    print(f" Encontrados {len(pdf_files)} PDF(s) em '{RAW_PDFS_DIR}'. Iniciando ingestão em lote...\n")

    for pdf_path in pdf_files:
        filename = pdf_path.stem
        # Nomenclatura esperada: "Fisica_Cinematica.pdf" -> Matéria = Fisica
        parts = filename.split("_")
        raw_subject = parts[0] if len(parts) > 1 else "Geral"
        title = filename.replace("_", " ")

        # Normaliza a matéria contra o enum Subject (ignora acentos/caixa e
        # cai em "Geral" se não reconhecer), garantindo que o valor gravado
        # seja idêntico ao usado no filtro de busca do chat.
        subject_enum = Subject.from_string(raw_subject)
        subject = subject_enum.value
        if subject_enum is Subject.GERAL and raw_subject.strip().lower() != "geral":
            print(f"⚠️  Matéria '{raw_subject}' não reconhecida, usando 'Geral' para '{filename}'.")

        if not force and await doc_repo.source_exists(pdf_path.name):
            print(f"⏭️  {filename} já ingerido, pulando (use --force para reingerir).")
            continue

        print(f"⏳ Ingerindo: {filename} (Matéria: {subject})...")
        try:
            chunks_count = await use_case.execute(
                pdf_path=str(pdf_path),
                subject=subject,
                title=title,
                source_name=pdf_path.name,
            )
            print(f" {filename} processado com sucesso! ({chunks_count} chunks gravados no MongoDB)")
        except Exception as e:
            print(f"❌ Erro ao ingerir {filename}: {e}")

    await close_mongo_connection()

if __name__ == "__main__":
    asyncio.run(main())
