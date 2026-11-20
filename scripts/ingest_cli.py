import asyncio
import sys

from src.infrastructure.config.settings import settings
from src.infrastructure.database.mongodb.connection import (
    connect_to_mongo,
    close_mongo_connection,
    db_context
)
from src.bootstrap import build_container
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
    # valor gravado consistente com o filtro usado na busca do chat.
    subject_enum = Subject.from_string(raw_subject)
    subject = subject_enum.value
    if subject_enum is Subject.GERAL and raw_subject.strip().lower() != "geral":
        print(f"⚠️  Matéria '{raw_subject}' não reconhecida, usando 'Geral'.")

    await connect_to_mongo()

    container = await build_container(settings, db_context.db)
    use_case = container.ingest_material

    print(f"🚀 Iniciando ingestão do PDF: {pdf_path} (Matéria: {subject})...")
    inserted_count = await use_case.execute(pdf_path=pdf_path, subject=subject, title=title)
    print(f" Concluído! {inserted_count} chunks gravados no MongoDB.")

    await close_mongo_connection()

if __name__ == "__main__":
    asyncio.run(main())
