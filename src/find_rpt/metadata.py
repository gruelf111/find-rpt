from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime

from .evidence import EvidenceDocument


EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
ROLE_RE = re.compile(
    r"\b(?:equity|research|financial|senior|lead|covering)?\s*"
    r"(?:analyst|strategist|associate|director|head of research)\b",
    re.I,
)
TITLE_EXCLUSION_RE = re.compile(
    r"\b(?:bloomberg|reuters|analysts?|research team|target price|price target|"
    r"rating|telephone|phone|email|disclosures?|contents|page \d+|www\.)\b|@",
    re.I,
)
NAME_RE = re.compile(
    r"^(?:[A-Z][A-Za-z'\-]+\s+){1,3}[A-Z][A-Za-z'\-]+(?:,?\s+(?:CFA|ACA|CPA))?$"
)
DATE_LINE_RE = re.compile(
    r"^(?:publication date|published|date)?\s*:?[ \t]*"
    r"(?P<date>\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4}|\d{4}-\d{2}-\d{2}|\d{1,2}[./-]\d{1,2}[./-]\d{4})$",
    re.I,
)


@dataclass(frozen=True)
class AnalystMetadata:
    name: str
    role: str | None
    email: str | None
    evidence_block_ids: tuple[str, ...]


@dataclass(frozen=True)
class ReportMetadata:
    title: str | None
    title_evidence_block_ids: tuple[str, ...]
    internal_publication_date: str | None
    analysts: tuple[AnalystMetadata, ...]
    warnings: tuple[str, ...]
    internal_publication_date_evidence_block_ids: tuple[str, ...] = ()
    document_id: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)


def _clean_line(value: str) -> str:
    return " ".join(value.split()).strip(" |")


def _title_score(line: str, *, y: float, height: float, line_height: float) -> float:
    words = re.findall(r"[A-Za-z][A-Za-z0-9&'\-/]*", line)
    if not 3 <= len(words) <= 24:
        return -1
    if not 12 <= len(line) <= 220 or TITLE_EXCLUSION_RE.search(line):
        return -1
    if sum(character.isalpha() for character in line) / max(1, len(line)) < 0.55:
        return -1
    if re.fullmatch(r"[A-Z]{1,6}(?:\s+[A-Z]{2})?", line):
        return -1
    position_score = max(0.0, 70.0 - (y / max(height, 1.0) * 100.0))
    shape_score = min(line_height, 28.0) * 2.0
    prose_score = 12.0 if 4 <= len(words) <= 16 else 0.0
    punctuation_score = 4.0 if re.search(r"[:\-–—]", line) else 0.0
    return position_score + shape_score + prose_score + punctuation_score


def _parse_date(value: str) -> str | None:
    for format_string in ("%d %B %Y", "%d %b %Y", "%Y-%m-%d", "%d/%m/%Y", "%d.%m.%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(value, format_string).date().isoformat()
        except ValueError:
            continue
    return None


class ReportMetadataExtractor:
    """Conservatively extract cited front-matter fields from page-one evidence.

    This adapter is intentionally separate from the renderer. It does not infer a
    person's name from an email local part and returns missing fields explicitly.
    """

    def extract(self, document: EvidenceDocument) -> ReportMetadata:
        page = next((item for item in document.pages if item.page_number == 1), None)
        if page is None:
            return ReportMetadata(
                None,
                (),
                None,
                (),
                ("page_one_not_available_for_metadata", "report_title_not_identified", "analyst_not_identified"),
                document_id=document.document_id,
            )

        candidates: list[tuple[float, int, str, str]] = []
        for order, block in enumerate(page.blocks[:40]):
            if block.bbox[1] > page.height * 0.48:
                continue
            lines = [_clean_line(line) for line in block.text.splitlines() if _clean_line(line)]
            line_height = (block.bbox[3] - block.bbox[1]) / max(1, len(lines))
            for line in lines:
                score = _title_score(
                    line,
                    y=block.bbox[1],
                    height=page.height,
                    line_height=line_height,
                )
                if score >= 0:
                    candidates.append((score, -order, line, block.block_id))
        candidates.sort(reverse=True)
        title = candidates[0][2] if candidates else None
        title_ids = (candidates[0][3],) if candidates else ()

        publication_dates: list[tuple[str, str]] = []
        for block in page.blocks:
            if block.bbox[1] > page.height * 0.25:
                continue
            for raw_line in block.text.splitlines():
                line = _clean_line(raw_line)
                match = DATE_LINE_RE.fullmatch(line)
                if not match:
                    continue
                parsed = _parse_date(match.group("date"))
                if parsed:
                    publication_dates.append((parsed, block.block_id))
        distinct_dates = tuple(dict.fromkeys(date for date, _ in publication_dates))
        internal_date = distinct_dates[0] if len(distinct_dates) == 1 else None
        internal_date_ids = tuple(
            dict.fromkeys(block_id for date, block_id in publication_dates if date == internal_date)
        ) if internal_date else ()

        analysts: list[AnalystMetadata] = []
        seen: set[tuple[str, str | None]] = set()
        for block in page.blocks:
            emails = EMAIL_RE.findall(block.text)
            if not emails:
                continue
            lines = [_clean_line(line) for line in block.text.splitlines() if _clean_line(line)]
            for email in emails:
                email_index = next(
                    (index for index, line in enumerate(lines) if email.casefold() in line.casefold()),
                    -1,
                )
                nearby = lines[max(0, email_index - 3) : email_index + 2]
                name = next(
                    (
                        line
                        for line in reversed(nearby)
                        if NAME_RE.fullmatch(line) and not ROLE_RE.search(line)
                    ),
                    None,
                )
                if name is None:
                    continue
                role_match = next((ROLE_RE.search(line) for line in nearby if ROLE_RE.search(line)), None)
                role = _clean_line(role_match.group(0)) if role_match else None
                key = (name.casefold(), email.casefold())
                if key in seen:
                    continue
                seen.add(key)
                analysts.append(AnalystMetadata(name, role, email, (block.block_id,)))

        warnings: list[str] = []
        if title is None:
            warnings.append("report_title_not_identified")
        if not analysts:
            warnings.append("analyst_not_identified")
        return ReportMetadata(
            title=title,
            title_evidence_block_ids=title_ids,
            internal_publication_date=internal_date,
            analysts=tuple(analysts),
            warnings=tuple(warnings),
            internal_publication_date_evidence_block_ids=internal_date_ids,
            document_id=document.document_id,
        )
