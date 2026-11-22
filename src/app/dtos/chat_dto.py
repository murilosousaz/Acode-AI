from dataclasses import dataclass, field
from typing import AsyncIterator, List, Optional


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


@dataclass
class AnswerStream:
    """Resposta em andamento. A busca nos materiais já foi feita (por isso `sources`
    já é conhecido); `tokens` entrega o texto aos pedaços e, só se terminar
    inteiro, grava a troca no histórico."""

    session_id: str
    sources: List[SourceDTO]
    tokens: AsyncIterator[str]
