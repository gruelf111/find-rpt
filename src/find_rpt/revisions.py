from __future__ import annotations

import json
import math
import re
import unicodedata
from dataclasses import asdict, dataclass, replace
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Iterable

from .evidence import EvidenceBlock, EvidenceDocument, EvidencePage, EvidenceWord


ROUNDING_TOLERANCE_PCT = 0.25
ROW_Y_TOLERANCE = 2.5
CURRENCY_CODES = {
    "AUD", "CAD", "CHF", "CNY", "DKK", "EUR", "GBP", "HKD", "JPY", "NOK",
    "SEK", "USD",
}
PER_SHARE_METRICS = {"eps", "dps", "book_value_per_share", "tangible_equity_per_share"}

REVISION_SIGNAL_RE = re.compile(
    r"\b(?:old|new|previous|prev\.?|current|revis(?:e|ed|ion|ions)|change[ds]?|"
    r"rais(?:e|ed|ing)|lower(?:ed|ing)?|cut(?:s|ting)?|increase[ds]?|decrease[ds]?)\b",
    re.IGNORECASE,
)
CONSENSUS_RE = re.compile(r"\bconsensus\b", re.IGNORECASE)
DISCLOSURE_RE = re.compile(
    r"\b(?:analyst certification|important disclosures?|explanation of .{0,30} ratings|"
    r"valuation methodology|other companies mentioned in this report|"
    r"risks which may impede the achievement of our price target|"
    r"under no circumstances is to be construed as an offer|"
    r"intended solely for accredited|past performance is not a guide)\b",
    re.IGNORECASE,
)
PERIOD_RE = re.compile(
    r"\b(?P<month>0?[1-9]|1[0-2])/(?P<myear>\d{2})(?P<mestimate>[Ee])?\b|"
    r"\b(?P<quarter>[1-4]Q|Q[1-4])\s*(?P<qyear>20\d{2}|\d{2})(?P<qestimate>[Ee])?\b|"
    r"\b(?P<half>[12]H|H[12])\s*(?P<hyear>20\d{2}|\d{2})(?P<hestimate>[Ee])?\b|"
    r"(?<![\d/.,])\b(?:(?P<prefix>FY|CY)\s*)?(?P<year>20\d{2}|\d{2})(?P<estimate>[Ee])?\b(?![\d/%.,])",
    re.IGNORECASE,
)

METRIC_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("target_price", re.compile(r"\b(?:target price|price target|price obj\.?|price objective|fair value|TP|PO)\b", re.I)),
    ("ebitda_margin", re.compile(r"\bEBITDA\s+margin\b", re.I)),
    ("ebit_margin", re.compile(r"\bEBIT\s+margin\b", re.I)),
    ("operating_margin", re.compile(r"\boperating\s+margin\b", re.I)),
    ("gross_margin", re.compile(r"\bgross\s+margin\b", re.I)),
    ("net_margin", re.compile(r"\bnet\s+margin\b", re.I)),
    ("eps", re.compile(r"\b(?:earnings per share|EPS)\b", re.I)),
    ("reinsurance_revenue_gross", re.compile(r"\breinsurance revenue\s*\(gross\)", re.I)),
    ("reinsurance_revenue_net", re.compile(r"\breinsurance revenue\s*\(net\)", re.I)),
    ("net_reinsurance_service_result", re.compile(r"\bnet reinsurance service result\b", re.I)),
    ("reinsurance_service_result", re.compile(r"\breinsurance service result\b", re.I)),
    ("revenue", re.compile(r"\b(?:revenue|revenues|sales|turnover)\b", re.I)),
    ("ebitda", re.compile(r"\bEBITDA\b", re.I)),
    ("ebit", re.compile(r"\bEBIT\b", re.I)),
    ("operating_profit", re.compile(r"\b(?:operating profit|operating income)\b", re.I)),
    ("pretax_profit", re.compile(r"\b(?:pre-tax|pretax|profit before tax|PBT)\b", re.I)),
    ("net_income", re.compile(r"\b(?:net income|net profit|net earnings)\b", re.I)),
    ("tax_rate", re.compile(r"\b(?:tax rate|effective tax)\b", re.I)),
    ("tax", re.compile(r"\b(?:tax expense|tax charge|taxation)\b", re.I)),
    ("net_interest_income", re.compile(r"\b(?:net interest income|NII)\b", re.I)),
    ("net_fee_income", re.compile(r"\bnet fee income\b", re.I)),
    ("trading_income", re.compile(r"\btrading income\b", re.I)),
    ("insurance_income", re.compile(r"\binsurance income\b|^insurance$", re.I)),
    ("other_income", re.compile(r"\bother income\b", re.I)),
    ("total_income", re.compile(r"\btotal income\b", re.I)),
    ("investment_income", re.compile(r"\b(?:net investment income|investment income)\b", re.I)),
    ("interest_expense", re.compile(r"\b(?:interest expense|interest cost)\b", re.I)),
    ("labour_costs", re.compile(r"\b(?:labour|labor) costs?\b", re.I)),
    ("operating_expenses", re.compile(r"\b(?:other )?operating expenses?\b", re.I)),
    ("depreciation", re.compile(r"\bdepreciation\b", re.I)),
    ("total_cost_of_risk", re.compile(r"\btotal cost of risk\b", re.I)),
    ("total_costs", re.compile(r"\btotal costs?\b", re.I)),
    ("loan_loss_provisions", re.compile(r"\bloan loss provisions?\b", re.I)),
    ("risk_provisions", re.compile(r"\brisk provisions?\b", re.I)),
    ("cost_of_risk", re.compile(r"\bcost of risk\b", re.I)),
    ("extraordinary_items", re.compile(r"\bextraordinary(?: interest)? items?\b", re.I)),
    ("book_value_per_share", re.compile(r"\bBV\s*(?:per share|ps)\b", re.I)),
    ("tangible_equity_per_share", re.compile(r"\bTE\s*(?:per share|ps)\b", re.I)),
    ("tangible_return_on_equity", re.compile(r"\b(?:tangible return on equity|tangible ROE)\b", re.I)),
    ("return_on_equity", re.compile(r"\b(?:return on equity|ROE)\b", re.I)),
    ("loans", re.compile(r"^loans?$", re.I)),
    ("customer_deposits", re.compile(r"\bdue to customers?\b|\bcustomer deposits?\b", re.I)),
    ("cet1_ratio", re.compile(r"\bCET1 ratio\b", re.I)),
    ("cost_income_ratio", re.compile(r"\bcost income(?: ratio)?\b", re.I)),
    ("free_cash_flow", re.compile(r"\b(?:free cash flow|FCF)\b", re.I)),
    ("capex", re.compile(r"\b(?:capital expenditure|capex)\b", re.I)),
    ("dps", re.compile(r"\b(?:dividend per share|DPS)\b", re.I)),
    ("combined_ratio", re.compile(r"\b(?:combined ratio|COR)\b", re.I)),
    ("new_business_contractual_service_margin", re.compile(r"\bnew business\s+(?:contractual service margin|CSM)\b", re.I)),
    ("contractual_service_margin", re.compile(r"\b(?:contractual service margin|CSM)\b", re.I)),
    ("shareholders_equity", re.compile(r"\bshareholders['’]?\s+equity\b", re.I)),
    ("solvency_ratio", re.compile(r"\b(?:solvency\s*(?:II|2)?\s*ratio|solvency\s*(?:II|2))\b", re.I)),
)

QUALIFIER_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("adjusted", re.compile(r"\b(?:adjusted|adj)\b", re.I)),
    ("diluted", re.compile(r"\bdiluted\b", re.I)),
    ("reported", re.compile(r"\b(?:reported|rep)\b", re.I)),
    ("restated", re.compile(r"\brestated\b", re.I)),
    ("stated", re.compile(r"\bstated\b", re.I)),
    ("ordinary", re.compile(r"\b(?:ordinary|ord)\b", re.I)),
    ("basic", re.compile(r"\bbasic\b", re.I)),
    ("organic", re.compile(r"\borganic\b", re.I)),
    ("underlying", re.compile(r"\bunderlying\b", re.I)),
    ("recurring", re.compile(r"\brecurring\b", re.I)),
    ("normalized", re.compile(r"\b(?:normalised|normalized)\b", re.I)),
    ("clean", re.compile(r"\bclean\b", re.I)),
)

NULL_STATE_RE = re.compile(r"^(?:n\.?a\.?|n/?m|n\.?m\.?|ns|not meaningful|-)$", re.I)
NUMBER_TOKEN_RE = re.compile(
    r"(?<![A-Za-z0-9])\(?\s*(?:[A-Z]{3}\s*|[€$£¥]\s*)?"
    r"[-+−]?\d(?:[\d.,]*\d)?"
    r"\s*(?:%|bps?|bp|ppts?|pts?|pp|bn|mn|m|b|k)?(?:\s*/\s*share)?\)?(?![A-Za-z0-9])",
    re.I,
)


@dataclass(frozen=True)
class RevisionEvidence:
    page_number: int
    block_ids: tuple[str, ...]


@dataclass(frozen=True)
class EstimateRevision:
    metric: str
    metric_qualifiers: tuple[str, ...]
    fiscal_period: str | None
    period_basis: str | None
    old_value: float | None
    new_value: float | None
    unit: str | None
    stated_revision_pct: float | None
    calculated_revision_pct: float | None
    stated_change_pp: float | None
    calculated_change_pp: float | None
    consensus_value: float | None
    old_vs_consensus_pct: float | None
    new_vs_consensus_pct: float | None
    direction: str
    evidence: tuple[RevisionEvidence, ...]
    extraction_method: str
    confidence: str
    warnings: tuple[str, ...]
    materiality_indicators: tuple[str, ...] = ()


@dataclass(frozen=True)
class RevisionResult:
    status: str
    document_id: str
    source_filename: str
    candidate_pages: tuple[int, ...]
    candidate_block_ids: tuple[str, ...]
    revisions: tuple[EstimateRevision, ...]
    warnings: tuple[str, ...]
    rounding_tolerance_pct: float = ROUNDING_TOLERANCE_PCT

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)


@dataclass(frozen=True)
class ParsedValue:
    value: float | None
    unit: str | None
    state: str | None = None


@dataclass(frozen=True)
class _PageLine:
    y: float
    words: tuple[tuple[EvidenceWord, str], ...]

    @property
    def text(self) -> str:
        return " ".join(word.text for word, _ in self.words)

    @property
    def block_ids(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(block_id for _, block_id in self.words))


@dataclass(frozen=True)
class _ConsensusObservation:
    page_number: int
    metric: str
    qualifiers: tuple[str, ...]
    period: str
    value: ParsedValue
    block_ids: tuple[str, ...]


def _round(value: Decimal | float) -> float:
    decimal_value = value if isinstance(value, Decimal) else Decimal(str(value))
    return float(decimal_value.quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP))


def calculate_revision_pct(old_value: float, new_value: float) -> tuple[float | None, str | None]:
    """Return relative change using abs(old) as the denominator.

    The absolute denominator makes loss narrowing/widening direction intuitive. A zero old
    value has no meaningful relative percentage and is returned explicitly as a warning.
    """
    if not math.isfinite(old_value) or not math.isfinite(new_value):
        return None, "non_finite_value"
    if old_value == 0:
        return None, "zero_old_value_no_relative_revision"
    result = (Decimal(str(new_value)) - Decimal(str(old_value))) / abs(Decimal(str(old_value))) * 100
    return _round(result), None


def calculate_consensus_spread(value: float, consensus: float) -> tuple[float | None, str | None]:
    if not math.isfinite(value) or not math.isfinite(consensus):
        return None, "non_finite_consensus_value"
    if consensus == 0:
        return None, "zero_consensus_no_relative_spread"
    result = (Decimal(str(value)) - Decimal(str(consensus))) / abs(Decimal(str(consensus))) * 100
    return _round(result), None


def normalize_metric(text: str) -> tuple[str | None, tuple[str, ...]]:
    normalized = unicodedata.normalize("NFKC", text)
    for metric, pattern in METRIC_PATTERNS:
        if pattern.search(normalized):
            qualifiers = tuple(name for name, qualifier in QUALIFIER_PATTERNS if qualifier.search(normalized))
            return metric, qualifiers
    return None, ()


def _nearest_metric(text: str, position: int) -> tuple[str | None, tuple[str, ...]]:
    matches: list[tuple[int, str, re.Match[str]]] = []
    for metric, pattern in METRIC_PATTERNS:
        matches.extend(
            (abs(found.start() - position), metric, found)
            for found in pattern.finditer(text)
        )
    if not matches:
        return None, ()
    _, metric, found = min(matches, key=lambda item: (item[0], item[2].start()))
    qualifier_context = text[max(0, found.start() - 50) : found.end() + 30]
    qualifiers = tuple(
        name for name, pattern in QUALIFIER_PATTERNS if pattern.search(qualifier_context)
    )
    return metric, qualifiers


def normalize_fiscal_period(text: str) -> tuple[str | None, str | None]:
    match = PERIOD_RE.search(unicodedata.normalize("NFKC", text))
    if not match:
        return None, None

    def year(value: str) -> str:
        return f"20{value}" if len(value) == 2 else value

    if match.group("quarter"):
        quarter = match.group("quarter").upper()
        quarter = f"Q{quarter[0]}" if quarter.endswith("Q") else quarter
        suffix = "E" if match.group("qestimate") else ""
        return f"{quarter} {year(match.group('qyear'))}{suffix}", "fiscal"
    if match.group("half"):
        half = match.group("half").upper()
        half = f"H{half[0]}" if half.endswith("H") else half
        suffix = "E" if match.group("hestimate") else ""
        return f"{half} {year(match.group('hyear'))}{suffix}", "fiscal"
    if match.group("month"):
        suffix = "E" if match.group("mestimate") else ""
        return f"FY{int(match.group('month')):02d}/{year(match.group('myear'))}{suffix}", "fiscal"
    prefix = (match.group("prefix") or "").upper()
    suffix = "E" if match.group("estimate") else ""
    period = f"{prefix}{year(match.group('year'))}{suffix}"
    basis = "fiscal" if prefix == "FY" else "calendar" if prefix == "CY" else "unspecified"
    return period, basis


def normalize_unit(text: str, *, metric: str | None = None) -> str | None:
    euro_shorthand = re.search(r"\bEu\s*(mn|m|bn|b)?\b", text, re.I)
    if euro_shorthand:
        suffix = (euro_shorthand.group(1) or "").casefold()
        scale = "bn" if suffix in {"bn", "b"} else "m" if suffix in {"mn", "m"} else ""
        return f"EUR{scale}/share" if metric in PER_SHARE_METRICS else f"EUR{scale}"
    compact = unicodedata.normalize("NFKC", text).replace(" ", "")
    lower = compact.casefold()
    if re.search(r"(?:ppts?|pts?|pp)$", lower):
        return "percentage_points"
    if lower.endswith("bp") or lower.endswith("bps"):
        return "basis_points"
    if "%" in compact:
        return "%"

    currency = None
    for pattern, code in ((r"€|EUR", "EUR"), (r"\$|USD", "USD"), (r"£|GBP", "GBP"), (r"¥|JPY", "JPY")):
        if re.search(pattern, compact, re.I):
            currency = code
            break
    if currency is None:
        code = re.search(r"\b([A-Z]{3})(?=[-+()\d])", compact)
        currency = code.group(1) if code and code.group(1) in CURRENCY_CODES else None

    scale = None
    if re.search(r"(?:bn|b)(?:/share)?$", lower):
        scale = "bn"
    elif re.search(r"(?:mn|m)(?:/share)?$", lower):
        scale = "m"
    elif re.search(r"k(?:/share)?$", lower):
        scale = "k"
    per_share = "/share" in lower or metric in PER_SHARE_METRICS
    if currency and scale:
        return f"{currency}{scale}/share" if per_share else f"{currency}{scale}"
    if currency:
        return f"{currency}/share" if per_share else currency
    if scale:
        return f"{scale}/share" if per_share else scale
    return "per_share" if per_share else None


def parse_value(text: str, *, metric: str | None = None) -> ParsedValue:
    cleaned = unicodedata.normalize("NFKC", text).strip()
    if NULL_STATE_RE.fullmatch(cleaned):
        return ParsedValue(None, None, cleaned.casefold())
    match = NUMBER_TOKEN_RE.search(cleaned)
    if not match:
        return ParsedValue(None, None)
    token = match.group(0).strip()
    negative_parentheses = "(" in token and ")" in token
    numeric = re.search(r"[-+−]?\d(?:[\d.,]*\d)?", token)
    if not numeric:
        return ParsedValue(None, normalize_unit(token, metric=metric))
    number = numeric.group(0).replace("−", "-")
    if "," in number and "." in number:
        number = number.replace(",", "") if number.rfind(".") > number.rfind(",") else number.replace(".", "").replace(",", ".")
    elif number.count(",") == 1 and len(number.rsplit(",", 1)[1]) <= 2:
        number = number.replace(",", ".")
    else:
        number = number.replace(",", "")
    try:
        value = Decimal(number)
    except InvalidOperation:
        return ParsedValue(None, normalize_unit(token, metric=metric))
    if negative_parentheses and value > 0:
        value = -value
    return ParsedValue(float(value), normalize_unit(token, metric=metric))


def _direction(old: float | None, new: float | None, text: str = "") -> str:
    if old is not None and new is not None:
        return "increase" if new > old else "decrease" if new < old else "unchanged"
    lowered = text.casefold()
    if re.search(r"\b(?:raise|raised|increase|increased|higher)\b", lowered):
        return "increase"
    if re.search(r"\b(?:lower|lowered|cut|decrease|decreased|reduced)\b", lowered):
        return "decrease"
    return "unknown"


def _same_unit(old: ParsedValue, new: ParsedValue) -> tuple[str | None, list[str]]:
    warnings: list[str] = []
    if old.unit and new.unit and old.unit != new.unit:
        warnings.append("old_new_unit_mismatch")
        return None, warnings
    return old.unit or new.unit, warnings


def _finalize_revision(
    *,
    metric: str,
    qualifiers: tuple[str, ...],
    period: str | None,
    period_basis: str | None,
    old: ParsedValue,
    new: ParsedValue,
    stated_pct: float | None,
    stated_pp: float | None,
    consensus: ParsedValue,
    evidence: tuple[RevisionEvidence, ...],
    method: str,
    source_text: str,
    warnings: Iterable[str] = (),
) -> EstimateRevision:
    warning_list = list(warnings)
    unit, unit_warnings = _same_unit(old, new)
    warning_list.extend(unit_warnings)
    if consensus.value is not None and consensus.unit and unit and consensus.unit != unit:
        warning_list.append("consensus_unit_mismatch")
        consensus = ParsedValue(None, consensus.unit)

    calculated_pct = None
    calculated_pp = None
    if old.value is not None and new.value is not None and not unit_warnings:
        if unit == "%":
            calculated_pp = _round(Decimal(str(new.value)) - Decimal(str(old.value)))
        elif unit == "basis_points":
            calculated_pp = _round(
                (Decimal(str(new.value)) - Decimal(str(old.value))) / 100
            )
        calculated_pct, arithmetic_warning = calculate_revision_pct(old.value, new.value)
        if arithmetic_warning:
            warning_list.append(arithmetic_warning)
    if stated_pct is not None and calculated_pct is not None:
        if abs(stated_pct - calculated_pct) > ROUNDING_TOLERANCE_PCT:
            warning_list.append("stated_calculated_revision_mismatch")
    if stated_pp is not None and calculated_pp is not None:
        if abs(stated_pp - calculated_pp) > ROUNDING_TOLERANCE_PCT:
            warning_list.append("stated_calculated_percentage_point_mismatch")

    old_spread = new_spread = None
    if consensus.value is not None:
        if old.value is not None:
            old_spread, spread_warning = calculate_consensus_spread(old.value, consensus.value)
            if spread_warning:
                warning_list.append(f"old_{spread_warning}")
        if new.value is not None:
            new_spread, spread_warning = calculate_consensus_spread(new.value, consensus.value)
            if spread_warning:
                warning_list.append(f"new_{spread_warning}")

    if period is None and metric != "target_price":
        warning_list.append("fiscal_period_unresolved")
    if old.value is None:
        warning_list.append("old_value_unresolved")
    if new.value is None:
        warning_list.append("new_value_unresolved")
    confidence = "high" if old.value is not None and new.value is not None and (period or metric == "target_price") else "medium"
    if old.value is None and new.value is None and stated_pct is None and stated_pp is None:
        confidence = "low"
    return EstimateRevision(
        metric=metric,
        metric_qualifiers=qualifiers,
        fiscal_period=period,
        period_basis=period_basis,
        old_value=old.value,
        new_value=new.value,
        unit=unit or consensus.unit,
        stated_revision_pct=stated_pct,
        calculated_revision_pct=calculated_pct,
        stated_change_pp=stated_pp,
        calculated_change_pp=calculated_pp,
        consensus_value=consensus.value,
        old_vs_consensus_pct=old_spread,
        new_vs_consensus_pct=new_spread,
        direction=_direction(old.value, new.value, source_text),
        evidence=evidence,
        extraction_method=method,
        confidence=confidence,
        warnings=tuple(dict.fromkeys(warning_list)),
    )


def _extract_explicit_change(text: str) -> tuple[float | None, float | None]:
    pp_match = re.search(r"(?:by|change(?:d)?(?:\s+of)?|revision(?:\s+of)?|up|down)\s*(?:c\.?\s*)?([+-]?\d+(?:[.,]\d+)?)\s*(pp|ppts?|bp|bps)\b", text, re.I)
    if pp_match:
        value = float(pp_match.group(1).replace(",", "."))
        if pp_match.group(2).casefold().startswith("bp"):
            value /= 100
        return None, value
    pct_match = re.search(r"(?:by|change(?:d)?(?:\s+of)?|revision(?:\s+of)?|up|down)\s*(?:c\.?\s*)?([+-]?\d+(?:[.,]\d+)?)\s*%", text, re.I)
    return (float(pct_match.group(1).replace(",", ".")), None) if pct_match else (None, None)


def _extract_consensus(text: str, metric: str) -> ParsedValue:
    match = re.search(r"\bconsensus\b(?:\s+(?:of|at|is))?\s*[:=]?\s*(" + NUMBER_TOKEN_RE.pattern + r")", text, re.I)
    return parse_value(match.group(1), metric=metric) if match else ParsedValue(None, None)


def _prose_revisions(page: EvidencePage, candidate_ids: set[str]) -> list[EstimateRevision]:
    revisions: list[EstimateRevision] = []
    patterns = (
        re.compile(r"\bfrom\s+(?P<old>" + NUMBER_TOKEN_RE.pattern + r")\s+(?:to|versus)\s+(?P<new>" + NUMBER_TOKEN_RE.pattern + r")", re.I),
        re.compile(r"\b(?:to|at)\s+(?P<new>" + NUMBER_TOKEN_RE.pattern + r")\s+from\s+(?P<old>" + NUMBER_TOKEN_RE.pattern + r")", re.I),
        re.compile(
            r"\b(?:to|at|of)\s+(?P<new>" + NUMBER_TOKEN_RE.pattern
            + r")\s*\(?\s*(?:vs\.?|versus)\s+(?P<old>" + NUMBER_TOKEN_RE.pattern
            + r")\s*(?:before|previously)?\s*\)?",
            re.I,
        ),
    )
    for block in page.blocks:
        if block.block_id not in candidate_ids:
            continue
        text = " ".join(block.text.split())
        for pattern in patterns:
            for match in pattern.finditer(text):
                context = text[max(0, match.start() - 160) : min(len(text), match.end() + 120)]
                if not REVISION_SIGNAL_RE.search(context):
                    continue
                metric, qualifiers = _nearest_metric(text, match.start())
                if metric is None:
                    continue
                period, basis = (
                    (None, None)
                    if metric == "target_price"
                    else normalize_fiscal_period(context)
                )
                old = parse_value(match.group("old"), metric=metric)
                new = parse_value(match.group("new"), metric=metric)
                stated_pct, stated_pp = _extract_explicit_change(context)
                consensus = _extract_consensus(context, metric)
                revisions.append(
                    _finalize_revision(
                        metric=metric,
                        qualifiers=qualifiers,
                        period=period,
                        period_basis=basis,
                        old=old,
                        new=new,
                        stated_pct=stated_pct,
                        stated_pp=stated_pp,
                        consensus=consensus,
                        evidence=(RevisionEvidence(page.page_number, (block.block_id,)),),
                        method="prose_old_new",
                        source_text=context,
                    )
                )
    return revisions


def _page_lines(page: EvidencePage) -> tuple[_PageLine, ...]:
    positioned: list[tuple[EvidenceWord, str]] = []
    for block in page.blocks:
        positioned.extend((word, block.block_id) for word in block.words)
    positioned.sort(key=lambda item: (item[0].bbox[1], item[0].bbox[0], item[1]))
    groups: list[list[tuple[EvidenceWord, str]]] = []
    y_values: list[float] = []
    for item in positioned:
        y = item[0].bbox[1]
        target = next((index for index, current in enumerate(y_values) if abs(current - y) <= ROW_Y_TOLERANCE), None)
        if target is None:
            groups.append([item])
            y_values.append(y)
        else:
            groups[target].append(item)
            y_values[target] = sum(word.bbox[1] for word, _ in groups[target]) / len(groups[target])
    lines = []
    for y, group in zip(y_values, groups):
        group.sort(key=lambda item: (item[0].bbox[0], item[0].bbox[2], item[1]))
        lines.append(_PageLine(round(y, 3), tuple(group)))
    return tuple(sorted(lines, key=lambda line: line.y))


def _scoped_words(
    line: _PageLine, minimum_x: float, maximum_x: float | None = None
) -> tuple[tuple[EvidenceWord, str], ...]:
    return tuple(
        item
        for item in line.words
        if item[0].bbox[0] >= minimum_x
        and (maximum_x is None or item[0].bbox[0] < maximum_x)
    )


def _words_text(words: Iterable[tuple[EvidenceWord, str]]) -> str:
    return " ".join(word.text for word, _ in words)


def _words_block_ids(words: Iterable[tuple[EvidenceWord, str]]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(block_id for _, block_id in words))


def _word_anchor(line: _PageLine, labels: set[str]) -> float | None:
    for word, _ in line.words:
        token = re.sub(r"[^a-z]", "", word.text.casefold())
        if token in labels:
            return (word.bbox[0] + word.bbox[2]) / 2
    return None


def _nearest_numeric(line: _PageLine, anchor: float, metric: str) -> ParsedValue:
    candidates: list[tuple[float, ParsedValue]] = []
    for index, (word, _) in enumerate(line.words):
        if PERIOD_RE.fullmatch(word.text.strip()):
            continue
        cell_text = word.text
        previous = line.words[index - 1][0].text.upper() if index else ""
        if index and (previous in CURRENCY_CODES or re.fullmatch(r"[€$£¥]", previous)):
            cell_text = f"{line.words[index - 1][0].text} {cell_text}"
        parsed = parse_value(cell_text, metric=metric)
        if parsed.value is None:
            continue
        center = (word.bbox[0] + word.bbox[2]) / 2
        distance = abs(center - anchor)
        if distance <= 70:
            candidates.append((distance, parsed))
    return min(candidates, key=lambda item: item[0])[1] if candidates else ParsedValue(None, None)


def _with_context_unit(
    value: ParsedValue, context_unit: str | None, metric: str
) -> ParsedValue:
    if value.value is None or value.unit not in {None, "per_share"} or context_unit is None:
        return value
    if metric in PER_SHARE_METRICS and not context_unit.endswith("/share"):
        context_unit = f"{context_unit}/share"
    return ParsedValue(value.value, context_unit, value.state)


def _group_period_line(
    lines: tuple[_PageLine, ...],
    header_index: int,
    new_anchor: float,
    old_anchor: float,
    change_anchor: float | None,
) -> _PageLine | None:
    if change_anchor is None:
        return None
    for line in lines[header_index + 1 :]:
        if line.y - lines[header_index].y > 45:
            break
        periods = [normalize_fiscal_period(word.text)[0] for word, _ in line.words]
        if len([period for period in periods if period]) >= 4:
            return line
    return None


def _header_table_revisions(page: EvidencePage, candidate_ids: set[str]) -> list[EstimateRevision]:
    lines = _page_lines(page)
    revisions: list[EstimateRevision] = []
    for header_index, header in enumerate(lines):
        old_anchor = _word_anchor(header, {"old", "previous", "prev", "former"})
        new_anchor = _word_anchor(header, {"new", "current", "revised"})
        if old_anchor is None or new_anchor is None or old_anchor == new_anchor:
            continue
        if re.search(r"\bchange\s+(?:vs\.?|versus)\s+previous\b", header.text, re.I):
            continue
        consensus_anchor = _word_anchor(header, {"consensus"})
        change_anchor = _word_anchor(header, {"change", "revision"})
        if _group_period_line(
            lines, header_index, new_anchor, old_anchor, change_anchor
        ) is not None:
            continue
        first_value_x = min(old_anchor, new_anchor, *(value for value in (consensus_anchor, change_anchor) if value is not None))
        headings = [
            line
            for line in lines[:header_index]
            if 0 <= header.y - line.y <= 100
            and re.search(
                r"\b(?:key|estimate|forecast)\s+(?:changes?|revisions?)\b",
                line.text,
                re.I,
            )
        ]
        if headings:
            heading_block_ids = {
                block_id
                for word, block_id in headings[-1].words
                if re.fullmatch(r"changes?|revisions?", word.text, re.I)
            }
            left_bound = min(
                word.bbox[0]
                for word, block_id in headings[-1].words
                if block_id in heading_block_ids
            )
        else:
            left_bound = first_value_x - 240
        right_bound = max(
            old_anchor,
            new_anchor,
            *(value for value in (consensus_anchor, change_anchor) if value is not None),
        ) + 90
        header_words = _scoped_words(header, left_bound, right_bound)
        header_text = _words_text(header_words)
        header_period, header_basis = normalize_fiscal_period(header_text)
        table_unit = normalize_unit(header_text)
        if change_anchor is not None and table_unit in {
            "%",
            "percentage_points",
            "basis_points",
        }:
            table_unit = None
        for row in lines[header_index + 1 :]:
            if row.y - header.y > 180:
                break
            if re.search(r"\b(?:estimate|forecast)\s+(?:changes?|revisions?)\b", row.text, re.I):
                break
            row_words = _scoped_words(row, left_bound, right_bound)
            label = _words_text(
                item for item in row_words if item[0].bbox[0] < first_value_x - 4
            )
            metric, qualifiers = normalize_metric(label or _words_text(row_words))
            if metric is None:
                continue
            period, basis = normalize_fiscal_period(label or row.text)
            period, basis = (period or header_period), (basis or header_basis)
            old = _with_context_unit(
                _nearest_numeric(row, old_anchor, metric), table_unit, metric
            )
            new = _with_context_unit(
                _nearest_numeric(row, new_anchor, metric), table_unit, metric
            )
            consensus = (
                _with_context_unit(
                    _nearest_numeric(row, consensus_anchor, metric), table_unit, metric
                )
                if consensus_anchor is not None
                else ParsedValue(None, None)
            )
            stated_pct = stated_pp = None
            if change_anchor is not None:
                change = _nearest_numeric(row, change_anchor, metric)
                if change.unit == "percentage_points":
                    stated_pp = change.value
                elif change.unit == "%":
                    stated_pct = change.value
            if old.value is None and new.value is None and stated_pct is None and stated_pp is None:
                continue
            block_ids = tuple(
                dict.fromkeys(
                    _words_block_ids(header_words) + _words_block_ids(row_words)
                )
            )
            revisions.append(
                _finalize_revision(
                    metric=metric,
                    qualifiers=qualifiers,
                    period=period,
                    period_basis=basis,
                    old=old,
                    new=new,
                    stated_pct=stated_pct,
                    stated_pp=stated_pp,
                    consensus=consensus,
                    evidence=(RevisionEvidence(page.page_number, block_ids),),
                    method="table_old_new",
                    source_text=f"{header_text} {_words_text(row_words)}",
                )
            )
    return revisions


def _grouped_old_new_table_revisions(page: EvidencePage) -> list[EstimateRevision]:
    lines = _page_lines(page)
    revisions: list[EstimateRevision] = []
    for header_index, header in enumerate(lines):
        old_anchor = _word_anchor(header, {"old", "previous", "prev", "former"})
        new_anchor = _word_anchor(header, {"new", "current", "revised"})
        change_anchor = _word_anchor(header, {"change", "revision"})
        if old_anchor is None or new_anchor is None or change_anchor is None:
            continue
        period_line = _group_period_line(
            lines, header_index, new_anchor, old_anchor, change_anchor
        )
        if period_line is None:
            continue
        new_old_boundary = (new_anchor + old_anchor) / 2
        old_change_boundary = (old_anchor + change_anchor) / 2
        columns: dict[str, dict[str, tuple[float, str | None]]] = {
            "new": {},
            "old": {},
            "change": {},
        }
        for word, _ in period_line.words:
            period, basis = normalize_fiscal_period(word.text)
            if period is None:
                continue
            center = (word.bbox[0] + word.bbox[2]) / 2
            group = (
                "new"
                if center < new_old_boundary
                else "old"
                if center < old_change_boundary
                else "change"
            )
            columns[group][period] = (center, basis)
        common_periods = sorted(
            set(columns["new"]) & set(columns["old"]) & set(columns["change"]),
            key=lambda period: columns["new"][period][0],
        )
        if len(common_periods) < 2:
            continue
        first_value_x = min(anchor for anchor, _ in columns["new"].values())
        unit_context = normalize_unit(
            " ".join(
                line.text
                for line in lines
                if -35 <= line.y - header.y <= 45
            )
        )
        for row in lines:
            if not (period_line.y < row.y <= period_line.y + 520):
                continue
            label_words = tuple(
                item for item in row.words if item[0].bbox[0] < first_value_x - 4
            )
            label = _words_text(label_words)
            metric, qualifiers = normalize_metric(label)
            if metric is None:
                continue
            row_unit = normalize_unit(label, metric=metric)
            context_unit = row_unit or unit_context
            if metric in PER_SHARE_METRICS and context_unit and context_unit.endswith("m"):
                context_unit = "EUR/share" if context_unit.startswith("EUR") else "per_share"
            for period in common_periods:
                new = _with_context_unit(
                    _nearest_numeric(row, columns["new"][period][0], metric),
                    context_unit,
                    metric,
                )
                old = _with_context_unit(
                    _nearest_numeric(row, columns["old"][period][0], metric),
                    context_unit,
                    metric,
                )
                change = _nearest_numeric(
                    row, columns["change"][period][0], metric
                )
                if old.value is None or new.value is None:
                    continue
                stated_pct = change.value if change.unit == "%" else None
                stated_pp = (
                    change.value
                    if change.unit == "percentage_points"
                    else change.value / 100
                    if change.unit == "basis_points" and change.value is not None
                    else None
                )
                block_ids = tuple(
                    dict.fromkeys(
                        header.block_ids
                        + period_line.block_ids
                        + _words_block_ids(row.words)
                    )
                )
                revisions.append(
                    _finalize_revision(
                        metric=metric,
                        qualifiers=qualifiers,
                        period=period,
                        period_basis=columns["new"][period][1],
                        old=old,
                        new=new,
                        stated_pct=stated_pct,
                        stated_pp=stated_pp,
                        consensus=ParsedValue(None, None),
                        evidence=(RevisionEvidence(page.page_number, block_ids),),
                        method="table_grouped_old_new",
                        source_text=f"{header.text} {period_line.text} {row.text}",
                    )
                )
    return revisions


def _revision_matrix_revisions(page: EvidencePage, candidate_ids: set[str]) -> list[EstimateRevision]:
    lines = _page_lines(page)
    revisions: list[EstimateRevision] = []
    context_lines = [
        line
        for line in lines
        if re.search(
            r"\b(?:estimate|forecast)\s+(?:changes?|revisions?)\b", line.text, re.I
        )
        and not re.search(
            r"\bchange\s+(?:vs\.?|versus)\s+previous\b", line.text, re.I
        )
    ]
    for context in context_lines:
        context_block_ids = {
            block_id
            for word, block_id in context.words
            if re.fullmatch(r"estimates?|forecasts?", word.text, re.I)
        }
        context_x = min(
            word.bbox[0]
            for word, block_id in context.words
            if block_id in context_block_ids
        )
        for header_index, header in enumerate(lines):
            if not (0 <= header.y - context.y <= 90):
                continue
            if any(context.y < other.y <= header.y for other in context_lines):
                continue
            change_headings = [
                line
                for line in lines
                if context.y <= line.y < header.y
                and re.search(r"\bchange\s+(?:vs\.?|versus)\s+previous\b", line.text, re.I)
            ]
            matrix_x = context_x
            if change_headings:
                change_words = [
                    word
                    for word, _ in change_headings[-1].words
                    if re.fullmatch(r"change", word.text, re.I)
                ]
                if change_words:
                    matrix_x = min(word.bbox[0] for word in change_words) - 15
            periods: list[tuple[float, str, str | None]] = []
            for word, _ in header.words:
                if word.bbox[0] < matrix_x - 5:
                    continue
                period, basis = normalize_fiscal_period(word.text)
                if period:
                    periods.append(((word.bbox[0] + word.bbox[2]) / 2, period, basis))
            if len(periods) < 2:
                continue
            for row in lines[header_index + 1 :]:
                if row.y - header.y > 350:
                    break
                row_words = _scoped_words(row, context_x - 5)
                row_text = _words_text(row_words)
                metric, qualifiers = normalize_metric(row_text)
                if metric is None:
                    continue
                for anchor, period, basis in periods:
                    value = _nearest_numeric(row, anchor, metric)
                    if value.value is None or value.unit not in {"%", "percentage_points", "basis_points"}:
                        continue
                    stated_pct = value.value if value.unit == "%" else None
                    stated_pp = value.value if value.unit == "percentage_points" else value.value / 100 if value.unit == "basis_points" else None
                    header_words = _scoped_words(header, matrix_x - 5)
                    block_ids = tuple(
                        dict.fromkeys(
                            context.block_ids
                            + _words_block_ids(header_words)
                            + _words_block_ids(row_words)
                        )
                    )
                    revisions.append(
                        _finalize_revision(
                            metric=metric,
                            qualifiers=qualifiers,
                            period=period,
                            period_basis=basis,
                            old=ParsedValue(None, None),
                            new=ParsedValue(None, None),
                            stated_pct=stated_pct,
                            stated_pp=stated_pp,
                            consensus=ParsedValue(None, None),
                            evidence=(RevisionEvidence(page.page_number, block_ids),),
                            method="table_revision_matrix",
                            source_text=f"{context.text} {_words_text(header_words)} {row_text}",
                            warnings=("matrix_supplies_change_without_old_new_values",),
                        )
                    )
    return revisions


def _consensus_observations(page: EvidencePage) -> tuple[_ConsensusObservation, ...]:
    lines = _page_lines(page)
    observations: list[_ConsensusObservation] = []
    for row_index, row in enumerate(lines):
        if not CONSENSUS_RE.search(row.text):
            continue
        metric, qualifiers = normalize_metric(row.text)
        if metric is None:
            continue
        headers: list[tuple[int, _PageLine, list[tuple[float, str, str | None]]]] = []
        for header_index in range(max(0, row_index - 20), row_index):
            header = lines[header_index]
            if row.y - header.y > 140:
                continue
            periods: list[tuple[float, str, str | None]] = []
            for word, _ in header.words:
                period, basis = normalize_fiscal_period(word.text)
                if period and (period.endswith("E") or period.startswith(("FY", "CY", "Q", "H"))):
                    periods.append(((word.bbox[0] + word.bbox[2]) / 2, period, basis))
            if len(periods) >= 2:
                headers.append((header_index, header, periods))
        if not headers:
            continue
        header_index, header, periods = headers[-1]
        unit_context = normalize_unit(header.text, metric=metric)
        if unit_context is None:
            for context_line in reversed(lines[max(0, header_index - 3) : header_index]):
                unit_context = normalize_unit(context_line.text, metric=metric)
                if unit_context is not None:
                    break
        for anchor, period, _ in periods:
            parsed = _with_context_unit(
                _nearest_numeric(row, anchor, metric), unit_context, metric
            )
            if parsed.value is None:
                continue
            block_ids = tuple(
                dict.fromkeys(header.block_ids + row.block_ids)
            )
            observations.append(
                _ConsensusObservation(
                    page_number=page.page_number,
                    metric=metric,
                    qualifiers=qualifiers,
                    period=period,
                    value=parsed,
                    block_ids=block_ids,
                )
            )
    return tuple(observations)


def _attach_consensus(
    revisions: tuple[EstimateRevision, ...],
    observations: tuple[_ConsensusObservation, ...],
) -> tuple[EstimateRevision, ...]:
    by_key: dict[tuple, list[_ConsensusObservation]] = {}
    for observation in observations:
        by_key.setdefault(
            (
                observation.page_number,
                observation.metric,
                observation.qualifiers,
                observation.period,
                observation.value.unit,
            ),
            [],
        ).append(observation)
    enriched: list[EstimateRevision] = []
    for revision in revisions:
        if revision.fiscal_period is None or revision.unit is None:
            enriched.append(revision)
            continue
        key = (
            revision.evidence[0].page_number,
            revision.metric,
            revision.metric_qualifiers,
            revision.fiscal_period,
            revision.unit,
        )
        candidates = by_key.get(key, [])
        distinct = {(item.value.value, item.value.unit) for item in candidates}
        if len(distinct) != 1:
            enriched.append(revision)
            continue
        observation = candidates[0]
        consensus_value = observation.value.value
        if consensus_value is None:
            enriched.append(revision)
            continue
        old_spread = new_spread = None
        warnings = list(revision.warnings)
        if revision.old_value is not None:
            old_spread, warning = calculate_consensus_spread(
                revision.old_value, consensus_value
            )
            if warning:
                warnings.append(f"old_{warning}")
        if revision.new_value is not None:
            new_spread, warning = calculate_consensus_spread(
                revision.new_value, consensus_value
            )
            if warning:
                warnings.append(f"new_{warning}")
        enriched.append(
            replace(
                revision,
                consensus_value=consensus_value,
                old_vs_consensus_pct=old_spread,
                new_vs_consensus_pct=new_spread,
                evidence=revision.evidence
                + (
                    RevisionEvidence(
                        observation.page_number, observation.block_ids
                    ),
                ),
                warnings=tuple(dict.fromkeys(warnings)),
            )
        )
    return tuple(enriched)


def _candidate_blocks(document: EvidenceDocument) -> tuple[tuple[int, ...], tuple[str, ...]]:
    pages: set[int] = set()
    block_ids: list[str] = []
    for page in document.pages:
        for block in page.blocks:
            text = " ".join(block.text.split())
            if DISCLOSURE_RE.search(text):
                continue
            metric, _ = normalize_metric(text)
            table_heading = re.search(r"\b(?:estimate|forecast)\s+(?:changes?|revisions?)\b", text, re.I)
            header = re.search(r"\b(?:old|previous|prev\.?)\b.*\b(?:new|current|revised)\b|\b(?:new|current|revised)\b.*\b(?:old|previous|prev\.?)\b", text, re.I | re.S)
            signal_count = sum(bool(pattern.search(text)) for pattern in (REVISION_SIGNAL_RE, CONSENSUS_RE, PERIOD_RE, NUMBER_TOKEN_RE))
            if table_heading or header or (metric is not None and signal_count >= 3):
                pages.add(page.page_number)
                block_ids.append(block.block_id)
    return tuple(sorted(pages)), tuple(dict.fromkeys(block_ids))


def _inline_change_revisions(
    page: EvidencePage, candidate_ids: set[str]
) -> list[EstimateRevision]:
    revisions: list[EstimateRevision] = []
    pair_re = re.compile(
        r"(?P<change>[+-]?\d+(?:[.,]\d+)?)\s*(?P<kind>%|pp|ppts?|bp|bps)\s*"
        r"(?P<period>(?:FY|CY)?\s*(?:20\d{2}|\d{2})[Ee]?)",
        re.I,
    )
    standalone_re = re.compile(
        r"(?P<change>[+-]?\d+(?:[.,]\d+)?)\s*(?P<kind>%|pp|ppts?|bp|bps)",
        re.I,
    )
    for block in page.blocks:
        if block.block_id not in candidate_ids:
            continue
        lines = block.text.splitlines()
        for index, line in enumerate(lines):
            if not re.search(r"\bchange\s+in\b", line, re.I):
                continue
            line = f"{line} {lines[index + 1]}" if index + 1 < len(lines) else line
            metric, qualifiers = normalize_metric(line)
            if metric is None:
                continue
            matches = list(pair_re.finditer(line))
            if not matches and metric == "target_price":
                standalone = standalone_re.search(line)
                matches = [standalone] if standalone else []
            for match in matches:
                raw = float(match.group("change").replace(",", "."))
                kind = match.group("kind").casefold()
                stated_pct = raw if kind == "%" else None
                stated_pp = (
                    raw / 100
                    if kind.startswith("bp")
                    else raw
                    if kind.startswith("pp")
                    else None
                )
                period, basis = (
                    normalize_fiscal_period(match.group("period"))
                    if "period" in match.re.groupindex
                    else (None, None)
                )
                revisions.append(
                    _finalize_revision(
                        metric=metric,
                        qualifiers=qualifiers,
                        period=period,
                        period_basis=basis,
                        old=ParsedValue(None, None),
                        new=ParsedValue(None, None),
                        stated_pct=stated_pct,
                        stated_pp=stated_pp,
                        consensus=ParsedValue(None, None),
                        evidence=(RevisionEvidence(page.page_number, (block.block_id,)),),
                        method="inline_stated_change",
                        source_text=line,
                        warnings=("stated_change_without_old_new_values",),
                    )
                )
    return revisions


def _compact_target_revisions(
    page: EvidencePage, candidate_ids: set[str]
) -> list[EstimateRevision]:
    revisions: list[EstimateRevision] = []
    pattern = re.compile(
        r"\b(?:target price|price target|price obj\.?|price objective|TP|PO)\b\s*:?\s*"
        r"(?P<new>(?:[A-Z]{3}\s*|[€$£¥]\s*)?[-+]?\d+(?:[.,]\d+)?)"
        r"\s*\(\s*(?P<old>\d+(?:[.,]\d+)?)\s*\)",
        re.I,
    )
    for block in page.blocks:
        if block.block_id not in candidate_ids:
            continue
        text = " ".join(block.text.split())
        match = pattern.search(text)
        if not match:
            continue
        new = parse_value(match.group("new"), metric="target_price")
        old = parse_value(match.group("old"), metric="target_price")
        if old.value is not None and old.unit is None:
            old = ParsedValue(old.value, new.unit)
        stated_pct, stated_pp = _extract_explicit_change(text)
        revisions.append(
            _finalize_revision(
                metric="target_price",
                qualifiers=(),
                period=None,
                period_basis=None,
                old=old,
                new=new,
                stated_pct=stated_pct,
                stated_pp=stated_pp,
                consensus=ParsedValue(None, None),
                evidence=(RevisionEvidence(page.page_number, (block.block_id,)),),
                method="compact_target_header",
                source_text=text,
            )
        )
    return revisions


def _deduplicate(revisions: Iterable[EstimateRevision]) -> tuple[EstimateRevision, ...]:
    unique: dict[tuple, EstimateRevision] = {}
    method_rank = {
        "compact_target_header": 5,
        "table_grouped_old_new": 5,
        "table_old_new": 4,
        "prose_old_new": 3,
        "inline_stated_change": 2,
        "table_revision_matrix": 1,
    }
    for revision in revisions:
        target_complete = (
            revision.metric == "target_price"
            and revision.old_value is not None
            and revision.new_value is not None
        )
        key = (
            revision.metric,
            revision.metric_qualifiers,
            revision.fiscal_period,
            revision.old_value,
            revision.new_value,
            revision.unit,
            None if target_complete else revision.stated_revision_pct,
            None if target_complete else revision.stated_change_pp,
            revision.evidence[0].page_number,
        )
        current = unique.get(key)
        if current is None or method_rank[revision.extraction_method] > method_rank[current.extraction_method]:
            unique[key] = revision
    values = list(unique.values())
    complete_target_pages = {
        item.evidence[0].page_number
        for item in values
        if item.metric == "target_price"
        and item.old_value is not None
        and item.new_value is not None
    }
    values = [
        item
        for item in values
        if not (
            item.metric == "target_price"
            and item.old_value is None
            and item.new_value is None
            and item.evidence[0].page_number in complete_target_pages
        )
    ]
    conflict_groups: dict[tuple, list[EstimateRevision]] = {}
    for item in values:
        conflict_groups.setdefault(
            (
                item.evidence[0].page_number,
                item.metric,
                item.metric_qualifiers,
                item.fiscal_period,
            ),
            [],
        ).append(item)
    conflicted: list[EstimateRevision] = []
    for group in conflict_groups.values():
        distinct = {(item.old_value, item.new_value, item.unit) for item in group}
        if len(distinct) > 1:
            group = [
                replace(
                    item,
                    warnings=tuple(
                        dict.fromkeys(
                            item.warnings
                            + ("conflicting_candidates_same_metric_period",)
                        )
                    ),
                )
                for item in group
            ]
        conflicted.extend(group)
    return tuple(sorted(conflicted, key=lambda item: (item.evidence[0].page_number, item.metric, item.fiscal_period or "", item.extraction_method)))


class RevisionExtractor:
    """Deterministically extract conservative estimate-revision candidates."""

    def extract(self, document: EvidenceDocument, *, broker: str | None = None) -> RevisionResult:
        # Broker-specific behavior is deliberately isolated here. No broker override is
        # currently required; all enabled parsers operate on explicit text/geometry signals.
        _ = broker
        candidate_pages, candidate_block_ids = _candidate_blocks(document)
        candidate_set = set(candidate_block_ids)
        revisions: list[EstimateRevision] = []
        consensus_observations: list[_ConsensusObservation] = []
        for page in document.pages:
            consensus_observations.extend(_consensus_observations(page))
            if page.page_number not in candidate_pages:
                continue
            revisions.extend(_prose_revisions(page, candidate_set))
            revisions.extend(_header_table_revisions(page, candidate_set))
            revisions.extend(_grouped_old_new_table_revisions(page))
            revisions.extend(_revision_matrix_revisions(page, candidate_set))
            revisions.extend(_inline_change_revisions(page, candidate_set))
            revisions.extend(_compact_target_revisions(page, candidate_set))
        deduplicated = _deduplicate(revisions)
        enriched = _attach_consensus(
            deduplicated, tuple(consensus_observations)
        )
        if enriched:
            status = "revisions_found"
            warnings: tuple[str, ...] = ()
        elif candidate_block_ids:
            status = "candidates_unresolved"
            warnings = ("revision_signals_detected_but_no_safe_rows_were_parsed",)
        else:
            status = "no_revisions"
            warnings = ()
        return RevisionResult(
            status=status,
            document_id=document.document_id,
            source_filename=document.source_filename,
            candidate_pages=candidate_pages,
            candidate_block_ids=candidate_block_ids,
            revisions=enriched,
            warnings=warnings,
        )
