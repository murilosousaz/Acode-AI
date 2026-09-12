import asyncio
from src.infrastructure.config.settings import settings
from src.infrastructure.database.mongodb.connection import (
    connect_to_mongo,
    close_mongo_connection,
    db_context,
)

async def create_vector_index():
    await connect_to_mongo()
    db = db_context.db
    collection = db["document_chunks"]

    search_index_definition = {
        "name": "vector_index",
        "type": "vectorSearch",
        "definition": {
            "fields": [
                {
                    "type": "vector",
                    "path": "embedding",
                    "numDimensions": 1536,
                    "similarity": "cosine"
                },
                {
                    "type": "filter",
                    "path": "metadata.subject"
                }
            ]
        }
    }

    try:
        await collection.create_search_index(model=search_index_definition)
        print(" Índice vetorial 'vector_index' criado com sucesso no MongoDB!")
    except Exception as e:
        print(f"❌ Erro ao criar índice vetorial: {e}")
    finally:
        await close_mongo_connection()

if __name__ == "__main__":
    asyncio.run(create_vector_index())