"""Deterministic report retrieval."""

from .retrieval import RetrievalEngine, RetrievalResult
from .evidence import (
    EncryptedPdfError,
    EvidenceBlock,
    EvidenceDocument,
    EvidenceError,
    EvidencePage,
    EvidenceWord,
    InvalidPageRangeError,
    NoUsableTextError,
    PdfEvidenceExtractor,
    UnreadablePdfError,
)

__all__ = [
    "EncryptedPdfError", "EvidenceBlock", "EvidenceDocument", "EvidenceError",
    "EvidencePage", "EvidenceWord", "InvalidPageRangeError", "NoUsableTextError",
    "PdfEvidenceExtractor", "UnreadablePdfError",
    "RetrievalEngine", "RetrievalResult",
]
