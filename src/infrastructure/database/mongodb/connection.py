from motor.motor_asyncio import AsyncIOMotorClient
from src.infrastructure.config.settings import settings

class MongoDB:
    client: AsyncIOMotorClient | None = None
    db = None

db_context = MongoDB()

async def connect_to_mongo():
    db_context.client = AsyncIOMotorClient(settings.MONGO_URI)
    db_context.db = db_context.client[settings.MONGO_DB_NAME]
    print(" Conectado ao MongoDB Atlas com sucesso!")

async def close_mongo_connection():
    if db_context.client:
        db_context.client.close()
        print(" Conexão com MongoDB encerrada.")