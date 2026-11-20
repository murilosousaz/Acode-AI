from datetime import datetime, timezone
from typing import List, Optional

from motor.motor_asyncio import AsyncIOMotorDatabase

from src.domain.entities.chat_session import ChatSession, Message
from src.domain.repositories.chat_repository import ChatRepository

MAX_STORED_MESSAGES = 20


class MongoChatRepository(ChatRepository):
    def __init__(self, db: AsyncIOMotorDatabase, collection_name: str = "chat_sessions"):
        self.collection = db[collection_name]

    async def ensure_indexes(self) -> None:
        # Índice parcial: documentos antigos (chaveados por `user_id`, da era
        # Discord) não têm `session_id` e não entram no índice único.
        await self.collection.create_index(
            "session_id",
            unique=True,
            partialFilterExpression={"session_id": {"$type": "string"}},
        )

    async def get_session(self, session_id: str, limit: Optional[int] = None) -> ChatSession:
        doc = await self.collection.find_one({"session_id": session_id})
        if not doc:
            return ChatSession(session_id=session_id, messages=[])

        raw = doc.get("messages", [])
        if limit is not None:
            raw = raw[-limit:]

        return ChatSession(
            session_id=session_id,
            messages=[
                Message(
                    role=m["role"],
                    content=m["content"],
                    timestamp=self._as_utc(m.get("timestamp")),
                )
                for m in raw
            ],
        )

    async def add_messages(self, session_id: str, messages: List[Message]) -> None:
        if not messages:
            return
        await self.collection.update_one(
            {"session_id": session_id},
            {
                "$push": {
                    "messages": {
                        "$each": [
                            {"role": m.role, "content": m.content, "timestamp": m.timestamp}
                            for m in messages
                        ],
                        "$slice": -MAX_STORED_MESSAGES,
                    }
                },
                "$set": {"updated_at": datetime.now(timezone.utc)},
            },
            upsert=True,
        )

    async def clear_history(self, session_id: str) -> None:
        await self.collection.delete_one({"session_id": session_id})

    @staticmethod
    def _as_utc(value: Optional[datetime]) -> datetime:
        # O Mongo devolve datetimes "naive" (UTC) por padrão.
        if value is None:
            return datetime.now(timezone.utc)
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
