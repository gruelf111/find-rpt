from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field, replace
from typing import Iterable

from .metadata import AnalystMetadata, ReportMetadata
from .rationale import Driver, RationaleResult
from .revisions import EstimateRevision, RevisionResult


DEFAULT_RELATIVE_MATERIALITY_PCT = 3.0
DEFAULT_PERCENTAGE_POINT_MATERIALITY = 1.0
EXPLICIT_MATERIALITY_FLAGS = {
    "explicitly_marked_material",
    "report_explicitly_marks_revision_material",
}
RATING_METRICS = {"rating", "rating_change", "recommendation"}
TARGET_PRICE_METRICS = {"target_price"}


@dataclass(frozen=True)
class EscalationPolicy:
    relative_materiality_pct: float = DEFAULT_RELATIVE_MATERIALITY_PCT
    percentage_point_materiality: float = DEFAULT_PERCENTAGE_POINT_MATERIALITY
    escalate_partial: bool = False

    def __post_init__(self) -> None:
        if self.relative_materiality_pct <= 0 or self.percentage_point_materiality <= 0:
            raise ValueError("materiality thresholds must be positive")


@dataclass(frozen=True)
class MaterialityAssessment:
    is_material: bool
    reason: str
    comparable_change: float | None
    change_kind: str | None
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class DraftAnalyst:
    name: str
    designation: str | None
    role: str | None
    email: str | None
    phone: str | None
    evidence_block_ids: tuple[str, ...]
    selection_status: str


@dataclass(frozen=True)
class EmailDraft:
    to: str
    analyst_names: tuple[str, ...]
    subject: str
    greeting: str
    body: str
    questions: tuple[str, ...]
    signoff_placeholder: str
    unresolved_fields: tuple[str, ...]
    warnings: tuple[str, ...]
    source_report_id: str
    escalation_reason: str
    sent: bool = field(default=False, init=False)


@dataclass(frozen=True)
class EscalationResult:
    requires_analyst_escalation: bool
    escalation_reason: str | None
    analyst: tuple[DraftAnalyst, ...]
    email_draft: EmailDraft | None
    warnings: tuple[str, ...]
    source_report_id: str
    sent: bool = field(default=False, init=False)

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)


def _first_available(*values: float | None) -> float | None:
    return next((value for value in values if value is not None), None)


def assess_materiality(
    revision: EstimateRevision,
    *,
    policy: EscalationPolicy | None = None,
) -> MaterialityAssessment:
    policy = policy or EscalationPolicy()
    flags = set(getattr(revision, "materiality_indicators", ()))
    if flags & EXPLICIT_MATERIALITY_FLAGS:
        return MaterialityAssessment(True, "explicitly_marked_material", None, "explicit")

    if revision.metric in RATING_METRICS:
        changed = revision.direction in {"increase", "decrease"} or (
            revision.old_value is not None
            and revision.new_value is not None
            and revision.old_value != revision.new_value
        )
        return MaterialityAssessment(changed, "rating_change" if changed else "rating_unchanged", None, "rating")

    if revision.metric in TARGET_PRICE_METRICS:
        changed = revision.direction in {"increase", "decrease"} or (
            revision.old_value is not None
            and revision.new_value is not None
            and revision.old_value != revision.new_value
        )
        return MaterialityAssessment(
            changed,
            "target_price_change" if changed else "target_price_unchanged",
            _first_available(revision.stated_revision_pct, revision.calculated_revision_pct),
            "percentage",
        )

    pp_change = _first_available(revision.stated_change_pp, revision.calculated_change_pp)
    if pp_change is not None:
        return MaterialityAssessment(
            abs(pp_change) >= policy.percentage_point_materiality,
            "percentage_point_threshold",
            pp_change,
            "percentage_points",
        )

    if revision.old_value == 0:
        return MaterialityAssessment(
            False,
            "zero_denominator_materiality_unresolved",
            None,
            None,
            ("zero_denominator_not_compared_to_relative_threshold",),
        )

    relative_change = _first_available(
        revision.stated_revision_pct,
        revision.calculated_revision_pct,
    )
    if relative_change is not None:
        reason = (
            "relative_threshold_negative_base"
            if revision.old_value is not None and revision.old_value < 0
            else "relative_percentage_threshold"
        )
        return MaterialityAssessment(
            abs(relative_change) >= policy.relative_materiality_pct,
            reason,
            relative_change,
            "percentage",
        )

    return MaterialityAssessment(
        False,
        "non_numeric_materiality_unresolved",
        None,
        None,
        ("non_numeric_revision_requires_explicit_materiality",),
    )


def _driver_answers_revision(driver: Driver, revision: EstimateRevision) -> bool:
    if driver.causal_link != "explicit":
        return False
    if revision.metric not in driver.impacted_metrics:
        return False
    if revision.fiscal_period is None:
        return revision.metric in TARGET_PRICE_METRICS or not driver.fiscal_periods
    return revision.fiscal_period in driver.fiscal_periods


def _unexplained_material_revisions(
    revisions: RevisionResult,
    rationale: RationaleResult,
    policy: EscalationPolicy,
) -> tuple[tuple[int, EstimateRevision, MaterialityAssessment], ...]:
    extraction = rationale.extraction
    if extraction is None:
        return ()
    unresolved: list[tuple[int, EstimateRevision, MaterialityAssessment]] = []
    for index, revision in enumerate(revisions.revisions, 1):
        assessment = assess_materiality(revision, policy=policy)
        if not assessment.is_material:
            continue
        if any(_driver_answers_revision(driver, revision) for driver in extraction.drivers):
            continue
        unresolved.append((index, revision, assessment))
    return tuple(
        sorted(
            unresolved,
            key=lambda item: (
                item[1].metric,
                item[1].metric_qualifiers,
                item[1].fiscal_period or "",
                item[0],
            ),
        )
    )


def _display_metric(revision: EstimateRevision) -> str:
    label = {
        "eps": "EPS",
        "ebit": "EBIT",
        "ebitda": "EBITDA",
        "dps": "DPS",
        "target_price": "target price",
        "rating": "rating",
        "rating_change": "rating",
    }.get(revision.metric, revision.metric.replace("_", " "))
    if revision.metric_qualifiers:
        return f"{' '.join(revision.metric_qualifiers)} {label}"
    return label


def _format_number(value: float | None) -> str:
    if value is None:
        return "not supplied"
    return f"{value:,.4f}".rstrip("0").rstrip(".")


def _format_observation(value: float | None, unit: str | None) -> str:
    rendered = _format_number(value)
    if value is None:
        return rendered
    if unit == "%":
        return f"{rendered}%"
    if unit == "percentage_points":
        return f"{rendered} percentage points"
    if unit == "basis_points":
        return f"{rendered} basis points"
    return f"{rendered} {unit}" if unit else rendered


def _assumption_choices(metric: str) -> str:
    if metric in {"revenue", "reinsurance_revenue_gross", "reinsurance_revenue_net"}:
        return "volume, price, mix, foreign exchange, or another assumption"
    if "margin" in metric or metric in {"ebit", "ebitda", "operating_profit", "net_income"}:
        return "volume, price, mix, margin, costs, foreign exchange, or another assumption"
    if metric == "eps":
        return "operating performance, margin, tax, interest, share count, accounting, or another assumption"
    if metric in TARGET_PRICE_METRICS:
        return "earnings, valuation multiple, discount rate, or another valuation assumption"
    if metric in RATING_METRICS:
        return "earnings, valuation, catalysts, risks, or another part of the investment case"
    return "the operational, financial, or modelling assumptions"


def _known_incomplete_driver(
    revision: EstimateRevision,
    drivers: Iterable[Driver],
) -> str | None:
    candidates = [driver.driver.rstrip(".") for driver in drivers if revision.metric in driver.impacted_metrics]
    return candidates[0] if candidates else None


def _question_for_revision(
    revision: EstimateRevision,
    assessment: MaterialityAssessment,
    *,
    drivers: tuple[Driver, ...],
    report_context: str,
    management_contact: str,
) -> str:
    metric = _display_metric(revision)
    period = revision.fiscal_period or "the current estimate"
    old_new = ""
    if revision.old_value is not None or revision.new_value is not None:
        old_new = (
            f" from {_format_observation(revision.old_value, revision.unit)}"
            f" to {_format_observation(revision.new_value, revision.unit)}"
        )
    if assessment.change_kind == "percentage_points" and assessment.comparable_change is not None:
        change = f" ({assessment.comparable_change:+g} percentage points)"
    elif assessment.comparable_change is not None:
        change = f" ({assessment.comparable_change:+g}%)"
    else:
        change = ""
    known = _known_incomplete_driver(revision, drivers)
    known_clause = f" The report mentions {known}, but the remaining bridge is unclear." if known else ""
    question = (
        f"For {metric} in {period}{old_new}{change}, what changed in "
        f"{_assumption_choices(revision.metric)}, and is the effect temporary or structural?"
        f"{known_clause}"
    )
    if revision.consensus_value is not None:
        relation = None
        if revision.new_vs_consensus_pct is not None:
            relation = "above" if revision.new_vs_consensus_pct > 0 else "below" if revision.new_vs_consensus_pct < 0 else "in line with"
        if relation:
            question += (
                f" What supports the revised estimate remaining {relation} consensus"
                f" ({_format_observation(revision.consensus_value, revision.unit)})?"
            )
    context_clause = {
        "results_preview": " Why make this change ahead of results?",
        "results_review": " Which result or management comment prompted the change now?",
        "event_reaction": " Which part of the recent event prompted the change now?",
        "management_meeting": " Did the management interaction influence the change?",
        "roadshow": " Did the roadshow discussion influence the change?",
    }.get(report_context)
    if context_clause:
        question += context_clause
    elif management_contact == "true":
        question += " Did management commentary influence the change now?"
    return " ".join(question.split())


def _deduplicate_questions(values: Iterable[str]) -> tuple[str, ...]:
    unique: dict[str, str] = {}
    for value in values:
        key = re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()
        unique.setdefault(key, value)
    return tuple(unique.values())


def _merge_question_groups(
    unresolved: tuple[tuple[int, EstimateRevision, MaterialityAssessment], ...],
) -> tuple[tuple[EstimateRevision, MaterialityAssessment], ...]:
    grouped: dict[tuple, list[tuple[EstimateRevision, MaterialityAssessment]]] = {}
    for _, revision, assessment in unresolved:
        grouped.setdefault(
            (revision.metric, revision.metric_qualifiers, revision.fiscal_period), []
        ).append((revision, assessment))
    merged: list[tuple[EstimateRevision, MaterialityAssessment]] = []
    for group in grouped.values():
        revision, assessment = group[0]
        observations = {
            (item.old_value, item.new_value, item.unit) for item, _ in group
        }
        consensus = {item.consensus_value for item, _ in group}
        if len(observations) > 1:
            revision = replace(
                revision,
                old_value=None,
                new_value=None,
                stated_revision_pct=None,
                calculated_revision_pct=None,
                stated_change_pp=None,
                calculated_change_pp=None,
            )
            assessment = replace(
                assessment, comparable_change=None, change_kind=None
            )
        if len(consensus) > 1:
            revision = replace(
                revision,
                consensus_value=None,
                old_vs_consensus_pct=None,
                new_vs_consensus_pct=None,
            )
        merged.append((revision, assessment))
    return tuple(merged)


def _selected_analysts(metadata: ReportMetadata) -> tuple[DraftAnalyst, ...]:
    analysts = tuple(metadata.analysts)
    preferred = tuple(
        analyst
        for analyst in analysts
        if getattr(analyst, "selection_status", "relevant") in {"covering", "lead"}
    )
    selected = preferred or analysts
    return tuple(
        DraftAnalyst(
            name=analyst.name,
            designation=getattr(analyst, "designation", None),
            role=analyst.role,
            email=analyst.email,
            phone=getattr(analyst, "phone", None),
            evidence_block_ids=analyst.evidence_block_ids,
            selection_status=getattr(analyst, "selection_status", "relevant"),
        )
        for analyst in selected
    )


def _display_name(analyst: DraftAnalyst) -> str:
    return f"{analyst.name}, {analyst.designation}" if analyst.designation else analyst.name


def _compose_draft(
    *,
    ticker: str,
    report_date: str,
    report_title: str | None,
    report_id: str,
    reason: str,
    analysts: tuple[DraftAnalyst, ...],
    questions: tuple[str, ...],
) -> EmailDraft:
    names = tuple(_display_name(analyst) for analyst in analysts)
    addresses = tuple(analyst.email for analyst in analysts if analyst.email)
    missing_addresses = len(addresses) != len(analysts) or not analysts
    to_parts = list(addresses)
    if missing_addresses:
        to_parts.append("[TODO: address]")
    to = "; ".join(dict.fromkeys(to_parts)) if to_parts else "[TODO: address]"
    if names:
        greeting_names = names[0] if len(names) == 1 else ", ".join(names[:-1]) + f" and {names[-1]}"
        greeting = f"Dear {greeting_names},"
    else:
        greeting = "Hello,"
    title = report_title or "the report"
    introduction = (
        f"I am reviewing {title} dated {report_date} and the revised estimates for {ticker}. "
        "Could you please clarify the following points?"
    )
    question_block = "\n".join(f"{index}. {question}" for index, question in enumerate(questions, 1))
    signoff = "Best,\n[Your name]"
    body = f"{greeting}\n\n{introduction}\n\n{question_block}\n\n{signoff}"
    unresolved: list[str] = []
    warnings: list[str] = []
    if missing_addresses:
        unresolved.append("recipient_address")
        warnings.append("one_or_more_analyst_email_addresses_not_found")
    if not names:
        unresolved.append("analyst_name")
        warnings.append("analyst_identity_not_found_neutral_greeting_used")
    return EmailDraft(
        to=to,
        analyst_names=names,
        subject=f"Question on revised estimates for {ticker}",
        greeting=greeting,
        body=body,
        questions=questions,
        signoff_placeholder=signoff,
        unresolved_fields=tuple(unresolved),
        warnings=tuple(warnings),
        source_report_id=report_id,
        escalation_reason=reason,
    )


class AmbiguityEscalationBuilder:
    """Build a deterministic review-only analyst escalation from structured data."""

    def __init__(self, policy: EscalationPolicy | None = None):
        self.policy = policy or EscalationPolicy()

    def build(
        self,
        *,
        ticker: str,
        report_date: str,
        metadata: ReportMetadata,
        revisions: RevisionResult,
        rationale: RationaleResult | None,
    ) -> EscalationResult:
        if metadata.document_id is not None and metadata.document_id != revisions.document_id:
            raise ValueError("metadata and revisions belong to different reports")
        if rationale is not None and rationale.document_id != revisions.document_id:
            raise ValueError("rationale and revisions belong to different reports")
        if revisions.status != "revisions_found" or not revisions.revisions:
            return EscalationResult(False, None, (), None, (), revisions.document_id)
        if rationale is None or rationale.extraction is None:
            return EscalationResult(
                False,
                None,
                (),
                None,
                ("rationale_clarity_unavailable",),
                revisions.document_id,
            )
        clarity = rationale.extraction.rationale_clarity
        if clarity == "clear":
            return EscalationResult(False, None, (), None, (), revisions.document_id)
        if clarity == "partial" and not self.policy.escalate_partial:
            return EscalationResult(
                False,
                None,
                (),
                None,
                ("partial_rationale_escalation_disabled",),
                revisions.document_id,
            )
        unresolved = _unexplained_material_revisions(revisions, rationale, self.policy)
        if not unresolved:
            return EscalationResult(False, None, (), None, (), revisions.document_id)
        reason = (
            "rationale_unclear_for_material_revision"
            if clarity == "unclear"
            else "partial_rationale_leaves_material_revision_unexplained"
        )
        extraction = rationale.extraction
        questions = _deduplicate_questions(
            _question_for_revision(
                revision,
                assessment,
                drivers=extraction.drivers,
                report_context=extraction.report_context,
                management_contact=extraction.management_contact,
            )
            for revision, assessment in _merge_question_groups(unresolved)
        )
        analysts = _selected_analysts(metadata)
        draft = _compose_draft(
            ticker=ticker,
            report_date=report_date,
            report_title=metadata.title,
            report_id=revisions.document_id,
            reason=reason,
            analysts=analysts,
            questions=questions,
        )
        warnings = list(draft.warnings)
        for _, _, assessment in unresolved:
            warnings.extend(assessment.warnings)
        return EscalationResult(
            True,
            reason,
            analysts,
            draft,
            tuple(dict.fromkeys(warnings)),
            revisions.document_id,
        )


def render_email_draft_markdown(draft: EmailDraft) -> str:
    lines = [
        f"**To:** {draft.to}",
        f"**Subject:** {draft.subject}",
        "",
        draft.body,
        "",
        "_This draft has not been sent. Review and edit it before taking any separate action outside find-rpt._",
    ]
    return "\n".join(lines)


def render_email_draft_text(draft: EmailDraft) -> str:
    return (
        f"To: {draft.to}\nSubject: {draft.subject}\n\n{draft.body}\n\n"
        "This draft has not been sent. Review and edit it before taking any separate action outside find-rpt."
    )
