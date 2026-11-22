from dataclasses import dataclass, field
from typing import List

from src.domain.ports import EmbeddingGenerator
from src.domain.repositories.document_repository import DocumentRepository

REINGEST_HINT = "python -m scripts.ingest_bulks_pdf (ou reenvie os PDFs pela área do professor)"


@dataclass(frozen=True)
class EmbeddingCompatibility:
    model: str
    document_prefix: str
    total: int
    stale: int
    stale_groups: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.stale == 0 and not self.warnings

    def lines(self) -> List[str]:
        """Mensagens prontas para log/terminal (vazio se está tudo certo)."""
        lines = list(self.warnings)
        if self.stale:
            lines.append(
                f"{self.stale} de {self.total} trechos foram vetorizados com uma configuração diferente "
                f"da atual (modelo '{self.model}', prefixo de documento {self.document_prefix!r}). "
                f"A busca fica pior até reingerir os PDFs: {REINGEST_HINT}. "
                f"Detalhe: {'; '.join(self.stale_groups)}."
            )
        return lines


class CheckEmbeddingCompatibilityUseCase:
    """Confere se os vetores guardados foram feitos como a configuração atual os faria.

    Ligar/desligar prefixos de embedding (ou trocar o modelo) sem reingerir não dá erro:
    a busca só piora em silêncio. Este caso de uso torna isso visível.
    """

    def __init__(self, doc_repo: DocumentRepository, embedding_generator: EmbeddingGenerator):
        self.doc_repo = doc_repo
        self.embedding_generator = embedding_generator

    async def execute(self) -> EmbeddingCompatibility:
        generator = self.embedding_generator
        model, prefix = generator.embedding_model, generator.document_prefix

        warnings: List[str] = []
        # Prefixo só de um lado quase sempre é engano: a pergunta e o texto ficam em "idiomas" diferentes.
        if bool(generator.query_prefix) != bool(prefix):
            lado = "de pergunta" if generator.query_prefix else "de documento"
            warnings.append(
                f"Só o prefixo {lado} está configurado; configure os dois "
                "(EMBEDDING_QUERY_PREFIX e EMBEDDING_DOCUMENT_PREFIX) ou nenhum."
            )

        total = stale = 0
        groups: List[str] = []
        for stamp in await self.doc_repo.embedding_stamps():
            total += stamp.count
            stamp_prefix = stamp.document_prefix or ""  # sem registro = ingerido sem prefixo
            stamp_model = stamp.model or model  # sem registro não dá para saber: assume o atual
            if stamp_prefix != prefix or stamp_model != model:
                stale += stamp.count
                origin = stamp.model or "anterior ao registro"
                groups.append(f"{stamp.count} com modelo {origin} e prefixo {stamp_prefix!r}")

        return EmbeddingCompatibility(
            model=model, document_prefix=prefix, total=total, stale=stale, stale_groups=groups, warnings=warnings
        )
