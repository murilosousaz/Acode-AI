from typing import List
from motor.motor_asyncio import AsyncIOMotorDatabase
from src.domain.entities.chat_session import ChatSession, Message
from src.domain.repositories.chat_repository import ChatRepository

class MongoChatRepository(ChatRepository):
    def __init__(self, db: AsyncIOMotorDatabase, collection_name: str = "chat_sessions"):
        self.collection = db[collection_name]

    async def get_session(self, user_id: str) -> ChatSession:
        doc = await self.collection.find_one({"user_id": user_id})
        if not doc:
            return ChatSession(user_id=user_id, messages=[])
        
        messages = [
            Message(role=m["role"], content=m["content"])
            for m in doc.get("messages", [])[-10:]  # Retorna no máximo as últimas 10 mensagens
        ]
        return ChatSession(user_id=user_id, messages=messages)

    async def add_message(self, user_id: str, message: Message) -> None:
        await self.collection.update_one(
            {"user_id": user_id},
            {
                "$push": {
                    "messages": {
                        "$each": [{"role": message.role, "content": message.content}],
                        "$slice": -20  # Mantém no máximo 20 mensagens salvas no banco
                    }
                }
            },
            upsert=True
        )

    async def clear_history(self, user_id: str) -> None:
        await self.collection.delete_one({"user_id": user_id})