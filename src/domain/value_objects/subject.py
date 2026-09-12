import unicodedata
from enum import Enum


def _normalize(value: str) -> str:
    """Remove acentos e normaliza para minúsculas, para permitir comparações
    tolerantes a maiúsculas/minúsculas e variações de escrita (ex.: 'física',
    'Fisica', 'FÍSICA' devem ser todos reconhecidos como o mesmo Subject)."""
    without_accents = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    return without_accents.strip().lower()


class Subject(str, Enum):
    """Matérias suportadas pelo tutor, usadas tanto na ingestão de PDFs
    quanto no filtro de busca do comando `/duvida`.

    Usar sempre este enum (via `from_string`) como fonte única de verdade
    para o valor de `metadata.subject` gravado no MongoDB garante que a
    ingestão (que recebe texto livre do admin ou do nome do arquivo) e a
    busca (que oferece um combobox fixo no Discord) fiquem consistentes.
    Sem essa normalização, um material ingerido como "física" nunca seria
    encontrado ao filtrar por "Fisica".
    """

    HISTORIA = "Historia"
    GEOGRAFIA = "Geografia"
    FISICA = "Fisica"
    QUIMICA = "Quimica"
    BIOLOGIA = "Biologia"
    MATEMATICA = "Matematica"
    LINGUAGENS = "Linguagens"
    GERAL = "Geral"

    @property
    def label(self) -> str:
        """Rótulo amigável em português para exibição na UI do Discord."""
        return {
            Subject.HISTORIA: "História",
            Subject.GEOGRAFIA: "Geografia",
            Subject.FISICA: "Física",
            Subject.QUIMICA: "Química",
            Subject.BIOLOGIA: "Biologia",
            Subject.MATEMATICA: "Matemática",
            Subject.LINGUAGENS: "Linguagens / Redação",
            Subject.GERAL: "Geral",
        }[self]

    @classmethod
    def from_string(cls, value: str) -> "Subject":
        """Mapeia uma string livre (nome de arquivo, input de CLI, etc.)
        para o Subject correspondente, ignorando acentos e caixa.

        Retorna `Subject.GERAL` quando não há correspondência, em vez de
        levantar uma exceção, para que scripts de ingestão em lote nunca
        travem por causa de um nome de matéria mal escrito — o material
        ainda é ingerido, só cai na categoria genérica.
        """
        if not value:
            return cls.GERAL

        normalized = _normalize(value)
        for subject in cls:
            if _normalize(subject.value) == normalized or _normalize(subject.label) == normalized:
                return subject
        return cls.GERAL
