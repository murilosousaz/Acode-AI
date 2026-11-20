from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from src.domain.value_objects.subject import Subject

MAX_QUESTION_CHARS = 2000


class ChatRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=MAX_QUESTION_CHARS, description="Dúvida do estudante.")
    subject: Optional[Subject] = Field(None, description="Filtra o material por matéria (valores de GET /subjects).")
    session_id: Optional[UUID] = Field(
        None,
        description="Identifica a conversa. Omita na primeira pergunta: a API cria um e devolve na resposta.",
    )

    @field_validator("question")
    @classmethod
    def _strip_not_blank(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("A pergunta não pode ficar em branco.")
        return v


class SourceOut(BaseModel):
    title: str
    subject: str
    excerpt: str
    score: Optional[float] = None


class ChatResponse(BaseModel):
    session_id: UUID
    answer: str
    sources: List[SourceOut]


class MessageOut(BaseModel):
    role: str
    content: str
    timestamp: datetime


class HistoryResponse(BaseModel):
    session_id: UUID
    messages: List[MessageOut]


class SubjectOut(BaseModel):
    value: str
    label: str


class IngestResponse(BaseModel):
    title: str
    subject: str
    filename: str
    chunks_created: int
