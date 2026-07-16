from __future__ import annotations

import hashlib
import html
import ipaddress
import json
import math
import re
from dataclasses import asdict, dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path, PurePosixPath
from typing import Iterable
from urllib.parse import urlsplit

import fitz

from .evidence import EvidenceBlock, EvidenceDocument, EvidencePage
from .rationale import RationaleResult
from .revisions import RevisionResult, normalize_fiscal_period, normalize_metric


SCHEMA_VERSION = 1
DEFAULT_CACHE = Path(".cache/find-rpt/citations")
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
BOX_TOLERANCE = 0.5
WORD_GAP_TOLERANCE = 4.0
CITATION_ID_RE = re.compile(r"^cit-[0-9a-f]{24}$")
DOCUMENT_ID_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


class CitationError(ValueError):
    """Base class for safe citation failures."""


class CitationInputError(CitationError):
    pass


class CitationNotFoundError(CitationError):
    pass


class StaleCitationError(CitationError):
    pass


@dataclass(frozen=True)
class CitationRequest:
    document_id: str
    evidence_block_ids: tuple[str, ...]
    label: str
    claim_key: str | None = None
    highlight_metric: str | None = None
    highlight_period: str | None = None


@dataclass(frozen=True)
class CitationRecord:
    citation_id: str
    document_id: str
    source_filename: str
    source_size: int
    source_sha256: str
    page_number: int
    page_width: float
    page_height: float
    evidence_block_ids: tuple[str, ...]
    bounding_boxes: tuple[tuple[float, float, float, float], ...]
    evidence_label: str
    claim_key: str | None
    local_url: str
    validation_status: str
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class CitationBuildResult:
    document_id: str
    source_filename: str
    citations: tuple[CitationRecord, ...]
    failed_requests: int
    warnings: tuple[str, ...]

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)


def source_fingerprint(path: Path | str) -> tuple[int, str]:
    path = Path(path)
    digest = hashlib.sha256()
    try:
        size = path.stat().st_size
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as error:
        raise CitationInputError("source PDF cannot be read") from error
    return size, digest.hexdigest()


def _validated_base_url(value: str) -> str:
    parsed = urlsplit(value)
    try:
        port = parsed.port
    except ValueError as error:
        raise CitationInputError("citation base URL has an invalid port") from error
    if (
        parsed.scheme != "http"
        or not parsed.hostname
        or not _is_loopback(parsed.hostname)
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
        or port is None
    ):
        raise CitationInputError("citation base URL must be a loopback HTTP origin")
    return value.rstrip("/")


def _safe_relative_source(path: Path, corpus_root: Path) -> str:
    if path.is_symlink():
        raise CitationInputError("symbolic-link source PDFs are not allowed")
    try:
        relative = path.resolve(strict=True).relative_to(corpus_root.resolve(strict=True))
    except (OSError, ValueError) as error:
        raise CitationInputError("source PDF must be an indexed file under the corpus root") from error
    if relative.suffix.casefold() != ".pdf" or any(part in {"", ".", ".."} for part in relative.parts):
        raise CitationInputError("source PDF must be a safe corpus-relative PDF path")
    return PurePosixPath(*relative.parts).as_posix()


def _validate_box(
    bbox: tuple[float, float, float, float], page: EvidencePage
) -> tuple[float, float, float, float]:
    if len(bbox) != 4 or not all(math.isfinite(value) for value in bbox):
        raise CitationInputError("evidence bounding box contains non-finite coordinates")
    x0, y0, x1, y1 = bbox
    if not (x0 < x1 and y0 < y1):
        raise CitationInputError("evidence bounding box is degenerate")
    if (
        x0 < -BOX_TOLERANCE
        or y0 < -BOX_TOLERANCE
        or x1 > page.width + BOX_TOLERANCE
        or y1 > page.height + BOX_TOLERANCE
    ):
        raise CitationInputError("evidence bounding box lies outside the cited page")
    return (
        round(max(0.0, x0), 3),
        round(max(0.0, y0), 3),
        round(min(page.width, x1), 3),
        round(min(page.height, y1), 3),
    )


def _highlight_boxes(
    page: EvidencePage,
    blocks: Iterable[EvidenceBlock],
    *,
    highlight_metric: str | None = None,
    highlight_period: str | None = None,
) -> tuple[tuple[tuple[float, float, float, float], ...], tuple[str, ...]]:
    boxes: list[tuple[float, float, float, float]] = []
    warnings: list[str] = []
    line_entries: list[tuple[list, float, bool, bool]] = []
    for block in blocks:
        if block.words:
            lines: dict[int, list] = {}
            for word in block.words:
                lines.setdefault(word.line_number, []).append(word)
            for words in lines.values():
                text = " ".join(word.text for word in words)
                metric_match = (
                    highlight_metric is not None
                    and normalize_metric(text)[0] == highlight_metric
                )
                period_matches = {
                    normalized
                    for token in re.findall(
                        r"(?:FY|CY)?\s*(?:20\d{2}|\d{2})[Ee]?|[1-4]Q\s*(?:20\d{2}|\d{2})[Ee]?|[12]H\s*(?:20\d{2}|\d{2})[Ee]?",
                        text,
                        re.I,
                    )
                    if (normalized := normalize_fiscal_period(token)[0]) is not None
                }
                period_match = highlight_period is not None and highlight_period in period_matches
                y = sum(word.bbox[1] for word in words) / len(words)
                line_entries.append((words, y, metric_match, period_match))
        else:
            boxes.append(_validate_box(block.bbox, page))
            warnings.append("block_box_fallback_used")
    metric_rows = [y for _, y, metric_match, _ in line_entries if metric_match]
    separate_period_header = any(
        period_match and all(abs(y - metric_y) > 3.0 for metric_y in metric_rows)
        for _, y, _, period_match in line_entries
    )
    metric_label_needs_aligned_values = any(
        metric_match
        and not any(
            re.search(r"\d", word.text)
            and normalize_fiscal_period(word.text)[0] is None
            for word in words
        )
        for words, _, metric_match, _ in line_entries
    )
    aligned_value_rows = separate_period_header or metric_label_needs_aligned_values
    metric_right_edge = max(
        (
            word.bbox[2]
            for words, _, metric_match, _ in line_entries
            if metric_match
            for word in words
        ),
        default=0.0,
    )
    period_anchors = [
        (word.bbox[0] + word.bbox[2]) / 2
        for words, _, _, period_match in line_entries
        if period_match
        for word in words
        if normalize_fiscal_period(word.text)[0] == highlight_period
    ]
    period_header_rows = [y for _, y, _, period_match in line_entries if period_match]
    all_period_anchors = [
        (word.bbox[0] + word.bbox[2]) / 2
        for words, y, _, _ in line_entries
        if any(abs(y - header_y) <= 3.0 for header_y in period_header_rows)
        for word in words
        if normalize_fiscal_period(word.text)[0] is not None
        or re.fullmatch(r"(?:FY|CY)?\s*(?:20\d{2}|\d{2})[AE]?", word.text, re.I)
    ]
    if highlight_metric is None and highlight_period is None:
        selected_entries = line_entries
    else:
        selected_entries = [
            entry
            for entry in line_entries
            for words, y, metric_match, period_match in (entry,)
            if metric_match
            or period_match
            or (
                aligned_value_rows
                and any(abs(y - metric_y) <= 3.0 for metric_y in metric_rows)
            )
        ]
        if not selected_entries:
            selected_entries = line_entries
            warnings.append("precise_line_selector_fallback_used")
    for words, y, metric_match, period_match in selected_entries:
        if (
            aligned_value_rows
            and not separate_period_header
            and not metric_match
            and any(abs(y - metric_y) <= 3.0 for metric_y in metric_rows)
        ):
            words = [word for word in words if word.bbox[0] >= metric_right_edge - 2.0]
            if not words:
                continue
        if (
            period_anchors
            and metric_rows
            and separate_period_header
            and not period_match
            and any(abs(y - metric_y) <= 3.0 for metric_y in metric_rows)
        ):
            left_label_boundary = min(all_period_anchors or period_anchors) - 20.0
            words = [
                word
                for word in words
                if (word.bbox[0] + word.bbox[2]) / 2 < left_label_boundary
                or any(
                    abs((word.bbox[0] + word.bbox[2]) / 2 - anchor) <= 24.0
                    for anchor in period_anchors
                )
            ]
            if not words:
                continue
        line_boxes = [_validate_box(word.bbox, page) for word in words]
        line_boxes.sort(key=lambda box: (box[0], box[1], box[2], box[3]))
        merged: list[list[float]] = []
        for box in line_boxes:
            if (
                merged
                and box[0] - merged[-1][2] <= WORD_GAP_TOLERANCE
                and box[1] < merged[-1][3]
                and box[3] > merged[-1][1]
            ):
                merged[-1][0] = min(merged[-1][0], box[0])
                merged[-1][1] = min(merged[-1][1], box[1])
                merged[-1][2] = max(merged[-1][2], box[2])
                merged[-1][3] = max(merged[-1][3], box[3])
            else:
                merged.append(list(box))
        boxes.extend(tuple(round(value, 3) for value in item) for item in merged)
    unique = tuple(dict.fromkeys(boxes))
    if not unique:
        raise CitationInputError("evidence resolved without a usable highlight box")
    return unique, tuple(dict.fromkeys(warnings))


def _citation_id(
    document_id: str,
    page_number: int,
    block_ids: tuple[str, ...],
    highlight_metric: str | None,
    highlight_period: str | None,
) -> str:
    payload = json.dumps(
        {
            "schema": SCHEMA_VERSION,
            "document_id": document_id,
            "page_number": page_number,
            "evidence_block_ids": list(block_ids),
            "highlight_metric": highlight_metric,
            "highlight_period": highlight_period,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return "cit-" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


def requests_from_revisions(result: RevisionResult) -> tuple[CitationRequest, ...]:
    requests: list[CitationRequest] = []
    for revision_index, revision in enumerate(result.revisions, start=1):
        period = revision.fiscal_period or "current"
        for evidence_index, evidence in enumerate(revision.evidence, start=1):
            requests.append(
                CitationRequest(
                    document_id=result.document_id,
                    evidence_block_ids=evidence.block_ids,
                    label=f"{revision.metric.replace('_', ' ')} {period} revision evidence",
                    claim_key=f"revision:{revision_index}:evidence:{evidence_index}",
                    highlight_metric=revision.metric,
                    highlight_period=revision.fiscal_period,
                )
            )
    return tuple(requests)


def requests_from_rationale(result: RationaleResult) -> tuple[CitationRequest, ...]:
    extraction = result.extraction
    if extraction is None:
        return ()
    requests: list[CitationRequest] = []

    def add(label: str, block_ids: tuple[str, ...], key: str) -> None:
        if block_ids:
            requests.append(CitationRequest(result.document_id, block_ids, label, key))

    for index, driver in enumerate(extraction.drivers, start=1):
        add(f"Rationale driver {index}", driver.evidence_block_ids, f"rationale:driver:{index}")
    if extraction.why_now:
        add("Why now", extraction.why_now.evidence_block_ids, "rationale:why_now")
    add("Report context", extraction.context_evidence_block_ids, "rationale:context")
    add("Management interaction", extraction.management_evidence_block_ids, "rationale:management")
    if extraction.one_line_takeaway:
        add("One-line takeaway", extraction.one_line_takeaway.evidence_block_ids, "rationale:takeaway")
    for index, item in enumerate(extraction.important_first_read_items, start=1):
        add(f"First-read item {index}", item.evidence_block_ids, f"rationale:first_read:{index}")
    return tuple(requests)


class CitationBuilder:
    def __init__(
        self,
        corpus_root: Path | str = "corpus",
        *,
        base_url: str = f"http://{DEFAULT_HOST}:{DEFAULT_PORT}",
    ):
        self.corpus_root = Path(corpus_root)
        self.base_url = _validated_base_url(base_url)

    def build(
        self,
        document: EvidenceDocument,
        source_path: Path | str,
        requests: Iterable[CitationRequest],
    ) -> CitationBuildResult:
        source_path = Path(source_path)
        source_filename = _safe_relative_source(source_path, self.corpus_root)
        source_size, source_sha256 = source_fingerprint(source_path)
        expected_document_id = f"sha256:{source_sha256}"
        if document.document_id != expected_document_id:
            raise StaleCitationError("source PDF changed after evidence extraction")

        pages = {page.page_number: page for page in document.pages}
        blocks: dict[str, tuple[EvidencePage, EvidenceBlock]] = {}
        for page in document.pages:
            for block in page.blocks:
                if block.block_id in blocks:
                    raise CitationInputError("duplicate evidence block ID in selected document")
                blocks[block.block_id] = (page, block)

        citations: list[CitationRecord] = []
        warnings: list[str] = []
        failed = 0
        seen_ids: set[str] = set()
        for request_index, request in enumerate(requests, start=1):
            label = " ".join(request.label.split())
            if request.document_id != document.document_id:
                failed += 1
                warnings.append(f"request_{request_index}:wrong_document")
                continue
            if not label or len(label) > 160 or not request.evidence_block_ids:
                failed += 1
                warnings.append(f"request_{request_index}:invalid_request_metadata")
                continue
            requested_ids = tuple(dict.fromkeys(request.evidence_block_ids))
            if any(block_id not in blocks for block_id in requested_ids):
                failed += 1
                warnings.append(f"request_{request_index}:unknown_evidence_block")
                continue
            grouped: dict[int, list[str]] = {}
            for block_id in requested_ids:
                grouped.setdefault(blocks[block_id][0].page_number, []).append(block_id)
            split = len(grouped) > 1
            for page_number, page_ids in sorted(grouped.items()):
                page = pages[page_number]
                ordered_ids = tuple(page_ids)
                try:
                    highlight_boxes, box_warnings = _highlight_boxes(
                        page,
                        (blocks[block_id][1] for block_id in ordered_ids),
                        highlight_metric=request.highlight_metric,
                        highlight_period=request.highlight_period,
                    )
                except CitationInputError:
                    failed += 1
                    warnings.append(f"request_{request_index}:invalid_bounding_box")
                    continue
                record_warnings = list(box_warnings)
                if split:
                    record_warnings.append("split_from_multi_page_evidence")
                identifier = _citation_id(
                    document.document_id,
                    page_number,
                    ordered_ids,
                    request.highlight_metric,
                    request.highlight_period,
                )
                if identifier in seen_ids:
                    continue
                seen_ids.add(identifier)
                citations.append(
                    CitationRecord(
                        citation_id=identifier,
                        document_id=document.document_id,
                        source_filename=source_filename,
                        source_size=source_size,
                        source_sha256=source_sha256,
                        page_number=page_number,
                        page_width=page.width,
                        page_height=page.height,
                        evidence_block_ids=ordered_ids,
                        bounding_boxes=highlight_boxes,
                        evidence_label=label,
                        claim_key=request.claim_key,
                        local_url=f"{self.base_url}/citation/{identifier}#evidence-target",
                        validation_status="valid",
                        warnings=tuple(record_warnings),
                    )
                )
        return CitationBuildResult(
            document_id=document.document_id,
            source_filename=source_filename,
            citations=tuple(citations),
            failed_requests=failed,
            warnings=tuple(warnings),
        )


class CitationStore:
    def __init__(self, cache_dir: Path | str = DEFAULT_CACHE):
        self.cache_dir = Path(cache_dir)
        self.index_path = self.cache_dir / "index.json"

    def _empty(self) -> dict:
        return {"schema_version": SCHEMA_VERSION, "documents": {}, "citations": {}}

    def load(self) -> dict:
        if not self.index_path.is_file():
            return self._empty()
        try:
            data = json.loads(self.index_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise CitationInputError("citation cache index is unreadable") from error
        if data.get("schema_version") != SCHEMA_VERSION:
            raise CitationInputError("citation cache schema is unsupported")
        if not isinstance(data.get("documents"), dict) or not isinstance(data.get("citations"), dict):
            raise CitationInputError("citation cache index is malformed")
        return data

    def save(self, result: CitationBuildResult) -> None:
        data = self.load()
        if result.citations:
            first = result.citations[0]
            data["documents"][result.document_id] = {
                "document_id": result.document_id,
                "source_filename": result.source_filename,
                "source_size": first.source_size,
                "source_sha256": first.source_sha256,
            }
        for citation in result.citations:
            data["citations"][citation.citation_id] = asdict(citation)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        temporary = self.index_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        temporary.replace(self.index_path)

    def citation(self, citation_id: str) -> CitationRecord:
        if not CITATION_ID_RE.fullmatch(citation_id):
            raise CitationNotFoundError("invalid citation ID")
        raw = self.load()["citations"].get(citation_id)
        if not isinstance(raw, dict):
            raise CitationNotFoundError("citation ID is not indexed")
        try:
            citation = CitationRecord(
                citation_id=raw["citation_id"],
                document_id=raw["document_id"],
                source_filename=raw["source_filename"],
                source_size=int(raw["source_size"]),
                source_sha256=raw["source_sha256"],
                page_number=int(raw["page_number"]),
                page_width=float(raw["page_width"]),
                page_height=float(raw["page_height"]),
                evidence_block_ids=tuple(raw["evidence_block_ids"]),
                bounding_boxes=tuple(tuple(map(float, box)) for box in raw["bounding_boxes"]),
                evidence_label=raw["evidence_label"],
                claim_key=raw.get("claim_key"),
                local_url=raw["local_url"],
                validation_status=raw["validation_status"],
                warnings=tuple(raw.get("warnings", ())),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise CitationInputError("citation cache record is malformed") from error
        if citation.citation_id != citation_id:
            raise CitationInputError("citation cache record does not match its index key")
        return citation


class CitationRepository:
    def __init__(self, corpus_root: Path | str, store: CitationStore):
        self.corpus_root = Path(corpus_root)
        self.store = store

    def source_path(self, source_filename: str) -> Path:
        relative = Path(PurePosixPath(source_filename))
        if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
            raise CitationNotFoundError("indexed source path is unsafe")
        try:
            root = self.corpus_root.resolve(strict=True)
            unresolved = root / relative
            current = root
            for part in relative.parts:
                current = current / part
                if current.is_symlink():
                    raise CitationNotFoundError("indexed source PDF is unavailable")
            path = unresolved.resolve(strict=True)
            path.relative_to(root)
        except (OSError, ValueError) as error:
            raise CitationNotFoundError("indexed source PDF is unavailable") from error
        if not path.is_file() or path.suffix.casefold() != ".pdf" or path.is_symlink():
            raise CitationNotFoundError("indexed source PDF is unavailable")
        return path

    def validate(self, citation_id: str) -> CitationRecord:
        citation = self.store.citation(citation_id)
        if citation.validation_status != "valid":
            raise CitationInputError("citation record is not valid")
        path = self.source_path(citation.source_filename)
        size, digest = source_fingerprint(path)
        if size != citation.source_size or digest != citation.source_sha256:
            raise StaleCitationError("source PDF changed after citation build")
        if citation.document_id != f"sha256:{digest}":
            raise StaleCitationError("citation document identity no longer matches source PDF")
        if not DOCUMENT_ID_RE.fullmatch(citation.document_id):
            raise CitationInputError("citation document ID is malformed")
        if citation.page_number < 1:
            raise CitationInputError("citation page number is invalid")
        if (
            not math.isfinite(citation.page_width)
            or not math.isfinite(citation.page_height)
            or citation.page_width <= 0
            or citation.page_height <= 0
            or not citation.bounding_boxes
        ):
            raise CitationInputError("citation page geometry is invalid")
        for box in citation.bounding_boxes:
            page = EvidencePage(citation.page_number, citation.page_width, citation.page_height, ())
            _validate_box(box, page)
        return citation


def _is_loopback(host: str) -> bool:
    if host.casefold() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _viewer_html(citation: CitationRecord) -> bytes:
    rectangles = "".join(
        f'<rect class="highlight" x="{x0}" y="{y0}" width="{x1-x0}" height="{y1-y0}" rx="1" />'
        for x0, y0, x1, y1 in citation.bounding_boxes
    )
    label = html.escape(citation.evidence_label)
    source = html.escape(PurePosixPath(citation.source_filename).name)
    target_top = max(box[1] for box in citation.bounding_boxes) / citation.page_height * 100
    content = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{label} - page {citation.page_number}</title>
<style>
body{{margin:0;background:#20242a;color:#f4f6f8;font:14px system-ui,sans-serif}}header{{position:sticky;top:0;z-index:3;padding:10px 16px;background:#111820;border-bottom:1px solid #48515b}}header a{{color:#8bc5ff}}.page{{position:relative;width:min(1100px,96vw);aspect-ratio:{citation.page_width}/{citation.page_height};margin:18px auto;box-shadow:0 3px 20px #0008}}.page img,.page svg{{position:absolute;inset:0;display:block;width:100%;height:100%}}#evidence-target{{display:block;width:1px;height:1px;scroll-margin-top:90px}}.highlight{{fill:#ffe45c;fill-opacity:.38;stroke:#ff9f1c;stroke-width:1.4;vector-effect:non-scaling-stroke}}</style></head>
<body><header><strong>{label}</strong> &middot; {source} &middot; page {citation.page_number} &middot; <a href="/document/{citation.document_id}.pdf#page={citation.page_number}">open original PDF</a></header>
<main class="page" id="evidence"><div style="height:{target_top}%"></div><span id="evidence-target"></span><img alt="Cited PDF page {citation.page_number}" src="/citation/{citation.citation_id}/page.png"><svg viewBox="0 0 {citation.page_width} {citation.page_height}" aria-label="Evidence highlights">{rectangles}</svg></main></body></html>"""
    return content.encode("utf-8")


def make_server(
    corpus_root: Path | str = "corpus",
    cache_dir: Path | str = DEFAULT_CACHE,
    *,
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
) -> ThreadingHTTPServer:
    if not _is_loopback(host):
        raise CitationInputError("citation viewer must bind to a loopback address")
    if not (0 <= port <= 65535):
        raise CitationInputError("citation viewer port must be between 0 and 65535")
    repository = CitationRepository(corpus_root, CitationStore(cache_dir))

    class Handler(BaseHTTPRequestHandler):
        server_version = "find-rpt-citations/1"

        def log_message(self, format: str, *args) -> None:
            return

        def _headers(self, status: HTTPStatus, content_type: str, length: int) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(length))
            self.send_header("Cache-Control", "no-store, private, max-age=0")
            self.send_header("Pragma", "no-cache")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'self'; img-src 'self'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; object-src 'none'; frame-ancestors 'none'")
            self.end_headers()

        def _error(self, status: HTTPStatus, message: str) -> None:
            payload = json.dumps({"error": message}).encode("utf-8")
            self._headers(status, "application/json; charset=utf-8", len(payload))
            self.wfile.write(payload)

        def do_GET(self) -> None:
            path = urlsplit(self.path).path
            citation_match = re.fullmatch(r"/citation/(cit-[0-9a-f]{24})(/page\.png)?", path)
            document_match = re.fullmatch(r"/document/(sha256:[0-9a-f]{64})\.pdf", path)
            try:
                if citation_match:
                    citation = repository.validate(citation_match.group(1))
                    if citation_match.group(2):
                        source_path = repository.source_path(citation.source_filename)
                        with fitz.open(source_path) as document:
                            if citation.page_number > document.page_count:
                                raise StaleCitationError("cited page no longer exists")
                            pixmap = document[citation.page_number - 1].get_pixmap(
                                matrix=fitz.Matrix(1.5, 1.5), alpha=False
                            )
                            payload = pixmap.tobytes("png")
                        self._headers(HTTPStatus.OK, "image/png", len(payload))
                    else:
                        payload = _viewer_html(citation)
                        self._headers(HTTPStatus.OK, "text/html; charset=utf-8", len(payload))
                    self.wfile.write(payload)
                    return
                if document_match:
                    document_id = document_match.group(1)
                    data = repository.store.load()
                    raw = data["documents"].get(document_id)
                    if not isinstance(raw, dict):
                        raise CitationNotFoundError("document is not indexed")
                    related = next(
                        (
                            citation_id
                            for citation_id, item in data["citations"].items()
                            if item.get("document_id") == document_id
                        ),
                        None,
                    )
                    if related is None:
                        raise CitationNotFoundError("document is not cited")
                    citation = repository.validate(related)
                    if citation.document_id != document_id:
                        raise CitationInputError("document index does not match citation")
                    payload = repository.source_path(citation.source_filename).read_bytes()
                    self._headers(HTTPStatus.OK, "application/pdf", len(payload))
                    self.wfile.write(payload)
                    return
                self._error(HTTPStatus.NOT_FOUND, "resource not found")
            except CitationNotFoundError:
                self._error(HTTPStatus.NOT_FOUND, "resource not found")
            except StaleCitationError:
                self._error(HTTPStatus.CONFLICT, "citation is stale")
            except CitationError:
                self._error(HTTPStatus.BAD_REQUEST, "citation could not be resolved")
            except Exception:
                self._error(HTTPStatus.INTERNAL_SERVER_ERROR, "viewer request failed")

    return ThreadingHTTPServer((host, port), Handler)
