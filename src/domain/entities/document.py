from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any

@dataclass
class Chunk:
    content: str
    embedding: List[float]
    metadata: Dict[str, Any] = field(default_factory=dict)
    chunk_id: Optional[str] = None

@dataclass
class Document:
    title: str
    subject: str  # ex: "História", "Física"
    chunks: List[Chunk] = field(default_factory=list)
    doc_id: Optional[str] = None