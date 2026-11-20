from dataclasses import dataclass, field
from typing import List, Optional


@dataclass(frozen=True)
class QuestionInput:
    """Entrada do caso de uso de responder a dúvida de um aluno."""

    session_id: str
    question: str
    subject: Optional[str] = None


@dataclass(frozen=True)
class SourceDTO:
    """Trecho de material usado como contexto da resposta."""

    title: str
    subject: str
    excerpt: str
    score: Optional[float] = None


@dataclass(frozen=True)
class AnswerDTO:
    session_id: str
    answer: str
    sources: List[SourceDTO] = field(default_factory=list)
