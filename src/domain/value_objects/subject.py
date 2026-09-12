from enum import Enum


class Subject(str, Enum):
    """Matérias suportadas pelo tutor, usadas tanto na ingestão de PDFs
    quanto no filtro de busca do comando `/duvida`."""

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
