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

async def main():
    if len(sys.argv) < 4:
        print("Uso incorreto. Exemplo:\n uv run python -m scripts.ingest_cli <caminho_pdf> <materia> <titulo>")
        sys.exit(1)

    pdf_path = sys.argv[1]
    subject = sys.argv[2]
    title = sys.argv[3]

    await connect_to_mongo()

    doc_repo = MongoDocumentRepository(db_context.db)
    openai_adapter = OpenAIAdapter(api_key=settings.OPENAI_API_KEY)

    use_case = IngestEducationalMaterialUseCase(doc_repo, openai_adapter)
    
    print(f"🚀 Iniciando ingestão do PDF: {pdf_path}...")
    await use_case.execute(pdf_path=pdf_path, subject=subject, title=title)

    await close_mongo_connection()

if __name__ == "__main__":
    asyncio.run(main())