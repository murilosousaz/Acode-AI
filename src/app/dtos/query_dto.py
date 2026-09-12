from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class QueryDTO:
    """Dados de entrada para o caso de uso de responder a dúvida de um aluno.

    Isolar esses campos em um DTO evita que o caso de uso cresça com
    parâmetros soltos e deixa explícito qual é o contrato de entrada da
    camada de aplicação, independente de vir do Discord, de uma CLI ou de
    qualquer outra interface no futuro.
    """

    user_id: str
    question: str
    subject: Optional[str] = None
