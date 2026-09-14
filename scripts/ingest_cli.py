import asyncio
import sys

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


async def main():
    if len(sys.argv) < 4:
        print("Uso incorreto. Exemplo:\n uv run python -m scripts.ingest_cli <caminho_pdf> <materia> <titulo>")
        print("Matérias reconhecidas: " + ", ".join(s.value for s in Subject))
        sys.exit(1)

    pdf_path = sys.argv[1]
    raw_subject = sys.argv[2]
    title = sys.argv[3]

    # Normaliza a matéria informada contra o enum Subject, para manter o
    # valor gravado consistente com o filtro usado no comando /duvida.
    subject_enum = Subject.from_string(raw_subject)
    subject = subject_enum.value
    if subject_enum is Subject.GERAL and raw_subject.strip().lower() != "geral":
        print(f"⚠️  Matéria '{raw_subject}' não reconhecida, usando 'Geral'.")

    await connect_to_mongo()

    doc_repo = MongoDocumentRepository(db_context.db)
    embedding_adapter = OpenAIAdapter(
        api_key=settings.GOOGLE_API_KEY, base_url=settings.GOOGLE_EMBEDDING_BASE_URL
    )

    use_case = IngestEducationalMaterialUseCase(
        doc_repo,
        embedding_adapter,
        embedding_model=settings.GOOGLE_EMBEDDING_MODEL,
        embedding_dimensions=settings.EMBEDDING_DIMENSIONS,
    )

    print(f"🚀 Iniciando ingestão do PDF: {pdf_path} (Matéria: {subject})...")
    inserted_count = await use_case.execute(pdf_path=pdf_path, subject=subject, title=title)
    print(f" Concluído! {inserted_count} chunks gravados no MongoDB.")

    await close_mongo_connection()

if __name__ == "__main__":
    asyncio.run(main())
