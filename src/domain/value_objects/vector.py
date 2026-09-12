import math
from dataclasses import dataclass
from typing import List, Sequence


@dataclass(frozen=True)
class Vector:
    """Value object que representa um vetor de embedding.

    Encapsula validações básicas (não vazio, todos os componentes
    numéricos, dimensão consistente ao comparar dois vetores) e a regra de
    similaridade por cosseno, mantendo essa lógica de domínio isolada de
    detalhes de infraestrutura (MongoDB, OpenAI, etc.).
    """

    values: List[float]

    def __post_init__(self) -> None:
        if not self.values:
            raise ValueError("Vector não pode ser vazio.")
        if not all(isinstance(v, (int, float)) for v in self.values):
            raise TypeError("Todos os componentes do Vector devem ser numéricos.")

    @property
    def dimensions(self) -> int:
        return len(self.values)

    def cosine_similarity(self, other: "Vector") -> float:
        if self.dimensions != other.dimensions:
            raise ValueError(
                f"Vetores com dimensões diferentes não podem ser comparados "
                f"({self.dimensions} != {other.dimensions})."
            )

        dot_product = sum(a * b for a, b in zip(self.values, other.values))
        norm_self = math.sqrt(sum(a * a for a in self.values))
        norm_other = math.sqrt(sum(b * b for b in other.values))

        if norm_self == 0 or norm_other == 0:
            return 0.0

        return dot_product / (norm_self * norm_other)

    @classmethod
    def from_sequence(cls, values: Sequence[float]) -> "Vector":
        return cls(values=list(values))
