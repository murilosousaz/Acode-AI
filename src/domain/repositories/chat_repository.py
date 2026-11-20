from abc import ABC, abstractmethod
from typing import List, Optional

from src.domain.entities.chat_session import ChatSession, Message


class ChatRepository(ABC):
    @abstractmethod
    async def get_session(self, session_id: str, limit: Optional[int] = None) -> ChatSession:
        """Retorna a sessão (vazia se não existir). `limit` devolve só as
        últimas N mensagens; `None` devolve tudo o que está armazenado."""

    @abstractmethod
    async def add_messages(self, session_id: str, messages: List[Message]) -> None:
        """Acrescenta mensagens ao fim da sessão, criando-a se necessário."""

    @abstractmethod
    async def clear_history(self, session_id: str) -> None:
        """Apaga a sessão."""
