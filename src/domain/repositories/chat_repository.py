from abc import ABC, abstractmethod
from src.domain.entities.chat_session import ChatSession, Message

class ChatRepository(ABC):
    @abstractmethod
    async def get_session(self, user_id: str) -> ChatSession:
        pass

    @abstractmethod
    async def add_message(self, user_id: str, message: Message) -> None:
        pass

    @abstractmethod
    async def clear_history(self, user_id: str) -> None:
        pass