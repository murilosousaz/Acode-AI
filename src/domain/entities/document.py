from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any


@dataclass
class DocumentChunk:
    """Um pedaço (chunk) vetorizado de um material didático."""

    content: str
    embedding: List[float]
    metadata: Dict[str, Any] = field(default_factory=dict)
    chunk_id: Optional[str] = None


@dataclass
class Document:
    title: str
    subject: str  # ex: "Historia", "Fisica"
    chunks: List[DocumentChunk] = field(default_factory=list)
    doc_id: Optional[str] = None
