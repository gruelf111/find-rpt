from __future__ import annotations

import json
import math
import re
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import PurePath
from typing import Iterable

from .citations import CitationBuildResult, CitationRecord
from .escalation import (
    DraftAnalyst,
    EmailDraft,
    EscalationResult,
    render_email_draft_markdown,
)
from .metadata import ReportMetadata
from .rationale import GroundedClaim, RationaleResult
from .revisions import EstimateRevision, RevisionResult


MISSING = "—"
DEFAULT_MAX_REVISION_ROWS = 8
DEFAULT_MAX_FIRST_READ_ITEMS = 4
METRIC_ORDER = {
    "revenue": 10,
    "reinsurance_revenue_gross": 11,
    "reinsurance_revenue_net": 12,
    "ebitda": 20,
    "ebit": 30,
    "operating_profit": 31,
    "gross_margin": 40,
    "ebitda_margin": 41,
    "ebit_margin": 42,
    "operating_margin": 43,
    "net_margin": 44,
    "eps": 50,
    "tax": 60,
    "tax_rate": 61,
    "interest_expense": 62,
    "net_interest_income": 63,
    "share_count": 64,
    "target_price": 70,
}
MATERIAL_ARITHMETIC_WARNINGS = {
    "old_new_unit_mismatch",
    "consensus_unit_mismatch",
    "zero_old_value_no_relative_revision",
    "zero_consensus_no_relative_spread",
    "stated_calculated_revision_mismatch",
    "stated_calculated_percentage_point_mismatch",
    "conflicting_candidates_same_metric_period",
}
CONTEXT_LABELS = {
    "results_preview": "results preview",
    "results_review": "results review",
    "roadshow": "roadshow",
    "management_meeting": "management meeting",
    "initiation": "coverage initiation",
    "reiteration": "reiteration",
    "rating_change": "rating change",
    "event_reaction": "event reaction",
    "other": "other stated context",
    "not_given": "context not given",
}


@dataclass(frozen=True)
class BriefCitation:
    citation_id: str
    label: str
    local_url: str
    page_number: int


@dataclass(frozen=True)
class BriefAnalyst:
    name: str
    role: str | None
    email: str | None
    citations: tuple[BriefCitation, ...]


@dataclass(frozen=True)
class BriefRevisionRow:
    metric: str
    metric_qualifiers: tuple[str, ...]
    fiscal_period: str | None
    old_value: float | None
    new_value: float | None
    revision_percentage: float | None
    revision_kind: str | None
    consensus_value: float | None
    old_vs_consensus: float | None
    new_vs_consensus: float | None
    unit: str | None
    direction: str
    citations: tuple[BriefCitation, ...]
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class EstimateVisualization:
    metric: str
    fiscal_period: str | None
    unit: str
    lines: tuple[str, ...]
    plain_text: str


@dataclass(frozen=True)
class ResearchBrief:
    ticker: str
    broker: str
    report_date: str
    internal_publication_date: str | None
    internal_publication_date_citations: tuple[BriefCitation, ...]
    report_title: str | None
    takeaway: str | None
    takeaway_citations: tuple[BriefCitation, ...]
    revisions_status: str
    revision_rows: tuple[BriefRevisionRow, ...]
    omitted_revision_rows: int
    rationale_clarity: str | None
    rationale_paragraphs: tuple[str, ...]
    estimate_visualizations: tuple[EstimateVisualization, ...]
    first_read_items: tuple[str, ...]
    source_identifier: str
    analysts: tuple[BriefAnalyst, ...]
    primary_citation: BriefCitation | None
    warnings: tuple[str, ...]
    requires_analyst_escalation: bool
    escalation_reason: str | None
    analyst: tuple[DraftAnalyst, ...]
    email_draft: EmailDraft | None

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)


def _citation_map(result: CitationBuildResult | None) -> dict[str, tuple[BriefCitation, ...]]:
    mapped: dict[str, list[BriefCitation]] = {}
    if result is None:
        return {}
    by_id: dict[str, BriefCitation] = {}
    for item in result.citations:
        if item.validation_status != "valid":
            continue
        rendered = BriefCitation(item.citation_id, item.evidence_label, item.local_url, item.page_number)
        by_id[item.citation_id] = rendered
        if item.claim_key is None:
            continue
        mapped.setdefault(item.claim_key, []).append(rendered)
    for claim_key, citation_id in result.claim_bindings:
        if citation_id in by_id:
            mapped.setdefault(claim_key, []).append(by_id[citation_id])
    return {key: tuple(dict.fromkeys(value)) for key, value in mapped.items()}


def _citation_markdown(citations: Iterable[BriefCitation], label: str = "source") -> str:
    items = tuple(citations)
    if not items:
        return ""
    links = [f"[{label if index == 1 else f'{label} {index}'}]({item.local_url})" for index, item in enumerate(items, 1)]
    return " " + " ".join(links)


def _metric_label(metric: str) -> str:
    labels = {
        "eps": "EPS",
        "ebit": "EBIT",
        "ebitda": "EBITDA",
        "dps": "DPS",
        "cet1_ratio": "CET1 ratio",
    }
    return labels.get(metric, metric.replace("_", " ").title())


def _sort_key(revision: EstimateRevision) -> tuple:
    return (
        METRIC_ORDER.get(revision.metric, 100),
        revision.metric,
        revision.metric_qualifiers,
        revision.fiscal_period or "",
        revision.evidence[0].page_number if revision.evidence else 0,
    )


def _materiality_key(item: tuple[int, EstimateRevision]) -> tuple:
    index, revision = item
    has_complete_comparison = revision.old_value is not None and revision.new_value is not None
    return (
        revision.consensus_value is None,
        not has_complete_comparison,
        METRIC_ORDER.get(revision.metric, 100),
        revision.metric,
        revision.fiscal_period or "",
        index,
    )


def _row_citations(index: int, revision: EstimateRevision, citations: dict[str, tuple[BriefCitation, ...]]) -> tuple[BriefCitation, ...]:
    values: list[BriefCitation] = []
    for evidence_index, _ in enumerate(revision.evidence, 1):
        values.extend(citations.get(f"revision:{index}:evidence:{evidence_index}", ()))
    return tuple(dict.fromkeys(values))


def _select_revision_rows(revisions: RevisionResult, citation_map: dict[str, tuple[BriefCitation, ...]], max_rows: int) -> tuple[tuple[BriefRevisionRow, ...], int]:
    indexed = list(enumerate(revisions.revisions, 1))
    supported = [item for item in indexed if _row_citations(item[0], item[1], citation_map)]
    selected = sorted(supported, key=_materiality_key)[:max_rows]
    selected.sort(key=lambda item: _sort_key(item[1]))
    rows: list[BriefRevisionRow] = []
    for original_index, revision in selected:
        if revision.stated_change_pp is not None or revision.calculated_change_pp is not None:
            change = revision.stated_change_pp if revision.stated_change_pp is not None else revision.calculated_change_pp
            kind = "percentage_points"
        else:
            change = revision.stated_revision_pct if revision.stated_revision_pct is not None else revision.calculated_revision_pct
            kind = "percentage"
        rows.append(
            BriefRevisionRow(
                metric=revision.metric,
                metric_qualifiers=revision.metric_qualifiers,
                fiscal_period=revision.fiscal_period,
                old_value=revision.old_value,
                new_value=revision.new_value,
                revision_percentage=change,
                revision_kind=kind if change is not None else None,
                consensus_value=revision.consensus_value,
                old_vs_consensus=revision.old_vs_consensus_pct,
                new_vs_consensus=revision.new_vs_consensus_pct,
                unit=revision.unit,
                direction=revision.direction,
                citations=_row_citations(original_index, revision, citation_map),
                warnings=tuple(item for item in revision.warnings if item in MATERIAL_ARITHMETIC_WARNINGS),
            )
        )
    return tuple(rows), max(0, len(supported) - len(selected))


def _format_number(value: float | None) -> str:
    if value is None:
        return MISSING
    if value == 0:
        return "0"
    absolute = abs(value)
    if absolute >= 100:
        return f"{value:,.0f}"
    if absolute >= 10:
        return f"{value:,.1f}".rstrip("0").rstrip(".")
    if absolute >= 1:
        return f"{value:,.2f}".rstrip("0").rstrip(".")
    if absolute >= 0.01:
        return f"{value:,.3f}".rstrip("0").rstrip(".")
    return f"{value:,.4f}".rstrip("0").rstrip(".")


def _format_value(value: float | None, unit: str | None) -> str:
    if value is None:
        return MISSING
    rendered = _format_number(value)
    if unit == "%":
        return f"{rendered}%"
    if unit == "percentage_points":
        return f"{rendered}pp"
    if unit == "basis_points":
        return f"{rendered}bp"
    return f"{rendered} {unit}" if unit else rendered


def _format_change(value: float | None, kind: str | None) -> str:
    if value is None:
        return MISSING
    sign = "+" if value > 0 else ""
    suffix = "pp" if kind == "percentage_points" else "%"
    return f"{sign}{_format_number(value)}{suffix}"


def _bar_line(label: str, value: float, maximum: float, *, half_width: int = 10) -> str:
    if maximum <= 0:
        count = 0
    else:
        count = max(1 if value else 0, round(abs(value) / maximum * half_width))
    left = ("█" * count).rjust(half_width) if value < 0 else " " * half_width
    right = ("█" * count).ljust(half_width) if value > 0 else " " * half_width
    return f"{label:<10} {left}│{right}  {_format_number(value)}"


def make_estimate_visualization(row: BriefRevisionRow) -> EstimateVisualization | None:
    observations = [("Old", row.old_value), ("New", row.new_value), ("Consensus", row.consensus_value)]
    values = [(label, value) for label, value in observations if value is not None and math.isfinite(value)]
    if len(values) < 2 or len({value for _, value in values}) < 2 or row.unit is None:
        return None
    maximum = max(abs(value) for _, value in values)
    if maximum == 0:
        return None
    lines = tuple(_bar_line(label, value, maximum) for label, value in values)
    title = f"{_metric_label(row.metric)} {row.fiscal_period or 'current'} ({row.unit})"
    return EstimateVisualization(row.metric, row.fiscal_period, row.unit, (title,) + lines, "\n".join((title,) + lines))


def _claim_text(claim: GroundedClaim, key: str, citation_map: dict[str, tuple[BriefCitation, ...]]) -> str:
    claim_citations = citation_map.get(key, ())
    if not claim_citations:
        return ""
    return claim.text.rstrip(".") + "." + _citation_markdown(claim_citations)


def _rationale_paragraphs(rationale: RationaleResult | None, citation_map: dict[str, tuple[BriefCitation, ...]]) -> tuple[tuple[str, ...], str | None, list[str]]:
    warnings: list[str] = []
    if rationale is None or rationale.extraction is None:
        warnings.append("rationale_not_available")
        return (), None, warnings
    extraction = rationale.extraction
    first: list[str] = []
    for index, driver in enumerate(extraction.drivers[:3], 1):
        driver_citations = citation_map.get(f"rationale:driver:{index}", ())
        if not driver_citations:
            continue
        sentence = driver.driver.rstrip(".") + "."
        first.append(sentence + _citation_markdown(driver_citations))
    if extraction.rationale_clarity == "partial":
        first.append("The report only partially explains the remaining estimate changes.")
    elif extraction.rationale_clarity == "unclear":
        first = ["The report gives revisions but does not clearly explain their cause."]

    second: list[str] = []
    context = CONTEXT_LABELS.get(extraction.report_context, "context not given")
    if extraction.report_context == "not_given":
        second.append("Publication context is not given.")
    else:
        context_citations = citation_map.get("rationale:context", ())
        if context_citations:
            second.append(f"Publication context: {context}." + _citation_markdown(context_citations))
    if extraction.why_now is not None:
        second.append(_claim_text(extraction.why_now, "rationale:why_now", citation_map))
    if extraction.management_contact == "true":
        people = ", ".join(
            f"{person.name}{f' ({person.role})' if person.role else ''}"
            for person in extraction.people_met
        )
        management_citations = citation_map.get("rationale:management", ())
        if management_citations:
            detail = f" Management interaction included {people}." if people else " The report states that the broker had management contact."
            second.append(detail.strip() + _citation_markdown(management_citations))
    return tuple(" ".join(part) for part in (first, second) if part), extraction.rationale_clarity, warnings


def _safe_source_identifier(value: str) -> str:
    return PurePath(value.replace("\\", "/")).name


class ResearchBriefBuilder:
    """Assemble a brief from validated structured results only."""

    def __init__(
        self,
        *,
        max_revision_rows: int = DEFAULT_MAX_REVISION_ROWS,
        max_visualizations: int = 2,
        max_first_read_items: int = DEFAULT_MAX_FIRST_READ_ITEMS,
    ):
        if max_revision_rows < 1 or max_visualizations < 0 or max_first_read_items < 0:
            raise ValueError("brief limits are invalid")
        self.max_revision_rows = max_revision_rows
        self.max_visualizations = max_visualizations
        self.max_first_read_items = max_first_read_items

    def build(
        self,
        *,
        ticker: str,
        broker: str,
        report_date: str,
        metadata: ReportMetadata,
        revisions: RevisionResult,
        rationale: RationaleResult | None,
        citations: CitationBuildResult | None,
        escalation: EscalationResult | None = None,
        include_visualization: bool = True,
    ) -> ResearchBrief:
        if rationale is not None and rationale.document_id != revisions.document_id:
            raise ValueError("rationale and revisions belong to different reports")
        if citations is not None and citations.document_id != revisions.document_id:
            raise ValueError("citations and revisions belong to different reports")
        if metadata.document_id is not None and metadata.document_id != revisions.document_id:
            raise ValueError("metadata and revisions belong to different reports")
        if escalation is not None and escalation.source_report_id != revisions.document_id:
            raise ValueError("escalation and revisions belong to different reports")
        citation_map = _citation_map(citations)
        rows, omitted = _select_revision_rows(revisions, citation_map, self.max_revision_rows)
        paragraphs, clarity, warnings = _rationale_paragraphs(rationale, citation_map)
        extraction = rationale.extraction if rationale is not None else None
        takeaway_citations = citation_map.get("rationale:takeaway", ())
        takeaway = (
            extraction.one_line_takeaway.text
            if extraction and extraction.one_line_takeaway and takeaway_citations
            else None
        )
        if takeaway is None:
            warnings.append("takeaway_not_available")
        if revisions.status == "no_revisions":
            warnings.append("no_estimate_revisions_found")
        elif revisions.status == "candidates_unresolved":
            warnings.append("revision_signals_unresolved")
        if omitted:
            warnings.append(f"additional_revision_rows_omitted:{omitted}")
        uncited_revision_rows = len(revisions.revisions) - len(
            [
                item
                for item in enumerate(revisions.revisions, 1)
                if _row_citations(item[0], item[1], citation_map)
            ]
        )
        if uncited_revision_rows:
            warnings.append(f"uncited_revision_rows_omitted:{uncited_revision_rows}")
        if citations is None:
            warnings.append("citations_not_available")
        elif citations.failed_requests:
            warnings.append(f"citation_requests_failed:{citations.failed_requests}")
        uncited_facts = 0
        uncited_facts += int(metadata.title is not None and not citation_map.get("metadata:title"))
        uncited_facts += int(
            metadata.internal_publication_date is not None
            and not citation_map.get("metadata:publication_date")
        )
        uncited_facts += sum(
            not citation_map.get(f"metadata:analyst:{index}")
            for index, _ in enumerate(metadata.analysts, 1)
        )
        if extraction is not None:
            uncited_facts += int(
                extraction.one_line_takeaway is not None
                and not citation_map.get("rationale:takeaway")
            )
            uncited_facts += sum(
                not citation_map.get(f"rationale:driver:{index}")
                for index, _ in enumerate(extraction.drivers[:3], 1)
            )
            uncited_facts += int(
                extraction.report_context != "not_given"
                and not citation_map.get("rationale:context")
            )
            uncited_facts += int(
                extraction.why_now is not None and not citation_map.get("rationale:why_now")
            )
            uncited_facts += int(
                extraction.management_contact == "true"
                and not citation_map.get("rationale:management")
            )
            uncited_facts += sum(
                not citation_map.get(f"rationale:first_read:{index}")
                for index, _ in enumerate(extraction.important_first_read_items, 1)
            )
        if uncited_facts:
            warnings.append(f"uncited_structured_facts_omitted:{uncited_facts}")
        warnings.extend(metadata.warnings)
        if rationale is not None:
            warnings.extend(rationale.warnings)
            if extraction is not None:
                warnings.extend(extraction.warnings)
        if escalation is not None:
            warnings.extend(escalation.warnings)

        visualizations: list[EstimateVisualization] = []
        if include_visualization:
            candidates = sorted(
                rows,
                key=lambda row: (
                    row.consensus_value is None,
                    METRIC_ORDER.get(row.metric, 100),
                    row.fiscal_period or "",
                ),
            )
            for row in candidates:
                visual = make_estimate_visualization(row)
                if visual is not None:
                    visualizations.append(visual)
                if len(visualizations) >= self.max_visualizations:
                    break

        first_read: list[str] = []
        if extraction is not None:
            for index, item in enumerate(extraction.important_first_read_items, 1):
                if len(first_read) >= self.max_first_read_items:
                    break
                rendered_item = _claim_text(item, f"rationale:first_read:{index}", citation_map)
                if rendered_item:
                    first_read.append(rendered_item)
            if len(extraction.important_first_read_items) > len(first_read):
                warnings.append(
                    f"additional_first_read_items_omitted:"
                    f"{len(extraction.important_first_read_items) - len(first_read)}"
                )

        analysts: list[BriefAnalyst] = []
        for index, analyst in enumerate(metadata.analysts, 1):
            analyst_citations = citation_map.get(f"metadata:analyst:{index}", ())
            if not analyst_citations:
                continue
            analysts.append(
                BriefAnalyst(
                    analyst.name,
                    analyst.role,
                    analyst.email,
                    analyst_citations,
                )
            )
        primary = next(iter(citation_map.get("metadata:title", ())), None)
        publication_date_citations = citation_map.get("metadata:publication_date", ())
        return ResearchBrief(
            ticker=ticker,
            broker=broker,
            report_date=report_date,
            internal_publication_date=(
                metadata.internal_publication_date if publication_date_citations else None
            ),
            internal_publication_date_citations=publication_date_citations,
            report_title=metadata.title if primary else None,
            takeaway=takeaway,
            takeaway_citations=takeaway_citations,
            revisions_status=revisions.status,
            revision_rows=rows,
            omitted_revision_rows=omitted,
            rationale_clarity=clarity,
            rationale_paragraphs=paragraphs,
            estimate_visualizations=tuple(visualizations),
            first_read_items=tuple(first_read),
            source_identifier=_safe_source_identifier(revisions.source_filename),
            analysts=tuple(analysts),
            primary_citation=primary,
            warnings=tuple(dict.fromkeys(warnings)),
            requires_analyst_escalation=(
                escalation.requires_analyst_escalation if escalation is not None else False
            ),
            escalation_reason=escalation.escalation_reason if escalation is not None else None,
            analyst=escalation.analyst if escalation is not None else (),
            email_draft=escalation.email_draft if escalation is not None else None,
        )


def _display_date(value: str) -> str:
    digits = value.replace("-", "")
    try:
        return datetime.strptime(digits, "%Y%m%d").strftime("%d %b %Y")
    except ValueError:
        return value


def render_markdown(brief: ResearchBrief) -> str:
    header = f"**{brief.ticker} — {brief.broker} — {_display_date(brief.report_date)}**"
    normalized_report_date = brief.report_date.replace("-", "")
    normalized_internal_date = (brief.internal_publication_date or "").replace("-", "")
    if normalized_internal_date and normalized_internal_date != normalized_report_date:
        header += (
            f" (published {_display_date(brief.internal_publication_date)})"
            + _citation_markdown(brief.internal_publication_date_citations)
        )
    lines = [header, ""]
    title = brief.report_title or "Report title unavailable"
    title_citation = _citation_markdown((brief.primary_citation,) if brief.primary_citation else ())
    lines.extend((f"# {title}{title_citation}", ""))
    takeaway = brief.takeaway or "A supported one-line takeaway is not available."
    lines.extend((takeaway.rstrip(".") + "." + _citation_markdown(brief.takeaway_citations), ""))

    if brief.revision_rows:
        lines.extend(("## What changed", ""))
        lines.append("| Metric | Period | Old | New | Revision | Consensus | Old vs cons. | New vs cons. |")
        lines.append("| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |")
        for row in brief.revision_rows:
            qualifier = f" ({', '.join(row.metric_qualifiers)})" if row.metric_qualifiers else ""
            metric = _metric_label(row.metric) + qualifier + _citation_markdown(row.citations)
            lines.append(
                "| " + " | ".join(
                    (
                        metric,
                        row.fiscal_period or MISSING,
                        _format_value(row.old_value, row.unit),
                        _format_value(row.new_value, row.unit),
                        _format_change(row.revision_percentage, row.revision_kind),
                        _format_value(row.consensus_value, row.unit),
                        _format_change(row.old_vs_consensus, "percentage"),
                        _format_change(row.new_vs_consensus, "percentage"),
                    )
                ) + " |"
            )
        if brief.omitted_revision_rows:
            lines.extend(("", f"_{brief.omitted_revision_rows} additional validated revision rows are omitted from the concise view; JSON retains the brief's selected-row count and omission warning._"))
        row_warnings = [
            f"{_metric_label(row.metric)} {row.fiscal_period or 'current'}: "
            + ", ".join(warning.replace("_", " ") for warning in row.warnings)
            for row in brief.revision_rows
            if row.warnings
        ]
        if row_warnings:
            lines.extend(("", "Material arithmetic warnings:"))
            lines.extend(f"- {warning}" for warning in row_warnings)
        lines.append("")

    if brief.rationale_paragraphs:
        lines.extend(("## Why it changed, and why now", ""))
        for paragraph in brief.rationale_paragraphs[:2]:
            lines.extend((paragraph, ""))

    if brief.estimate_visualizations:
        lines.extend(("## Estimate picture", ""))
        for visual in brief.estimate_visualizations:
            lines.extend(("```text", visual.plain_text, "```", ""))

    if brief.first_read_items:
        lines.extend(("## Important first-read items", ""))
        lines.extend(f"- {item}" for item in brief.first_read_items)
        lines.append("")

    lines.extend(("## Source and analyst information", ""))
    source = brief.source_identifier + _citation_markdown((brief.primary_citation,) if brief.primary_citation else (), "report")
    lines.append(f"- Source: {source}")
    lines.append(f"- Report title: {title}{title_citation}")
    if brief.analysts:
        for analyst in brief.analysts:
            details = ", ".join(item for item in (analyst.role, analyst.email) if item)
            suffix = f" — {details}" if details else ""
            lines.append(f"- Analyst: {analyst.name}{suffix}{_citation_markdown(analyst.citations)}")
    else:
        lines.append("- Analyst: not identified from validated report evidence")
    lines.append("")

    if brief.warnings:
        lines.extend(("## Warnings / missing information", ""))
        lines.extend(f"- {warning.replace('_', ' ')}" for warning in brief.warnings)
        lines.append("")

    if brief.requires_analyst_escalation and brief.email_draft is not None:
        lines.extend(("## Analyst clarification draft", ""))
        lines.append(
            "The report contains a material revision whose rationale is unclear. "
            "You may wish to contact the covering analyst; a review-only draft follows."
        )
        lines.extend(("", render_email_draft_markdown(brief.email_draft)))
    return "\n".join(lines).rstrip() + "\n"


def render_text(brief: ResearchBrief) -> str:
    markdown = render_markdown(brief)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1 <\2>", markdown)
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.M)
    text = text.replace("**", "").replace("```text\n", "").replace("```\n", "")
    return text
