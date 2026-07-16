from __future__ import annotations

import copy
import ipaddress
import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, replace
from typing import Any, Mapping, Protocol
from urllib.parse import urlparse

from .evidence import EvidenceBlock, EvidenceDocument
from .revisions import (
    DISCLOSURE_RE,
    RevisionExtractor,
    RevisionResult,
    normalize_fiscal_period,
    normalize_metric,
)


RATIONALE_CLARITIES = {"clear", "partial", "unclear"}
CONTEXTS = {
    "results_preview", "results_review", "roadshow", "management_meeting",
    "initiation", "reiteration", "rating_change", "event_reaction", "other",
    "not_given",
}
MANAGEMENT_STATES = {"true", "false", "unknown"}
CONFIDENCES = {"high", "medium", "low"}
CAUSAL_LINKS = {"explicit", "inferred"}
DRIVER_CATEGORIES = {
    "revenue or volume", "pricing", "product mix", "gross margin",
    "operating costs", "restructuring", "foreign exchange",
    "commodities or input costs", "tax", "interest", "share count",
    "accounting treatment", "acquisitions or disposals", "regulation",
    "guidance", "valuation only", "other",
}

SIGNAL_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("revision", re.compile(r"\b(?:we\s+)?(?:raise|raised|lower|lowered|cut|increase|increased|reduce|reduced|revise|revised)\b", re.I)),
    ("cause", re.compile(r"\b(?:driven by|due to|reflecting|on the back of|because|as a result of|owing to)\b", re.I)),
    ("timing", re.compile(r"\b(?:following|after results|ahead of results|preview|review|results?|trading update|capital markets day)\b", re.I)),
    ("management", re.compile(r"\b(?:roadshow|met with|spoke with|management|CEO|CFO|chief executive|chief financial)\b", re.I)),
    ("coverage", re.compile(r"\b(?:initiating coverage|initiation|reiterate|reiterating|upgrade|downgrade|rating change)\b", re.I)),
    ("first_read", re.compile(r"\b(?:target price|price target|guidance|valuation|catalyst|risk|rating|buy|hold|sell|overweight|underweight)\b", re.I)),
)
CAUSAL_RE = re.compile(
    r"\b(?:driven by|due to|reflecting|on the back of|because|as a result of|owing to|"
    r"we (?:raise|raised|lower|lowered|cut|increase|increased|reduce|reduced).{0,100}(?:after|following|to reflect))\b",
    re.I | re.S,
)
INFERRED_CAUSAL_RE = re.compile(
    r"\b(?:may|might|could|likely|appears?|suggests?)\b.{0,80}"
    r"\b(?:affect|impact|contribut|drive|support|weigh|lead|result)\w*\b",
    re.I | re.S,
)
MANAGEMENT_INTERACTION_RE = re.compile(
    r"\b(?:met with|meeting with|spoke with|roadshow with)\b|"
    r"\b(?:meeting|meetings|roadshow|hosted)\b.{0,120}"
    r"\b(?:management|CEO|CFO|chief executive|chief financial|investor relations)\b|"
    r"\b(?:management|CEO|CFO|chief executive|chief financial|investor relations)\b.{0,120}"
    r"\b(?:meeting|meetings|roadshow|hosted)\b",
    re.I | re.S,
)
NUMBER_RE = re.compile(r"(?<![A-Za-z])[-+]?\d+(?:[.,]\d+)?%?")
TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]{2,}")
STOPWORDS = {
    "and", "the", "for", "with", "that", "this", "from", "into", "because",
    "after", "before", "broker", "report", "estimate", "estimates", "change",
    "changed", "higher", "lower", "reflecting", "driven", "results", "result",
}
WARNING_CODE_RE = re.compile(r"^[a-z][a-z0-9_]{0,79}$")
MAX_CLAIM_CHARACTERS = 500
MAX_DRIVERS = 20
MAX_PEOPLE = 20
MAX_JARGON_DEFINITIONS = 30
MAX_FIRST_READ_ITEMS = 20
JARGON_REQUIRED_TOKENS: dict[str, set[str]] = {
    "eps": {"earnings", "share"},
    "ebit": {"earnings", "interest", "tax"},
    "ebitda": {"earnings", "interest", "tax", "depreciation", "amortization"},
    "nii": {"net", "interest", "income"},
    "fcf": {"free", "cash", "flow"},
    "capex": {"capital", "expenditure"},
    "cet1": {"common", "equity", "tier"},
}
GENERIC_ROLE_TOKENS = {"chief", "officer", "head", "director", "president", "executive"}

CONTEXT_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("results_preview", re.compile(r"\b(?:results?|earnings)\s+preview\b|\bahead of (?:the )?(?:results?|earnings)\b", re.I)),
    ("results_review", re.compile(r"\b(?:results?|earnings)\s+review\b|\bafter (?:the )?(?:results?|earnings)\b|\bpost[- ]results?\b", re.I)),
    ("roadshow", re.compile(r"\broadshow\b", re.I)),
    ("management_meeting", MANAGEMENT_INTERACTION_RE),
    ("initiation", re.compile(r"\b(?:initiating coverage|initiation of coverage|initiate with)\b", re.I)),
    ("reiteration", re.compile(r"\b(?:reiterate|reiterating|reaffirm)\b", re.I)),
    ("rating_change", re.compile(
        r"\bwe\s+(?:upgrade|downgrade)(?:d)?\b|"
        r"\b(?:upgrade|upgraded|downgrade|downgraded)\b.{0,35}\bto\s+"
        r"(?:buy|hold|sell|overweight|underweight|neutral|outperform|underperform)\b|"
        r"\brating\s+(?:upgrade|downgrade|change)\b",
        re.I | re.S,
    )),
    ("event_reaction", re.compile(r"\b(?:reaction to|following|after)\s+(?:the\s+)?(?:announcement|event|trading update|capital markets day|acquisition|disposal)\b", re.I)),
)


class RationaleError(ValueError):
    """Base class for safe rationale-pipeline failures."""


class ModelConfigurationError(RationaleError):
    pass


class ModelResponseError(RationaleError):
    pass


class RationaleInputError(RationaleError):
    pass


@dataclass(frozen=True)
class CandidatePassage:
    page_number: int
    block_id: str
    text: str
    reasons: tuple[str, ...]
    score: int


@dataclass(frozen=True)
class GroundedClaim:
    text: str
    evidence_block_ids: tuple[str, ...]
    confidence: str


@dataclass(frozen=True)
class Driver:
    driver: str
    impacted_metrics: tuple[str, ...]
    fiscal_periods: tuple[str, ...]
    category: str | None
    evidence_block_ids: tuple[str, ...]
    causal_link: str
    confidence: str


@dataclass(frozen=True)
class PersonMet:
    name: str
    role: str | None
    evidence_block_ids: tuple[str, ...]


@dataclass(frozen=True)
class JargonDefinition:
    term: str
    definition: str
    evidence_block_ids: tuple[str, ...]


@dataclass(frozen=True)
class RationaleExtraction:
    rationale_clarity: str
    drivers: tuple[Driver, ...]
    why_now: GroundedClaim | None
    report_context: str
    context_evidence_block_ids: tuple[str, ...]
    management_contact: str
    management_evidence_block_ids: tuple[str, ...]
    people_met: tuple[PersonMet, ...]
    one_line_takeaway: GroundedClaim | None
    jargon_definitions: tuple[JargonDefinition, ...]
    important_first_read_items: tuple[GroundedClaim, ...]
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class RationaleResult:
    status: str
    document_id: str
    source_filename: str
    revision_status: str
    candidate_passages: tuple[CandidatePassage, ...]
    context_signals: tuple[str, ...]
    extraction: RationaleExtraction | None
    model_input_block_count: int
    model_input_character_count: int
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)


class RationaleModel(Protocol):
    def extract(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        """Interpret only the bounded evidence payload and return schema-shaped data."""


class DeterministicFakeRationaleModel:
    """Repeatable test provider; it never accesses a network or a PDF."""

    def __init__(self, response: Mapping[str, Any] | str):
        self.response = response
        self.calls: list[Mapping[str, Any]] = []

    def extract(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        self.calls.append(copy.deepcopy(payload))
        if isinstance(self.response, str):
            try:
                parsed = json.loads(self.response)
            except json.JSONDecodeError as error:
                raise ModelResponseError("model returned malformed JSON") from error
        else:
            parsed = copy.deepcopy(self.response)
        if not isinstance(parsed, Mapping):
            raise ModelResponseError("model response must be a JSON object")
        return parsed


class LocalOpenAICompatibleRationaleModel:
    """Configured provider restricted to a loopback OpenAI-compatible endpoint."""

    def __init__(self, endpoint: str, api_key: str, model: str, *, timeout: float = 60.0):
        self.endpoint = endpoint
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        _require_loopback_endpoint(endpoint)

    @classmethod
    def from_environment(cls) -> "LocalOpenAICompatibleRationaleModel":
        api_key = os.environ.get("FIND_RPT_MODEL_API_KEY", "").strip()
        if not api_key:
            raise ModelConfigurationError(
                "FIND_RPT_MODEL_API_KEY is not configured; use --no-model for passage retrieval only"
            )
        endpoint = os.environ.get(
            "FIND_RPT_MODEL_URL", "http://127.0.0.1:11434/v1/chat/completions"
        ).strip()
        model = os.environ.get("FIND_RPT_MODEL_NAME", "local-rationale-model").strip()
        if not model:
            raise ModelConfigurationError("FIND_RPT_MODEL_NAME must not be empty")
        return cls(endpoint, api_key, model)

    def extract(self, payload: Mapping[str, Any]) -> Mapping[str, Any]:
        body = {
            "model": self.model,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
            ],
        }
        request = urllib.request.Request(
            self.endpoint,
            data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                envelope = json.loads(response.read().decode("utf-8"))
            content = envelope["choices"][0]["message"]["content"]
            parsed = json.loads(content) if isinstance(content, str) else content
        except (OSError, KeyError, IndexError, TypeError, json.JSONDecodeError, urllib.error.URLError) as error:
            raise ModelResponseError("local model request failed or returned malformed JSON") from error
        if not isinstance(parsed, Mapping):
            raise ModelResponseError("model response must be a JSON object")
        return parsed


def _require_loopback_endpoint(endpoint: str) -> None:
    parsed = urlparse(endpoint)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ModelConfigurationError("FIND_RPT_MODEL_URL must be an HTTP(S) URL")
    hostname = parsed.hostname.casefold()
    if hostname == "localhost":
        return
    try:
        if ipaddress.ip_address(hostname).is_loopback:
            return
    except ValueError:
        pass
    raise ModelConfigurationError(
        "FIND_RPT_MODEL_URL must use localhost or a loopback address; report passages cannot be sent externally"
    )


def detect_context_signals(passages: tuple[CandidatePassage, ...]) -> tuple[str, ...]:
    signals: list[str] = []
    for context, pattern in CONTEXT_PATTERNS:
        if any(pattern.search(passage.text) for passage in passages):
            signals.append(context)
    return tuple(signals)


def _block_maps(document: EvidenceDocument) -> tuple[dict[str, EvidenceBlock], dict[str, int]]:
    blocks: dict[str, EvidenceBlock] = {}
    pages: dict[str, int] = {}
    for page in document.pages:
        for block in page.blocks:
            blocks[block.block_id] = block
            pages[block.block_id] = page.page_number
    return blocks, pages


class CandidatePassageSelector:
    """Select a small deterministic evidence set before any model is called."""

    def __init__(self, *, max_blocks: int = 24, max_characters: int = 12_000):
        if max_blocks < 1 or max_characters < 1:
            raise ValueError("passage limits must be positive")
        self.max_blocks = max_blocks
        self.max_characters = max_characters

    def select(
        self, document: EvidenceDocument, revisions: RevisionResult
    ) -> tuple[CandidatePassage, ...]:
        blocks, block_pages = _block_maps(document)
        ordered = [block for page in document.pages for block in page.blocks]
        positions = {block.block_id: index for index, block in enumerate(ordered)}
        scores: dict[str, int] = {}
        reasons: dict[str, list[str]] = {}

        def add(block_id: str, score: int, reason: str) -> None:
            if block_id not in blocks:
                return
            scores[block_id] = scores.get(block_id, 0) + score
            reasons.setdefault(block_id, []).append(reason)

        revision_ids = {
            block_id
            for revision in revisions.revisions
            for evidence in revision.evidence
            for block_id in evidence.block_ids
        } | set(revisions.candidate_block_ids)
        revision_metrics = {revision.metric.replace("_", " ") for revision in revisions.revisions}
        first_page = next((page for page in document.pages if page.page_number == 1), None)
        if first_page is not None:
            for block in first_page.blocks[:4]:
                add(block.block_id, 12, "opening_context")
        for block_id in revision_ids:
            add(block_id, 100, "revision_evidence")
            position = positions.get(block_id)
            if position is None:
                continue
            page_number = block_pages[block_id]
            for adjacent in ordered[max(0, position - 2) : position + 3]:
                if block_pages[adjacent.block_id] == page_number and adjacent.block_id != block_id:
                    add(adjacent.block_id, 45, "adjacent_to_revision")

        seen_contexts: set[str] = set()
        for block in ordered:
            page_number = block_pages[block.block_id]
            if DISCLOSURE_RE.search(block.text):
                continue
            matched = [name for name, pattern in SIGNAL_PATTERNS if pattern.search(block.text)]
            if matched:
                add(block.block_id, 18 * len(matched), "signal:" + ",".join(matched))
            direct_contexts = [
                name for name, pattern in CONTEXT_PATTERNS if pattern.search(block.text)
            ]
            if direct_contexts:
                first_contexts = [name for name in direct_contexts if name not in seen_contexts]
                add(
                    block.block_id,
                    1_000 if first_contexts else 120,
                    "direct_context:" + ",".join(direct_contexts),
                )
                seen_contexts.update(direct_contexts)
            if CAUSAL_RE.search(block.text) or INFERRED_CAUSAL_RE.search(block.text):
                add(block.block_id, 90, "direct_causal_language")
            if page_number <= 2 and matched:
                add(block.block_id, 20, "opening_page_signal")
            if revision_metrics and any(metric in block.text.casefold().replace("_", " ") for metric in revision_metrics):
                if any(abs(page_number - page) <= 1 for page in revisions.candidate_pages):
                    add(block.block_id, 20, "nearby_revision_metric")

        cross_reference_re = re.compile(r"\b(?:see|refer to)\s+(?:section\s+)?(?:on\s+)?page\s+(\d{1,3})\b", re.I)
        for block_id in tuple(scores):
            for match in cross_reference_re.finditer(blocks[block_id].text):
                target_page = int(match.group(1))
                for page in document.pages:
                    if page.page_number == target_page:
                        for target in page.blocks[:4]:
                            add(target.block_id, 35, "explicit_cross_reference")

        ranked = sorted(
            scores,
            key=lambda block_id: (-scores[block_id], block_pages[block_id], positions[block_id]),
        )
        selected: list[CandidatePassage] = []
        characters = 0
        for block_id in ranked:
            text = blocks[block_id].text.strip()
            if not text:
                continue
            if len(selected) >= self.max_blocks:
                break
            remaining = self.max_characters - characters
            if remaining <= 0:
                break
            if selected and len(text) > remaining:
                continue
            passage_reasons = list(dict.fromkeys(reasons[block_id]))
            if len(text) > remaining:
                text = text[:remaining]
                passage_reasons.append("truncated_for_model_input")
            selected.append(
                CandidatePassage(
                    page_number=block_pages[block_id],
                    block_id=block_id,
                    text=text,
                    reasons=tuple(passage_reasons),
                    score=scores[block_id],
                )
            )
            characters += len(text)
            if len(selected) >= self.max_blocks:
                break
        return tuple(selected)


_SYSTEM_PROMPT = """You extract a concise sell-side rationale from bounded evidence passages.
Return only one JSON object matching the requested schema. Use only supplied passages from the
single selected report. Never add financial knowledge. Do not treat proximity as causation.
Use causal_link=explicit only for a direct source link; otherwise inferred. If revisions exist
without a causal explanation, rationale_clarity must be unclear. Do not invent context,
management contact, people, roles, events, metrics, periods, numbers, or block IDs. Context absent
means report_context=not_given. Expand specialist shorthand on first use. Every material claim
must cite supplied evidence_block_ids. Keep why_now and all drivers together short enough for two
brief paragraphs. Do not create citation URLs.

Schema keys: rationale_clarity; drivers[{driver, impacted_metrics[], fiscal_periods[], category,
evidence_block_ids[], causal_link, confidence}]; why_now({text,evidence_block_ids[],confidence}|null);
report_context; context_evidence_block_ids[]; management_contact(true|false|unknown);
management_evidence_block_ids[]; people_met[{name,role,evidence_block_ids[]}];
one_line_takeaway({text,evidence_block_ids[],confidence}|null);
jargon_definitions[{term,definition,evidence_block_ids[]}];
important_first_read_items[{text,evidence_block_ids[],confidence}]; warnings[]."""


def _model_payload(
    document: EvidenceDocument,
    revisions: RevisionResult,
    passages: tuple[CandidatePassage, ...],
    context_signals: tuple[str, ...],
) -> dict[str, Any]:
    grouped: dict[tuple[str, str], set[str]] = {}
    for revision in revisions.revisions:
        grouped.setdefault((revision.metric, revision.direction), set()).add(
            revision.fiscal_period or "not_given"
        )
    revision_summary = [
        {"metric": metric, "direction": direction, "fiscal_periods": sorted(periods)}
        for (metric, direction), periods in sorted(grouped.items())
    ]
    return {
        "document_id": document.document_id,
        "revision_status": revisions.status,
        "revision_summary": revision_summary,
        "deterministic_context_signals": list(context_signals),
        "allowed_driver_categories": sorted(DRIVER_CATEGORIES),
        "allowed_report_contexts": sorted(CONTEXTS),
        "evidence_passages": [
            {"block_id": item.block_id, "page_number": item.page_number, "text": item.text}
            for item in passages
        ],
    }


def _as_string(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    stripped = value.strip()
    return stripped if stripped and len(stripped) <= MAX_CLAIM_CHARACTERS else None


def _string_tuple(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(
        item.strip()
        for item in value[:100]
        if isinstance(item, str) and item.strip() and len(item.strip()) <= MAX_CLAIM_CHARACTERS
    )


def _schema_exact(value: Mapping[str, Any], fields: set[str]) -> bool:
    return set(value) == fields


def _evidence_text(ids: tuple[str, ...], blocks: Mapping[str, EvidenceBlock]) -> str:
    return "\n".join(blocks[block_id].text for block_id in ids if block_id in blocks)


def _valid_ids(value: Any, allowed: set[str]) -> tuple[tuple[str, ...], bool]:
    raw = _string_tuple(value)
    valid = tuple(dict.fromkeys(block_id for block_id in raw if block_id in allowed))
    return valid, len(valid) == len(raw)


def _claim_supported(text: str, ids: tuple[str, ...], blocks: Mapping[str, EvidenceBlock]) -> bool:
    if not text or not ids:
        return False
    evidence = _evidence_text(ids, blocks)
    claim_numbers = {item.replace(",", ".") for item in NUMBER_RE.findall(text)}
    evidence_numbers = {item.replace(",", ".") for item in NUMBER_RE.findall(evidence)}
    if not claim_numbers.issubset(evidence_numbers):
        return False
    claim_tokens = {token.casefold() for token in TOKEN_RE.findall(text)} - STOPWORDS
    evidence_tokens = {token.casefold() for token in TOKEN_RE.findall(evidence)}
    overlap = claim_tokens & evidence_tokens
    required_overlap = max(1, (len(claim_tokens) + 1) // 2)
    return not claim_tokens or len(overlap) >= required_overlap


def _claim_confidence(text: str, ids: tuple[str, ...], blocks: Mapping[str, EvidenceBlock]) -> str:
    evidence_tokens = {
        token.casefold() for token in TOKEN_RE.findall(_evidence_text(ids, blocks))
    }
    claim_tokens = {token.casefold() for token in TOKEN_RE.findall(text)} - STOPWORDS
    ratio = len(claim_tokens & evidence_tokens) / max(1, len(claim_tokens))
    if len(ids) == 1 and ratio >= 0.8:
        return "high"
    if ratio >= 0.5:
        return "medium"
    return "low"


def _sentence_causal_support(
    driver: str, evidence: str, pattern: re.Pattern[str]
) -> bool:
    driver_tokens = {token.casefold() for token in TOKEN_RE.findall(driver)} - STOPWORDS
    for sentence in re.split(r"(?:[.!?]\s+|\n+)", evidence):
        if not pattern.search(sentence):
            continue
        sentence_tokens = {token.casefold() for token in TOKEN_RE.findall(sentence)}
        if len(driver_tokens & sentence_tokens) >= max(1, (len(driver_tokens) + 1) // 2):
            return True
    return False


def _explicit_causal_support(driver: str, evidence: str) -> bool:
    return _sentence_causal_support(driver, evidence, CAUSAL_RE)


def _inferred_causal_support(driver: str, evidence: str) -> bool:
    return _sentence_causal_support(driver, evidence, INFERRED_CAUSAL_RE)


def _driver_confidence(causal_link: str, metrics: tuple[str, ...], periods: tuple[str, ...]) -> str:
    if causal_link == "explicit" and metrics and periods:
        return "high"
    if causal_link == "explicit" or metrics or periods:
        return "medium"
    return "low"


def _jargon_supported(term: str, definition: str, evidence: str) -> bool:
    if term.casefold() not in evidence.casefold():
        return False
    definition_tokens = {token.casefold() for token in TOKEN_RE.findall(definition)}
    required = JARGON_REQUIRED_TOKENS.get(term.casefold())
    if required is not None:
        return required.issubset(definition_tokens)
    explicit_definition = re.compile(
        rf"\b{re.escape(term)}\b.{{0,30}}\b(?:means|defined as|refers to)\b",
        re.I | re.S,
    )
    evidence_tokens = {token.casefold() for token in TOKEN_RE.findall(evidence)}
    return bool(
        explicit_definition.search(evidence)
        and len(definition_tokens & evidence_tokens) >= max(1, (len(definition_tokens) + 1) // 2)
    )


def _role_supported(role: str, evidence: str) -> bool:
    role_tokens = {token.casefold() for token in TOKEN_RE.findall(role)}
    specific = role_tokens - GENERIC_ROLE_TOKENS
    evidence_tokens = {token.casefold() for token in TOKEN_RE.findall(evidence)}
    return specific.issubset(evidence_tokens) if specific else role.casefold() in evidence.casefold()


def _parse_claim(
    value: Any,
    allowed_ids: set[str],
    blocks: Mapping[str, EvidenceBlock],
) -> tuple[GroundedClaim | None, list[str]]:
    warnings: list[str] = []
    if value is None:
        return None, warnings
    if not isinstance(value, Mapping):
        return None, ["malformed_grounded_claim_removed"]
    if not _schema_exact(value, {"text", "evidence_block_ids", "confidence"}):
        return None, ["malformed_grounded_claim_removed"]
    if not isinstance(value.get("evidence_block_ids"), list) or value.get("confidence") not in CONFIDENCES:
        return None, ["malformed_grounded_claim_removed"]
    text = _as_string(value.get("text"))
    ids, complete = _valid_ids(value.get("evidence_block_ids"), allowed_ids)
    if not complete:
        warnings.append("invented_or_unselected_block_id_removed")
    if text is None or not _claim_supported(text, ids, blocks):
        return None, warnings + ["unsupported_claim_removed"]
    return GroundedClaim(text, ids, _claim_confidence(text, ids, blocks)), warnings


def _validate_model_output(
    raw: Mapping[str, Any],
    document: EvidenceDocument,
    revisions: RevisionResult,
    passages: tuple[CandidatePassage, ...],
    context_signals: tuple[str, ...],
) -> RationaleExtraction:
    required = {
        "rationale_clarity", "drivers", "why_now", "report_context",
        "context_evidence_block_ids", "management_contact",
        "management_evidence_block_ids", "people_met", "one_line_takeaway",
        "jargon_definitions", "important_first_read_items", "warnings",
    }
    if set(raw) != required:
        raise ModelResponseError("model response does not match the required top-level schema")
    if not isinstance(raw.get("warnings"), list):
        raise ModelResponseError("warnings must be a JSON array")
    all_blocks, _ = _block_maps(document)
    selected_ids = {passage.block_id for passage in passages}
    validation_blocks = {
        passage.block_id: replace(all_blocks[passage.block_id], text=passage.text)
        for passage in passages
    }
    raw_warnings = _string_tuple(raw.get("warnings"))
    warnings = [warning for warning in raw_warnings if WARNING_CODE_RE.fullmatch(warning)]
    if len(warnings) != len(raw_warnings):
        warnings.append("invalid_model_warning_removed")
    drivers: list[Driver] = []
    raw_drivers = raw.get("drivers")
    if not isinstance(raw_drivers, list):
        raise ModelResponseError("drivers must be a JSON array")
    if len(raw_drivers) > MAX_DRIVERS:
        warnings.append("excess_drivers_removed")
    driver_fields = {
        "driver", "impacted_metrics", "fiscal_periods", "category",
        "evidence_block_ids", "causal_link", "confidence",
    }
    for item in raw_drivers[:MAX_DRIVERS]:
        if not isinstance(item, Mapping):
            warnings.append("malformed_driver_removed")
            continue
        if not _schema_exact(item, driver_fields):
            warnings.append("malformed_driver_removed")
            continue
        if (
            not isinstance(item.get("impacted_metrics"), list)
            or not isinstance(item.get("fiscal_periods"), list)
            or not isinstance(item.get("evidence_block_ids"), list)
            or item.get("causal_link") not in CAUSAL_LINKS
            or item.get("confidence") not in CONFIDENCES
            or (item.get("category") is not None and not isinstance(item.get("category"), str))
        ):
            warnings.append("malformed_driver_removed")
            continue
        text = _as_string(item.get("driver"))
        ids, complete = _valid_ids(item.get("evidence_block_ids"), selected_ids)
        if not complete:
            warnings.append("invented_or_unselected_block_id_removed")
        if text is None or not _claim_supported(text, ids, validation_blocks):
            warnings.append("unsupported_driver_removed")
            continue
        evidence_text = _evidence_text(ids, validation_blocks)
        evidence_metrics = {
            metric for block_id in ids
            if (metric := normalize_metric(validation_blocks[block_id].text)[0]) is not None
        }
        metrics: list[str] = []
        for metric in _string_tuple(item.get("impacted_metrics")):
            canonical = normalize_metric(metric)[0] or metric.casefold().replace(" ", "_")
            if canonical in evidence_metrics:
                metrics.append(canonical)
            else:
                warnings.append("unsupported_impacted_metric_removed")
        evidence_periods = {
            period for match in re.finditer(r"(?:FY|CY)?\s*(?:20\d{2}|\d{2})[Ee]?|[1-4]Q\s*(?:20\d{2}|\d{2})[Ee]?|[12]H\s*(?:20\d{2}|\d{2})[Ee]?", evidence_text, re.I)
            if (period := normalize_fiscal_period(match.group(0))[0]) is not None
        }
        periods: list[str] = []
        for period_text in _string_tuple(item.get("fiscal_periods")):
            period = normalize_fiscal_period(period_text)[0]
            if period and period in evidence_periods:
                periods.append(period)
            else:
                warnings.append("unsupported_fiscal_period_removed")
        category = item.get("category")
        if category is not None and category not in DRIVER_CATEGORIES:
            category = None
            warnings.append("unknown_driver_category_removed")
        if category == "valuation only" and (
            "target_price" not in evidence_metrics
            or any(metric != "target_price" for metric in metrics)
        ):
            warnings.append("valuation_only_driver_not_linked_to_target_price")
            continue
        causal_link = item["causal_link"]
        explicit_support = _explicit_causal_support(text, evidence_text)
        inferred_support = _inferred_causal_support(text, evidence_text)
        if causal_link == "explicit" and not explicit_support:
            if inferred_support:
                causal_link = "inferred"
                warnings.append("causal_link_downgraded_to_inferred")
            else:
                warnings.append("unsupported_causal_driver_removed")
                continue
        elif causal_link == "inferred" and not (explicit_support or inferred_support):
            warnings.append("unsupported_causal_driver_removed")
            continue
        metric_tuple = tuple(dict.fromkeys(metrics))
        period_tuple = tuple(dict.fromkeys(periods))
        drivers.append(
            Driver(
                driver=text,
                impacted_metrics=metric_tuple,
                fiscal_periods=period_tuple,
                category=category,
                evidence_block_ids=ids,
                causal_link=causal_link,
                confidence=_driver_confidence(causal_link, metric_tuple, period_tuple),
            )
        )

    why_now, claim_warnings = _parse_claim(raw.get("why_now"), selected_ids, validation_blocks)
    warnings.extend(claim_warnings)
    takeaway, claim_warnings = _parse_claim(raw.get("one_line_takeaway"), selected_ids, validation_blocks)
    warnings.extend(claim_warnings)

    context = raw.get("report_context") if raw.get("report_context") in CONTEXTS else "not_given"
    context_ids, complete = _valid_ids(raw.get("context_evidence_block_ids"), selected_ids)
    if not complete:
        warnings.append("invented_or_unselected_block_id_removed")
    if context == "not_given":
        context_ids = ()
    elif context == "other" and context_ids:
        pass
    elif not context_ids or not any(pattern.search(_evidence_text(context_ids, validation_blocks)) for name, pattern in CONTEXT_PATTERNS if name == context):
        context = "not_given"
        context_ids = ()
        warnings.append("unsupported_report_context_removed")

    management = str(raw.get("management_contact", "unknown")).casefold()
    if management not in MANAGEMENT_STATES:
        management = "unknown"
    management_ids, complete = _valid_ids(raw.get("management_evidence_block_ids"), selected_ids)
    if not complete:
        warnings.append("invented_or_unselected_block_id_removed")
    management_text = _evidence_text(management_ids, validation_blocks)
    if management == "true" and not MANAGEMENT_INTERACTION_RE.search(management_text):
        management, management_ids = "unknown", ()
        warnings.append("unsupported_management_contact_removed")
    elif management == "false" and not re.search(r"\b(?:did not|no)\s+(?:meet|meeting|contact|discussion)\b", management_text, re.I):
        management, management_ids = "unknown", ()
        warnings.append("unsupported_management_absence_removed")

    people: list[PersonMet] = []
    raw_people = raw.get("people_met")
    if not isinstance(raw_people, list):
        raise ModelResponseError("people_met must be a JSON array")
    if len(raw_people) > MAX_PEOPLE:
        warnings.append("excess_people_removed")
    person_fields = {"name", "role", "evidence_block_ids"}
    for item in raw_people[:MAX_PEOPLE]:
        if not isinstance(item, Mapping):
            warnings.append("malformed_person_removed")
            continue
        if not _schema_exact(item, person_fields):
            warnings.append("malformed_person_removed")
            continue
        if (
            not isinstance(item.get("evidence_block_ids"), list)
            or not isinstance(item.get("name"), str)
            or (item.get("role") is not None and not isinstance(item.get("role"), str))
        ):
            warnings.append("malformed_person_removed")
            continue
        name = _as_string(item.get("name"))
        role = _as_string(item.get("role"))
        ids, complete = _valid_ids(item.get("evidence_block_ids"), selected_ids)
        evidence_text = _evidence_text(ids, validation_blocks)
        if not complete:
            warnings.append("invented_or_unselected_block_id_removed")
        if name is None or name.casefold() not in evidence_text.casefold():
            warnings.append("unsupported_person_removed")
            continue
        if management != "true" or not MANAGEMENT_INTERACTION_RE.search(evidence_text):
            warnings.append("person_without_management_interaction_removed")
            continue
        if role and not _role_supported(role, evidence_text):
            role = None
            warnings.append("unsupported_person_role_removed")
        people.append(PersonMet(name, role, ids))

    jargon: list[JargonDefinition] = []
    raw_jargon = raw.get("jargon_definitions")
    if not isinstance(raw_jargon, list):
        raise ModelResponseError("jargon_definitions must be a JSON array")
    if len(raw_jargon) > MAX_JARGON_DEFINITIONS:
        warnings.append("excess_jargon_definitions_removed")
    jargon_fields = {"term", "definition", "evidence_block_ids"}
    for item in raw_jargon[:MAX_JARGON_DEFINITIONS]:
        if (
            not isinstance(item, Mapping)
            or not _schema_exact(item, jargon_fields)
            or not isinstance(item.get("term"), str)
            or not isinstance(item.get("definition"), str)
            or not isinstance(item.get("evidence_block_ids"), list)
        ):
            warnings.append("malformed_jargon_definition_removed")
            continue
        term, definition = _as_string(item.get("term")), _as_string(item.get("definition"))
        ids, complete = _valid_ids(item.get("evidence_block_ids"), selected_ids)
        if not complete:
            warnings.append("invented_or_unselected_block_id_removed")
        evidence_text = _evidence_text(ids, validation_blocks)
        if term and definition and ids and _jargon_supported(term, definition, evidence_text):
            jargon.append(JargonDefinition(term, definition, ids))
        else:
            warnings.append("unsupported_jargon_definition_removed")

    items: list[GroundedClaim] = []
    raw_items = raw.get("important_first_read_items")
    if not isinstance(raw_items, list):
        raise ModelResponseError("important_first_read_items must be a JSON array")
    if len(raw_items) > MAX_FIRST_READ_ITEMS:
        warnings.append("excess_first_read_items_removed")
    for item in raw_items[:MAX_FIRST_READ_ITEMS]:
        claim, claim_warnings = _parse_claim(item, selected_ids, validation_blocks)
        warnings.extend(claim_warnings)
        if claim:
            items.append(claim)

    clarity = raw.get("rationale_clarity") if raw.get("rationale_clarity") in RATIONALE_CLARITIES else "unclear"
    if revisions.status != "no_revisions" and not drivers:
        clarity = "unclear"
    elif any(warning in warnings for warning in ("unsupported_driver_removed", "causal_link_downgraded_to_inferred")) and clarity == "clear":
        clarity = "partial"
    return RationaleExtraction(
        rationale_clarity=clarity,
        drivers=tuple(drivers),
        why_now=why_now,
        report_context=context,
        context_evidence_block_ids=context_ids,
        management_contact=management,
        management_evidence_block_ids=management_ids,
        people_met=tuple(people),
        one_line_takeaway=takeaway,
        jargon_definitions=tuple(jargon),
        important_first_read_items=tuple(items),
        warnings=tuple(dict.fromkeys(warnings)),
    )


class RationaleExtractor:
    def __init__(
        self,
        model: RationaleModel | None = None,
        *,
        selector: CandidatePassageSelector | None = None,
    ):
        self.model = model
        self.selector = selector or CandidatePassageSelector()

    def extract(
        self,
        document: EvidenceDocument,
        *,
        revisions: RevisionResult | None = None,
        no_model: bool = False,
        broker: str | None = None,
    ) -> RationaleResult:
        revisions = revisions or RevisionExtractor().extract(document, broker=broker)
        if revisions.document_id != document.document_id:
            raise RationaleInputError(
                "revision data does not belong to the selected evidence document"
            )
        passages = self.selector.select(document, revisions)
        context_signals = detect_context_signals(passages)
        payload = _model_payload(document, revisions, passages, context_signals)
        character_count = sum(len(item["text"]) for item in payload["evidence_passages"])
        if no_model:
            return RationaleResult(
                status="retrieval_only",
                document_id=document.document_id,
                source_filename=document.source_filename,
                revision_status=revisions.status,
                candidate_passages=passages,
                context_signals=context_signals,
                extraction=None,
                model_input_block_count=len(passages),
                model_input_character_count=character_count,
                warnings=("semantic_interpretation_skipped",),
            )
        model = self.model or LocalOpenAICompatibleRationaleModel.from_environment()
        try:
            raw = model.extract(payload)
            extraction = _validate_model_output(raw, document, revisions, passages, context_signals)
        except ModelResponseError as error:
            return RationaleResult(
                status="model_error",
                document_id=document.document_id,
                source_filename=document.source_filename,
                revision_status=revisions.status,
                candidate_passages=passages,
                context_signals=context_signals,
                extraction=None,
                model_input_block_count=len(passages),
                model_input_character_count=character_count,
                warnings=(f"model_failure:{error}",),
            )
        except Exception:
            return RationaleResult(
                status="model_error",
                document_id=document.document_id,
                source_filename=document.source_filename,
                revision_status=revisions.status,
                candidate_passages=passages,
                context_signals=context_signals,
                extraction=None,
                model_input_block_count=len(passages),
                model_input_character_count=character_count,
                warnings=("model_failure:unexpected_provider_or_validation_error",),
            )
        return RationaleResult(
            status="interpreted",
            document_id=document.document_id,
            source_filename=document.source_filename,
            revision_status=revisions.status,
            candidate_passages=passages,
            context_signals=context_signals,
            extraction=extraction,
            model_input_block_count=len(passages),
            model_input_character_count=character_count,
            warnings=(),
        )
