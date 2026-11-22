from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class EmbeddingStamp:
    """Quantos chunks do banco foram vetorizados com certa configuração.

    `None` = o chunk é anterior ao registro dessa informação.
    """

    model: Optional[str]
    document_prefix: Optional[str]
    count: int
