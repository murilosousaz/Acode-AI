import asyncio
from pathlib import Path

from src.infrastructure.config.settings import settings
from src.infrastructure.database.mongodb.connection import (
    connect_to_mongo,
    close_mongo_connection,
    db_context
)
from src.infrastructure.database.mongodb.mongo_document_repo import MongoDocumentRepository
from src.infrastructure.adapters.openai_adapter import OpenAIAdapter
from src.app.use_cases.ingest_educational_material import IngestEducationalMaterialUseCase
from src.domain.value_objects.subject import Subject

RAW_PDFS_DIR = Path("data/raw_pdfs")


async def main():
    await connect_to_mongo()

    doc_repo = MongoDocumentRepository(db_context.db)
    openai_adapter = OpenAIAdapter(api_key=settings.OPENAI_API_KEY)
    use_case = IngestEducationalMaterialUseCase(
        doc_repo, openai_adapter, embedding_model=settings.OPENAI_EMBEDDING_MODEL
    )

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
        # seja idêntico ao usado no filtro do comando /duvida.
        subject_enum = Subject.from_string(raw_subject)
        subject = subject_enum.value
        if subject_enum is Subject.GERAL and raw_subject.strip().lower() != "geral":
            print(f"⚠️  Matéria '{raw_subject}' não reconhecida, usando 'Geral' para '{filename}'.")

        print(f"⏳ Ingerindo: {filename} (Matéria: {subject})...")
        try:
            chunks_count = await use_case.execute(
                pdf_path=str(pdf_path),
                subject=subject,
                title=title
            )
            print(f" {filename} processado com sucesso! ({chunks_count} chunks gravados no MongoDB)")
        except Exception as e:
            print(f"❌ Erro ao ingerir {filename}: {e}")

    await close_mongo_connection()

if __name__ == "__main__":
    asyncio.run(main())
