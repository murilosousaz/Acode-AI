from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


@dataclass
class Student:
    """Representa um aluno (usuário do Discord) que interage com o tutor.

    Ainda não é persistida em uma coleção própria — hoje o histórico de
    conversas (`ChatSession`) já é suficiente para o funcionamento do bot.
    Esta entidade fica disponível para futuras funcionalidades que exijam
    dados de perfil (ex.: matéria preferida padrão, estatísticas de uso,
    um comando `/perfil`), sem precisar redesenhar o domínio depois.
    """

    discord_id: str
    display_name: str
    preferred_subject: Optional[str] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
