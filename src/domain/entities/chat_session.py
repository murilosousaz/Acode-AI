from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List


@dataclass
class Message:
    role: str  # "user" ou "assistant"
    content: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class ChatSession:
    session_id: str
    messages: List[Message] = field(default_factory=list)
