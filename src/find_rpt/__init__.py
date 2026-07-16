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
from .revisions import (
    EstimateRevision,
    RevisionEvidence,
    RevisionExtractor,
    RevisionResult,
    calculate_consensus_spread,
    calculate_revision_pct,
    normalize_fiscal_period,
    normalize_metric,
    normalize_unit,
    parse_value,
)
from .rationale import (
    CandidatePassage,
    CandidatePassageSelector,
    DeterministicFakeRationaleModel,
    Driver,
    GroundedClaim,
    JargonDefinition,
    LocalOpenAICompatibleRationaleModel,
    ModelConfigurationError,
    ModelResponseError,
    PersonMet,
    RationaleExtraction,
    RationaleExtractor,
    RationaleInputError,
    RationaleModel,
    RationaleResult,
    detect_context_signals,
)

__all__ = [
    "EncryptedPdfError", "EvidenceBlock", "EvidenceDocument", "EvidenceError",
    "EvidencePage", "EvidenceWord", "InvalidPageRangeError", "NoUsableTextError",
    "PdfEvidenceExtractor", "UnreadablePdfError",
    "RetrievalEngine", "RetrievalResult",
    "EstimateRevision", "RevisionEvidence", "RevisionExtractor", "RevisionResult",
    "calculate_consensus_spread", "calculate_revision_pct", "normalize_fiscal_period",
    "normalize_metric", "normalize_unit", "parse_value",
    "CandidatePassage", "CandidatePassageSelector", "DeterministicFakeRationaleModel",
    "Driver", "GroundedClaim", "JargonDefinition", "LocalOpenAICompatibleRationaleModel",
    "ModelConfigurationError", "ModelResponseError", "PersonMet", "RationaleExtraction",
    "RationaleExtractor", "RationaleInputError", "RationaleModel", "RationaleResult",
    "detect_context_signals",
]
