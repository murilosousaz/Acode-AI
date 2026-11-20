import asyncio
import logging

from pymongo.errors import CollectionInvalid, OperationFailure

from src.infrastructure.config.settings import settings
from src.infrastructure.database.mongodb.connection import (
    connect_to_mongo,
    close_mongo_connection,
    db_context,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("create_vector_index")

COLLECTION_NAME = "document_chunks"
INDEX_NAME = "vector_index"


async def _ensure_collection_exists(db) -> None:
    """A criação de um índice de busca vetorial no Atlas exige que a coleção
    já exista. Antes da primeira ingestão a coleção 'document_chunks' ainda
    não foi criada, então garantimos isso aqui explicitamente."""
    existing = await db.list_collection_names()
    if COLLECTION_NAME in existing:
        return
    try:
        await db.create_collection(COLLECTION_NAME)
        logger.info("Coleção '%s' criada.", COLLECTION_NAME)
    except CollectionInvalid:
        pass  # já existe (criada em paralelo) - sem problema


async def _wait_until_ready(collection, timeout_seconds: int = 90) -> None:
    """Faz polling do status do índice até ficar pronto ou até o timeout.

    A criação do índice no Atlas é assíncrona; tentar usá-lo em uma busca
    antes de ficar pronto resulta em erro ou resultados vazios. Se o polling
    falhar por qualquer motivo (ex.: diferença de API entre Atlas real e
    mongodb-atlas-local), apenas avisamos e seguimos, pois o índice já foi
    solicitado com sucesso.
    """
    elapsed = 0
    interval = 3
    try:
        while elapsed < timeout_seconds:
            indexes = await collection.list_search_indexes(INDEX_NAME).to_list(length=1)
            if indexes and indexes[0].get("status") == "READY":
                logger.info("✅ Índice '%s' está pronto para uso.", INDEX_NAME)
                return
            await asyncio.sleep(interval)
            elapsed += interval
        logger.warning(
            "Tempo de espera esgotado aguardando o índice ficar pronto. "
            "Ele pode ainda estar sendo construído em segundo plano; "
            "verifique no Atlas (ou tente ingerir depois de alguns instantes)."
        )
    except Exception:
        logger.info(
            "Não foi possível confirmar o status do índice automaticamente "
            "(normal em algumas versões do mongodb-atlas-local). O comando "
            "de criação já foi enviado com sucesso."
        )


async def create_vector_index():
    await connect_to_mongo()
    db = db_context.db

    try:
        await _ensure_collection_exists(db)
        collection = db[COLLECTION_NAME]

        search_index_definition = {
            "name": INDEX_NAME,
            "type": "vectorSearch",
            "definition": {
                "fields": [
                    {
                        "type": "vector",
                        "path": "embedding",
                        "numDimensions": settings.EMBEDDING_DIMENSIONS,
                        "similarity": "cosine",
                    },
                    {
                        "type": "filter",
                        "path": "metadata.subject",
                    },
                ]
            },
        }

        await collection.create_search_index(model=search_index_definition)
        print(f" Índice vetorial '{INDEX_NAME}' solicitado com sucesso (dimensões: {settings.EMBEDDING_DIMENSIONS}).")
        await _wait_until_ready(collection)
    except OperationFailure as e:
        if getattr(e, "code", None) == 68 or "already exists" in str(e).lower():
            print(f"ℹ️  Índice '{INDEX_NAME}' já existe, nada a fazer.")
        else:
            logger.exception("Erro ao criar índice vetorial: %s", e)
            raise
    except Exception as e:
        print(f"❌ Erro ao criar índice vetorial: {e}")
        raise
    finally:
        await close_mongo_connection()

if __name__ == "__main__":
    asyncio.run(create_vector_index())
