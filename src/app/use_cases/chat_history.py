from src.domain.entities.chat_session import ChatSession
from src.domain.repositories.chat_repository import ChatRepository


class GetChatHistoryUseCase:
    def __init__(self, chat_repo: ChatRepository):
        self.chat_repo = chat_repo

    async def execute(self, session_id: str) -> ChatSession:
        return await self.chat_repo.get_session(session_id)


class ClearChatHistoryUseCase:
    def __init__(self, chat_repo: ChatRepository):
        self.chat_repo = chat_repo

    async def execute(self, session_id: str) -> None:
        await self.chat_repo.clear_history(session_id)
