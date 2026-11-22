"""Confere se os PDFs já ingeridos foram vetorizados com a configuração atual.

Use depois de mudar EMBEDDING_QUERY_PREFIX / EMBEDDING_DOCUMENT_PREFIX / o modelo:

    uv run python -m scripts.check_embeddings

Sai com código 1 se houver incompatibilidade (útil em scripts de deploy).
"""

import asyncio
import sys

from src.bootstrap import build_container
from src.infrastructure.config.settings import settings
from src.infrastructure.database.mongodb.connection import (
    close_mongo_connection,
    connect_to_mongo,
    db_context,
)


async def main() -> int:
    await connect_to_mongo()
    try:
        container = await build_container(settings, db_context.db)
        report = await container.check_embeddings.execute()
    finally:
        await close_mongo_connection()

    print(f"Modelo: {report.model} | prefixo de documento: {report.document_prefix!r}")
    print(f"Trechos no banco: {report.total} (desatualizados: {report.stale})")
    if report.ok:
        print("✅ Tudo certo: o banco foi vetorizado com a configuração atual.")
        return 0
    for line in report.lines():
        print(f"⚠️  {line}")
    return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
