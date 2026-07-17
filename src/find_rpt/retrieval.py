from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Protocol

from pypdf import PdfReader


FILENAME_RE = re.compile(
    r"^(?P<date>\d{8})_(?P<broker>.+)_(?P<digest>[0-9a-f]{32})\.pdf$",
    re.IGNORECASE,
)
EXCHANGE_ALIASES = {"GY": "GR"}
STRONG_MATCH = 80
SAFE_MARGIN = 20


def normalize_date(value: str) -> str:
    if re.fullmatch(r"\d{8}", value):
        digits = value
    elif re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        digits = value.replace("-", "")
    else:
        raise ValueError("date must be YYYYMMDD or YYYY-MM-DD")
    datetime.strptime(digits, "%Y%m%d")
    return digits


def normalize_broker(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).casefold()
    return "".join(character for character in normalized if character.isalnum())


def normalize_ticker(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).upper()
    tokens = re.findall(r"[A-Z0-9]+", normalized)
    if len(tokens) != 2 or not re.fullmatch(r"[A-Z]{2}", tokens[1]):
        raise ValueError("ticker must contain one security code and a two-letter exchange suffix")
    tokens[-1] = EXCHANGE_ALIASES.get(tokens[-1], tokens[-1])
    return " ".join(tokens)


def _normalized_line(value: str) -> str:
    tokens = re.findall(r"[A-Z0-9]+", unicodedata.normalize("NFKD", value).upper())
    return " ".join(EXCHANGE_ALIASES.get(token, token) for token in tokens)


def _contains_ticker(line: str, ticker: str) -> bool:
    normalized = _normalized_line(line)
    if re.search(rf"(?<![A-Z0-9]){re.escape(ticker)}(?![A-Z0-9])", normalized):
        return True

    # Some embedded PDF text layers collapse a Bloomberg root and exchange suffix
    # inside a delimited identifier row (for example, ``SOIFP|SOIT.PA``). Accept
    # only that exact compact token in an identifier-shaped line; matching compact
    # tokens in ordinary prose would turn common words into false ticker evidence.
    compact_ticker = ticker.replace(" ", "")
    compact_line = unicodedata.normalize("NFKD", line).upper()
    return bool(
        re.search(r"[,/|():]", compact_line)
        and re.search(
            rf"(?<![A-Z0-9]){re.escape(compact_ticker)}(?![A-Z0-9])",
            compact_line,
        )
    )


@dataclass(frozen=True)
class Query:
    ticker: str
    normalized_ticker: str
    date: str
    broker: str
    normalized_broker: str


@dataclass(frozen=True)
class Evidence:
    page: int
    line: int
    kind: str
    score: int
    matched_ticker: str


@dataclass
class Candidate:
    filename: str
    path: str
    score: int = 0
    confidence: str = "none"
    pages_inspected: list[int] = field(default_factory=list)
    evidence: list[Evidence] = field(default_factory=list)
    error: str | None = None


@dataclass
class RetrievalResult:
    status: str
    query: Query
    reason: str
    match: Candidate | None
    candidates: list[Candidate]

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)


class PageInspector(Protocol):
    def extract_page(self, path: Path, page_index: int) -> str | None:
        """Return page text, or None if the page does not exist."""


class PypdfInspector:
    def extract_page(self, path: Path, page_index: int) -> str | None:
        with path.open("rb") as source:
            if b"%PDF-" not in source.read(1024):
                raise ValueError("invalid PDF signature")
            source.seek(0)
            reader = PdfReader(source)
            if page_index >= len(reader.pages):
                return None
            return reader.pages[page_index].extract_text() or ""


def parse_corpus_filename(path: Path) -> tuple[str, str] | None:
    match = FILENAME_RE.fullmatch(path.name)
    if not match:
        return None
    return match.group("date"), match.group("broker")


def _is_field_label(line: str, label: str) -> bool:
    compact = " ".join(line.split()).upper()
    if len(compact) > 140:
        return False
    if compact.startswith(label):
        return True
    tokens = set(re.findall(r"[A-Z]+", compact))
    return (
        compact.startswith(("REUTERS ", "EXCHANGE "))
        and label in tokens
        and len(tokens) <= 8
    )


def _looks_like_paired_identifier(line: str) -> bool:
    if len(line) > 120 or not re.search(r"[,/|()]", line):
        return False
    tokens = re.findall(r"[A-Z0-9]+", line.upper())
    return 3 <= len(tokens) <= 6


def _confidence_for_score(score: int) -> str:
    if score >= 105:
        return "high_explicit"
    if score >= STRONG_MATCH:
        return "strong"
    if score > 0:
        return "weak"
    return "none"


def _evidence_for_page(text: str, ticker: str, page: int) -> list[Evidence]:
    evidence: list[Evidence] = []
    nonempty_lines = [
        (line_number, " ".join(raw_line.split()))
        for line_number, raw_line in enumerate(text.splitlines(), start=1)
        if raw_line.strip()
    ]
    for index, (line_number, line) in enumerate(nonempty_lines):
        if not _contains_ticker(line, ticker):
            continue

        prior_lines = [item[1] for item in nonempty_lines[max(0, index - 2) : index]]
        if _is_field_label(line, "BLOOMBERG") or any(
            _is_field_label(prior, "BLOOMBERG") for prior in prior_lines
        ):
            score = 120 if page == 1 else 95
            kind = "explicit_bloomberg_field"
        elif _is_field_label(line, "TICKER") or any(
            _is_field_label(prior, "TICKER") for prior in prior_lines
        ):
            score = 105 if page == 1 else 85
            kind = "explicit_ticker_field"
        elif page == 1 and (line_number <= 25 or _looks_like_paired_identifier(line)):
            score = 85
            kind = "header_or_title"
        elif page == 1 and line_number <= 45:
            score = 55
            kind = "possible_header"
        elif page == 1:
            score = 25
            kind = "first_page_body"
        elif line_number <= 30:
            score = 45
            kind = "later_page_header"
        else:
            score = 15
            kind = "later_page_body"

        evidence.append(
            Evidence(
                page=page,
                line=line_number,
                kind=kind,
                score=score,
                matched_ticker=ticker,
            )
        )
    return evidence


class RetrievalEngine:
    def __init__(self, corpus: Path | str, inspector: PageInspector | None = None):
        self.corpus = Path(corpus)
        self.inspector = inspector or PypdfInspector()

    def _query(self, ticker: str, date: str, broker: str) -> Query:
        normalized_broker = normalize_broker(broker)
        if not normalized_broker:
            raise ValueError("broker must not be empty")
        return Query(
            ticker=ticker,
            normalized_ticker=normalize_ticker(ticker),
            date=normalize_date(date),
            broker=broker,
            normalized_broker=normalized_broker,
        )

    def _shortlist(self, query: Query) -> list[Candidate]:
        candidates: list[Candidate] = []
        if not self.corpus.is_dir():
            return candidates
        paths = (
            path
            for path in self.corpus.iterdir()
            if path.is_file() and path.suffix.casefold() == ".pdf"
        )
        for path in sorted(paths, key=lambda item: item.name.casefold()):
            parsed = parse_corpus_filename(path)
            if parsed is None:
                continue
            file_date, file_broker = parsed
            if file_date != query.date:
                continue
            if normalize_broker(file_broker) != query.normalized_broker:
                continue
            candidates.append(
                Candidate(
                    filename=path.name,
                    path=PurePosixPath(self.corpus.name, path.name).as_posix(),
                )
            )
        return candidates

    def _inspect(self, candidates: list[Candidate], query: Query, page_index: int) -> None:
        for candidate in candidates:
            if candidate.error is not None:
                continue
            path = self.corpus / candidate.filename
            if path.is_symlink():
                candidate.error = "UnsafePath: symbolic links are not allowed"
                continue
            try:
                text = self.inspector.extract_page(path, page_index)
            except Exception as error:  # Per-file errors are result data, not fatal query errors.
                candidate.error = f"{type(error).__name__}: page inspection failed"
                continue
            if text is None:
                continue
            page = page_index + 1
            candidate.pages_inspected.append(page)
            candidate.evidence.extend(_evidence_for_page(text, query.normalized_ticker, page))
            candidate.evidence.sort(key=lambda item: (-item.score, item.page, item.line))
            candidate.score = candidate.evidence[0].score if candidate.evidence else 0
            candidate.confidence = _confidence_for_score(candidate.score)

    @staticmethod
    def _rank(candidates: list[Candidate]) -> list[Candidate]:
        return sorted(
            candidates,
            key=lambda candidate: (
                -candidate.score,
                candidate.error is not None,
                candidate.filename.casefold(),
            ),
        )

    @staticmethod
    def _safe_match(candidates: list[Candidate]) -> Candidate | None:
        ranked = RetrievalEngine._rank(candidates)
        if any(candidate.error is not None for candidate in ranked):
            return None
        viable = [candidate for candidate in ranked if candidate.error is None]
        if not viable or viable[0].score < STRONG_MATCH:
            return None
        runner_score = viable[1].score if len(viable) > 1 else 0
        if viable[0].score - runner_score < SAFE_MARGIN:
            return None
        return viable[0]

    def retrieve(self, ticker: str, date: str, broker: str) -> RetrievalResult:
        query = self._query(ticker, date, broker)
        if not self.corpus.is_dir():
            return RetrievalResult(
                status="not_found",
                query=query,
                reason="The corpus path does not exist or is not a directory.",
                match=None,
                candidates=[],
            )
        candidates = self._shortlist(query)
        if not candidates:
            return RetrievalResult(
                status="not_found",
                query=query,
                reason="No files matched the filename date and broker.",
                match=None,
                candidates=[],
            )

        self._inspect(candidates, query, page_index=0)
        match = self._safe_match(candidates)
        if match is not None:
            return RetrievalResult(
                status="found",
                query=query,
                reason="One candidate had unique strong page-1 ticker evidence.",
                match=match,
                candidates=self._rank(candidates),
            )

        # Page 2 is the bounded fallback. It is read only when page 1 did not safely decide.
        self._inspect(candidates, query, page_index=1)
        ranked = self._rank(candidates)
        match = self._safe_match(ranked)
        if match is not None:
            return RetrievalResult(
                status="found",
                query=query,
                reason="One candidate had unique strong ticker evidence after the page-2 fallback.",
                match=match,
                candidates=ranked,
            )

        matched = [candidate for candidate in ranked if candidate.score > 0]
        errors = [candidate for candidate in ranked if candidate.error is not None]
        if errors:
            return RetrievalResult(
                status="ambiguous",
                query=query,
                reason=(
                    "One or more shortlisted candidates could not be inspected, so a unique "
                    "ticker match cannot be established safely."
                ),
                match=None,
                candidates=ranked,
            )
        if not matched:
            return RetrievalResult(
                status="not_found",
                query=query,
                reason="No ticker evidence was found in the first two pages of the shortlisted files.",
                match=None,
                candidates=ranked,
            )

        top = matched[0]
        tied = len(matched) > 1 and top.score - matched[1].score < SAFE_MARGIN
        reason = (
            "The leading candidates were tied or too close to select safely."
            if tied
            else "Ticker evidence existed, but the strongest evidence was too weak to select safely."
        )
        return RetrievalResult(
            status="ambiguous",
            query=query,
            reason=reason,
            match=None,
            candidates=ranked,
        )
