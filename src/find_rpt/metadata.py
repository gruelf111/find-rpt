from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime

from .evidence import EvidenceDocument


EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
PHONE_RE = re.compile(r"(?<!\w)(?:\+\d{1,3}[\s.-]?)?(?:\(?\d{2,4}\)?[\s.-]?){2,4}\d{2,4}(?!\w)")
ROLE_RE = re.compile(
    r"\b(?:(?:equity|research|financial|senior|lead|covering|primary)\s+){0,3}"
    r"(?:analyst|strategist|associate|director|head of(?:\s+[A-Za-z&-]+){0,5}\s+research)\b",
    re.I,
)
EXCLUDED_CONTACT_RE = re.compile(
    r"\b(?:sales|specialist sales|ESG|environmental social governance|media|press|"
    r"compliance|disclosure|editor|publishing)\b",
    re.I,
)
GENERIC_NAME_LINE_RE = re.compile(
    r"^(?:equity research|company research|global research|investment research|"
    r"research team|company update|analyst certification|important information)$",
    re.I,
)
TITLE_EXCLUSION_RE = re.compile(
    r"\b(?:bloomberg|reuters|analysts?|research|target price|price target|"
    r"rating|telephone|phone|email|disclosures?|contents|page \d+|www\.|"
    r"equity research|company research|first reaction note|first take|company update|"
    r"this insert is part of|sector report)\b|\b(?:sector|price)\s*:|@",
    re.I,
)
SHORT_RATING_LINE_RE = re.compile(
    r"^(?:[A-Za-z0-9.&'’\-]+\s+){0,3}"
    r"(?:buy|hold|sell|overweight|underweight|neutral|outperform|underperform)"
    r"(?:\s*\([^)]{1,20}\))?$",
    re.I,
)
NAME_RE = re.compile(
    r"^(?P<name>(?:[A-Z][A-Za-z'’\-]+\s+){1,3}[A-Z][A-Za-z'’\-]+)"
    r"(?:,?\s+(?P<designation>CFA|ACA|CPA|CA))?$"
)
CONTACT_NAME_RE = re.compile(
    r"^(?P<name>(?:[A-Z][A-Za-z'’\-]+\s+){1,3}[A-Z][A-Za-z'’\-]+)"
    r"(?:,?\s*(?P<designation>CFA|ACA|CPA|CA|PhD))?"
    r"(?=\s*(?:[*†‡]\s*)?(?:[|:>•(]|\+?\d|$))"
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
    designation: str | None = None
    phone: str | None = None
    selection_status: str = "relevant"
    source_location: str = "report_contact_evidence"


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


def _plausible_person_name(value: str) -> bool:
    tokens = value.replace("-", " ").split()
    if not 2 <= len(tokens) <= 5:
        return False
    return all(not (token.isupper() and len(token) > 1) for token in tokens)


def _title_score(line: str, *, y: float, height: float, line_height: float) -> float:
    words = re.findall(r"[A-Za-z][A-Za-z0-9&'\-/]*", line)
    if not 3 <= len(words) <= 24:
        return -1
    if (
        not 12 <= len(line) <= 220
        or TITLE_EXCLUSION_RE.search(line)
        or SHORT_RATING_LINE_RE.fullmatch(line)
    ):
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
            for start in range(len(lines)):
                for length in range(1, min(3, len(lines) - start) + 1):
                    if length > 1 and any(
                        len(re.findall(r"[A-Za-z0-9]+", part)) < 2
                        for part in lines[start : start + length]
                    ):
                        continue
                    line = " ".join(lines[start : start + length])
                    score = _title_score(
                        line,
                        y=block.bbox[1],
                        height=page.height,
                        line_height=line_height,
                    )
                    if score >= 0:
                        candidates.append(
                            (score + 6.0 * (length - 1), -order, line, block.block_id)
                        )
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
        for evidence_page in document.pages:
            blocks = evidence_page.blocks
            for block_index, block in enumerate(blocks):
                lines = [_clean_line(line) for line in block.text.splitlines() if _clean_line(line)]
                for line_index, line in enumerate(lines):
                    name_match = NAME_RE.fullmatch(line) or CONTACT_NAME_RE.match(line)
                    if (
                        name_match is None
                        or ROLE_RE.search(name_match.group("name"))
                        or GENERIC_NAME_LINE_RE.fullmatch(name_match.group("name"))
                        or not _plausible_person_name(name_match.group("name"))
                    ):
                        continue
                    nearby_blocks = tuple(
                        candidate
                        for candidate in blocks[max(0, block_index - 3) : block_index + 4]
                        if candidate.block_id == block.block_id
                        or (
                            candidate.bbox[1] <= block.bbox[3] + 120
                            and candidate.bbox[3] >= block.bbox[1] - 120
                            and abs(candidate.bbox[0] - block.bbox[0]) <= 120
                        )
                    )
                    nearby_text = "\n".join(candidate.text for candidate in nearby_blocks)
                    same_line_email = EMAIL_RE.findall(line)
                    block_email_lines = [
                        (index, email)
                        for index, candidate_line in enumerate(lines)
                        for email in EMAIL_RE.findall(candidate_line)
                    ]
                    nearest_block_emails: tuple[str, ...] = ()
                    if block_email_lines:
                        nearest_distance = min(abs(index - line_index) for index, _ in block_email_lines)
                        nearest_block_emails = tuple(
                            dict.fromkeys(
                                email
                                for index, email in block_email_lines
                                if abs(index - line_index) == nearest_distance
                            )
                        )
                    nearby_emails = tuple(dict.fromkeys(EMAIL_RE.findall(nearby_text)))
                    positioned_emails = [
                        (
                            0 if candidate.bbox[1] >= block.bbox[1] else 1,
                            abs(candidate.bbox[1] - block.bbox[1]),
                            email,
                        )
                        for candidate in nearby_blocks
                        for email in EMAIL_RE.findall(candidate.text)
                    ]
                    closest_positioned_emails: tuple[str, ...] = ()
                    if positioned_emails:
                        best_position = min((direction, distance) for direction, distance, _ in positioned_emails)
                        closest_positioned_emails = tuple(
                            dict.fromkeys(
                                email
                                for direction, distance, email in positioned_emails
                                if (direction, distance) == best_position
                            )
                        )
                    email = (
                        same_line_email[0]
                        if len(same_line_email) == 1
                        else nearest_block_emails[0]
                        if len(nearest_block_emails) == 1
                        else closest_positioned_emails[0]
                        if len(closest_positioned_emails) == 1
                        else nearby_emails[0]
                        if len(nearby_emails) == 1
                        else None
                    )
                    block_role_lines = [
                        (index, match)
                        for index, candidate_line in enumerate(lines)
                        for match in ROLE_RE.finditer(candidate_line)
                    ]
                    role_match = (
                        min(block_role_lines, key=lambda item: (abs(item[0] - line_index), item[0]))[1]
                        if block_role_lines
                        else next(iter(ROLE_RE.finditer(nearby_text)), None)
                    )
                    role = _clean_line(role_match.group(0)) if role_match else None
                    explicit_certification = bool(
                        re.search(
                            rf"\b(?:I,?\s+{re.escape(name_match.group('name'))}|"
                            rf"{re.escape(name_match.group('name'))}\s+(?:hereby\s+)?certif(?:y|ies))\b",
                            nearby_text,
                            re.I,
                        )
                    )
                    strong_contact_link = bool(
                        same_line_email or block_email_lines or block_role_lines
                    )
                    explicit_contact_context = bool(
                        (
                            evidence_page.page_number == 1
                            and (
                                (email and strong_contact_link)
                                or (role and bool(block_role_lines))
                                or (
                                    strong_contact_link
                                    and re.search(r"\b(?:analysts?|research team|byline|author)\b", nearby_text, re.I)
                                )
                            )
                        )
                        or (explicit_certification and email is not None)
                    )
                    if not explicit_contact_context:
                        continue
                    identity_context = "\n".join(
                        lines[max(0, line_index - 1) : line_index + 2]
                    ) + (f"\n{role}" if role else "")
                    if EXCLUDED_CONTACT_RE.search(identity_context) and not re.search(
                        r"\b(?:equity|research|covering|lead)\s+analyst\b",
                        identity_context,
                        re.I,
                    ):
                        continue
                    phone_lines = [
                        (index, match.group(0).strip())
                        for index, candidate_line in enumerate(lines)
                        for match in PHONE_RE.finditer(candidate_line)
                    ]
                    nearest_phone = None
                    if phone_lines:
                        nearest_distance = min(abs(index - line_index) for index, _ in phone_lines)
                        nearest_phones = tuple(
                            dict.fromkeys(
                                phone for index, phone in phone_lines if abs(index - line_index) == nearest_distance
                            )
                        )
                        nearest_phone = nearest_phones[0] if len(nearest_phones) == 1 else None
                    selection_status = (
                        "covering"
                        if re.search(r"\bcovering\s+analyst\b", nearby_text, re.I)
                        else "lead"
                        if re.search(r"\b(?:lead|primary)\s+(?:equity|research\s+)?analyst\b", nearby_text, re.I)
                        else "relevant"
                    )
                    evidence_ids = tuple(
                        dict.fromkeys(
                            candidate.block_id
                            for candidate in nearby_blocks
                            if candidate.block_id == block.block_id
                            or (email and email.casefold() in candidate.text.casefold())
                            or (role and role.casefold() in candidate.text.casefold())
                            or (
                                nearest_phone
                                and nearest_phone in _clean_line(candidate.text)
                            )
                            or (
                                selection_status != "relevant"
                                and re.search(
                                    r"\b(?:covering|lead|primary)\s+(?:equity|research\s+)?analyst\b",
                                    candidate.text,
                                    re.I,
                                )
                            )
                        )
                    )
                    source_location = (
                        "first_page_byline_or_contact"
                        if evidence_page.page_number == 1
                        else "analyst_certification"
                        if re.search(r"\banalyst certification\b", nearby_text, re.I)
                        else "report_footer_or_contact"
                    )
                    name = name_match.group("name")
                    designation = name_match.group("designation")
                    key = (name.casefold(), email.casefold() if email else None)
                    if key in seen:
                        continue
                    seen.add(key)
                    analysts.append(
                        AnalystMetadata(
                            name=name,
                            role=role,
                            email=email,
                            evidence_block_ids=evidence_ids,
                            designation=designation,
                            phone=nearest_phone,
                            selection_status=selection_status,
                            source_location=source_location,
                        )
                    )

        analysts.sort(
            key=lambda analyst: (
                {"covering": 0, "lead": 1, "relevant": 2}.get(analyst.selection_status, 3),
                analyst.name.casefold(),
                analyst.email or "",
            )
        )

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
