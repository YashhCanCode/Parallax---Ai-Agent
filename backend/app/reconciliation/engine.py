"""Deterministic reconciliation of financial figures across filings, concepts and sources.

Nothing here calls a model. Every finding cites observation ids and states its arithmetic.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from typing import Iterable, Optional

from app.financial_data.companies import METRIC_BY_KEY, MetricDef
from app.models.schemas import Classification, EvidenceRef, Finding, FindingStatus, Observation

MATCH_TOLERANCE = 0.005  # 0.5% relative difference counts as the same figure


def fmt_usd(v: float) -> str:
    a = abs(v)
    sign = "-" if v < 0 else ""
    if a >= 1e12:
        return f"{sign}${a / 1e12:,.2f}T"
    if a >= 1e9:
        return f"{sign}${a / 1e9:,.2f}B"
    if a >= 1e6:
        return f"{sign}${a / 1e6:,.1f}M"
    return f"{sign}${a:,.0f}"


def rel_diff(a: float, b: float) -> Optional[float]:
    """Relative difference of a vs b; None when b is zero (undefined)."""
    if b == 0:
        return None
    return (a - b) / abs(b)


def close(a: float, b: float, tol: float = MATCH_TOLERANCE) -> bool:
    if b == 0:
        return a == 0
    d = rel_diff(a, b)
    return d is not None and abs(d) <= tol


def is_primary(o: Observation) -> bool:
    return o.form != "secondary"


def period_label(start: Optional[date], end: date, period_type: str) -> str:
    if period_type == "instant":
        return f"as of {end.isoformat()}"
    if period_type == "annual":
        return f"FY ending {end.isoformat()}"
    return f"{start.isoformat() if start else '?'} to {end.isoformat()} ({period_type})"


@dataclass
class PeriodResolution:
    """The resolved figure for one period of one metric, from primary filings."""

    metric: str
    period_start: Optional[date]
    period_end: date
    period_type: str
    current: Observation  # preferred concept, latest filing
    original: Observation  # preferred concept, earliest filing
    by_concept: dict[str, list[Observation]] = field(default_factory=dict)

    @property
    def revised(self) -> bool:
        return not close(self.current.value, self.original.value, 1e-9)

    @property
    def label(self) -> str:
        return period_label(self.period_start, self.period_end, self.period_type)


def _filed_key(o: Observation) -> tuple:
    return (o.published_at or date.min, o.accession_number or "")


STATEMENT_FORM_PREFIXES = ("10-K", "10-Q", "20-F", "40-F", "10-KT", "10-QT")


def is_statement_form(o: Observation) -> bool:
    """Periodic financial-statement filings (and their amendments). Other documents that carry XBRL
    facts, such as proxy statements (DEF 14A) or registration statements, are compared but never
    treated as the source of record or as a 'revision'."""
    return (o.form or "").upper().startswith(STATEMENT_FORM_PREFIXES)


def resolve_periods(
    observations: Iterable[Observation], metric: MetricDef, period_types: tuple[str, ...] = ("annual", "instant")
) -> list[PeriodResolution]:
    """Group primary observations by period and pick a current value per period.

    Concept priority follows MetricDef.tags; within a concept the most recently filed value
    wins (later filings carry revised comparatives).
    """
    groups: dict[tuple, list[Observation]] = defaultdict(list)
    for o in observations:
        if o.metric == metric.key and is_primary(o) and o.period_type in period_types:
            groups[(o.period_start, o.period_end, o.period_type)].append(o)
    priority = {f"us-gaap:{t}": i for i, t in enumerate(metric.tags)}
    out: list[PeriodResolution] = []
    for (start, end, ptype), obs in groups.items():
        by_concept: dict[str, list[Observation]] = defaultdict(list)
        for o in obs:
            by_concept[o.concept].append(o)
        statement_concepts = [c for c, os in by_concept.items() if any(is_statement_form(o) for o in os)]
        best = min(statement_concepts or list(by_concept), key=lambda c: priority.get(c, 99))
        candidates = [o for o in by_concept[best] if is_statement_form(o)] or by_concept[best]
        ordered = sorted(candidates, key=_filed_key)
        out.append(
            PeriodResolution(metric.key, start, end, ptype, current=ordered[-1], original=ordered[0],
                             by_concept={k: sorted(v, key=_filed_key) for k, v in by_concept.items()})
        )
    out.sort(key=lambda r: r.period_end)
    return out


def consistent_window(series: list[PeriodResolution], n: int) -> list[PeriodResolution]:
    """Last n periods that share the latest period's concept, so trends never mix definitions."""
    if not series:
        return []
    concept = series[-1].current.concept
    out: list[PeriodResolution] = []
    for r in reversed(series):
        if r.current.concept != concept:
            break
        out.append(r)
        if len(out) == n:
            break
    return list(reversed(out))


def annual_series(observations: Iterable[Observation], metric_key: str) -> list[PeriodResolution]:
    metric = METRIC_BY_KEY[metric_key]
    types = ("instant",) if metric.kind == "instant" else ("annual",)
    res = resolve_periods(observations, metric, types)
    if metric.kind == "instant":
        # Keep fiscal year-end balances only: those reported in a 10-K (or sample 10-K).
        res = [r for r in res if any((o.form or "").startswith("10-K") for os in r.by_concept.values() for o in os)]
    return res


# ---------------------------------------------------------------------------------------
# Findings about the filings themselves
# ---------------------------------------------------------------------------------------

def _fid(prefix: str, *parts: object) -> str:
    import hashlib

    return f"{prefix}-" + hashlib.sha1("|".join(map(str, parts)).encode()).hexdigest()[:8]


def revision_findings(observations: list[Observation], metric_key: str, max_items: int = 3) -> list[Finding]:
    """Periods whose figure differs between the original filing and a later filing."""
    metric = METRIC_BY_KEY[metric_key]
    revised = [r for r in annual_series(observations, metric_key) if r.revised]
    findings: list[Finding] = []
    for r in revised[-max_items:]:
        diff = r.current.value - r.original.value
        pct = rel_diff(r.current.value, r.original.value)
        findings.append(
            Finding(
                id=_fid("rev", metric_key, r.period_end, r.original.id, r.current.id),
                category="financial_truth",
                title=f"{metric.label} for {r.label} was revised in a later filing",
                claim=(
                    f"{metric.label} for {r.label} was first reported as {fmt_usd(r.original.value)} "
                    f"({r.original.form}, filed {r.original.published_at}) and later as {fmt_usd(r.current.value)} "
                    f"({r.current.form}, filed {r.current.published_at})."
                ),
                classification=Classification.reported_fact,
                supporting_evidence=[
                    EvidenceRef(observation_id=r.original.id, note="originally reported"),
                    EvidenceRef(observation_id=r.current.id, note="most recent filing"),
                ],
                calculation_details={
                    "formula": "difference = latest - original; pct = difference / |original|",
                    "inputs": {"original": r.original.value, "latest": r.current.value},
                    "difference": diff,
                    "pct": pct,
                },
                uncertainty_or_limitations=(
                    "XBRL facts show that the figure changed, not why. A restatement, a reclassification, "
                    "discontinued operations or an accounting-standard change can all produce this; read the "
                    "later filing's notes to confirm the cause."
                ),
                why_it_matters="Two sources quoting this period can both be 'right' if one predates the revision.",
                status=FindingStatus.supported,
                severity="watch" if pct is not None and abs(pct) >= 0.01 else "info",
            )
        )
    return findings


def concept_findings(observations: list[Observation], metric_key: str) -> list[Finding]:
    """Detect the same period reported under different XBRL concepts, and concept switches."""
    metric = METRIC_BY_KEY[metric_key]
    series = annual_series(observations, metric_key)
    findings: list[Finding] = []
    overlaps = [r for r in series if len(r.by_concept) > 1]
    for r in overlaps[-2:]:
        concepts = list(r.by_concept)
        latest = {c: r.by_concept[c][-1] for c in concepts}
        values = {c: o.value for c, o in latest.items()}
        same = len({round(v) for v in values.values()}) == 1
        a, b = concepts[0], concepts[1]
        findings.append(
            Finding(
                id=_fid("concept", metric_key, r.period_end, *concepts),
                category="financial_truth",
                title=f"{metric.label} for {r.label} appears under {len(concepts)} different definitions",
                claim=(
                    f"{a} reports {fmt_usd(values[a])} and {b} reports {fmt_usd(values[b])} for {r.label}."
                    + (" The values agree." if same else " The values differ.")
                ),
                classification=Classification.reported_fact,
                supporting_evidence=[EvidenceRef(observation_id=o.id, note=c) for c, o in latest.items()],
                calculation_details={
                    "formula": "difference = value(concept B) - value(concept A)",
                    "inputs": values,
                    "difference": values[b] - values[a],
                },
                uncertainty_or_limitations=(
                    "Different US-GAAP concepts have different definitions (for example, revenue under ASC 606 "
                    "excludes some items that the broader 'Revenues' concept may include). FinSight uses the "
                    f"concept order {', '.join(metric.tags)} and shows the alternatives instead of mixing them."
                ),
                why_it_matters="Data sites that pull a different concept can show a different number for the same year.",
                status=FindingStatus.supported,
                severity="info" if same else "watch",
            )
        )
    # Concept switch: the preferred concept's history starts after an older concept's ends.
    concept_years: dict[str, list[date]] = defaultdict(list)
    for r in series:
        for c in r.by_concept:
            concept_years[c].append(r.period_end)
    if len(concept_years) > 1:
        spans = sorted(((min(v), max(v), c) for c, v in concept_years.items()), key=lambda s: s[1])
        older, newer = spans[0], spans[-1]
        if older[1] < newer[1]:
            ev = [r for r in series if older[2] in r.by_concept][-1].by_concept[older[2]][-1]
            ev2 = [r for r in series if newer[2] in r.by_concept][0].by_concept[newer[2]][-1]
            findings.append(
                Finding(
                    id=_fid("switch", metric_key, older[2], newer[2]),
                    category="financial_truth",
                    title=f"{metric.label} switched reporting concept",
                    claim=(
                        f"The company's filings stop using {older[2]} after the period ending {older[1]} "
                        f"and use {newer[2]} from the period ending {newer[0]}."
                    ),
                    classification=Classification.reported_fact,
                    supporting_evidence=[EvidenceRef(observation_id=ev.id, note=f"last {older[2]}"),
                                         EvidenceRef(observation_id=ev2.id, note=f"first {newer[2]}")],
                    uncertainty_or_limitations=(
                        "A tool that reads only the older concept will look as if the data stopped. FinSight "
                        "joins the series using the concept priority above; check the overlap year for definition differences."
                    ),
                    why_it_matters="This is a common reason a data source shows 'no revenue' for recent years.",
                    status=FindingStatus.supported,
                    severity="info",
                )
            )
    return findings


def other_document_findings(observations: list[Observation], metric_key: str, recent: int = 3) -> list[Finding]:
    """Non-statement documents (e.g. DEF 14A proxy statements) reporting a different figure."""
    metric = METRIC_BY_KEY[metric_key]
    findings: list[Finding] = []
    for r in annual_series(observations, metric_key)[-recent:]:
        for o in r.by_concept.get(r.current.concept, []):
            if is_statement_form(o) or close(o.value, r.current.value, 1e-9):
                continue
            pct = rel_diff(o.value, r.current.value)
            findings.append(Finding(
                id=_fid("doc", metric_key, r.period_end, o.id),
                category="financial_truth",
                title=f"{o.form} shows a different {metric.label.lower()} than the {r.current.form} for {r.label}",
                claim=(f"The {o.form} filed {o.published_at} reports {fmt_usd(o.value)}; the {r.current.form} filed "
                       f"{r.current.published_at} reports {fmt_usd(r.current.value)} under the same concept {o.concept}."),
                classification=Classification.reported_fact,
                supporting_evidence=[EvidenceRef(observation_id=r.current.id, note=f"{r.current.form} (source of record)")],
                counterevidence=[EvidenceRef(observation_id=o.id, note=o.form or "other document")],
                calculation_details={"formula": "pct = (other - statement) / |statement|",
                                     "inputs": {"statement": r.current.value, "other": o.value}, "pct": pct},
                uncertainty_or_limitations=(
                    f"A {o.form} is not a financial-statement filing, so FinSight does not treat it as a revision. "
                    "Proxy statements (DEF 14A) often present measures defined for executive-pay tables, which can "
                    "differ in scope (for example, including non-controlling interests). The filings do not state the "
                    "reason here, so it is not asserted."
                ),
                why_it_matters="A data site that pulls the latest XBRL fact regardless of document type may show this figure.",
                status=FindingStatus.supported,
                severity="watch" if pct is not None and abs(pct) >= 0.01 else "info",
            ))
    return findings


def consistency_finding(observations: list[Observation], metric_key: str) -> Optional[Finding]:
    metric = METRIC_BY_KEY[metric_key]
    series = annual_series(observations, metric_key)
    if not series:
        return None
    r = series[-1]
    same_concept = [o for o in r.by_concept[r.current.concept] if is_statement_form(o)] or r.by_concept[r.current.concept]
    distinct = {o.value for o in same_concept}
    filings = sorted({o.accession_number for o in same_concept if o.accession_number})
    return Finding(
        id=_fid("latest", metric_key, r.period_end),
        category="financial_truth",
        title=f"Latest annual {metric.label.lower()}: {fmt_usd(r.current.value)} ({r.label})",
        claim=(
            f"{metric.label} for {r.label} is {fmt_usd(r.current.value)} under {r.current.concept}, "
            f"reported in {len(filings)} filing(s)"
            + (" with one consistent value." if len(distinct) == 1 else f" with {len(distinct)} different values.")
        ),
        classification=Classification.reported_fact,
        supporting_evidence=[EvidenceRef(observation_id=o.id, note=o.form or "") for o in same_concept],
        uncertainty_or_limitations="Values are as filed in XBRL; they are not audited by FinSight.",
        status=FindingStatus.supported if len(distinct) == 1 else FindingStatus.unresolved,
        severity="info",
    )


# ---------------------------------------------------------------------------------------
# Explaining an outside value (secondary source or user claim)
# ---------------------------------------------------------------------------------------

@dataclass
class Explanation:
    kind: str  # match | unit_normalized_match | unit_scale | period_mismatch | revision | stale_source
    #            | alternate_concept | basis | fiscal_year_offset | unexplained | no_data
    status: FindingStatus
    text: str
    matched: Optional[Observation] = None
    reference: Optional[PeriodResolution] = None
    details: dict = field(default_factory=dict)


def explain_value(
    value: float,
    observations: list[Observation],
    metric_key: str,
    *,
    period_end_year: Optional[int] = None,
    period_end: Optional[date] = None,
    basis: str = "consolidated",
    published_at: Optional[date] = None,
    was_unit_scaled: bool = False,
    is_user_claim: bool = False,
) -> Explanation:
    metric = METRIC_BY_KEY[metric_key]
    series = annual_series(observations, metric_key)
    if not series:
        return Explanation("no_data", FindingStatus.insufficient_evidence,
                           f"No reported {metric.label.lower()} figures are available to compare against.")
    ref: Optional[PeriodResolution] = None
    if period_end is not None:
        ref = next((r for r in series if r.period_end == period_end), None)
    elif period_end_year is not None:
        ref = next((r for r in series if r.period_end.year == period_end_year), None)
    else:
        ref = series[-1]
    if ref is None:
        years = ", ".join(str(r.period_end.year) for r in series)
        return Explanation("no_data", FindingStatus.insufficient_evidence,
                           f"No annual {metric.label.lower()} figure exists for that year (available: {years}).")
    cur = ref.current.value
    details = {"compared_value": value, "reference_value": cur, "pct_difference": rel_diff(value, cur)}

    if close(value, cur):
        if was_unit_scaled:
            return Explanation("unit_normalized_match", FindingStatus.supported,
                               f"Matches the filed figure {fmt_usd(cur)} once the source's units are converted to USD.",
                               ref.current, ref, details)
        return Explanation("match", FindingStatus.supported, f"Matches the filed figure {fmt_usd(cur)} for {ref.label}.",
                           ref.current, ref, details)

    if basis != "consolidated":
        return Explanation(
            "basis", FindingStatus.supported,
            f"The source reports a {basis} figure; the filings' {fmt_usd(cur)} is consolidated (includes subsidiaries). "
            f"The two measure different scopes, so the gap is expected. FinSight cannot verify the {basis} figure itself.",
            ref.current, ref, details,
        )

    # Earlier filed value for the same period (any concept).
    for concept, obs in ref.by_concept.items():
        for o in obs:
            if close(value, o.value) and o.id != ref.current.id:
                if not is_statement_form(o):
                    return Explanation("other_document", FindingStatus.supported,
                                       f"Matches {fmt_usd(o.value)} reported in a {o.form} (filed {o.published_at}), "
                                       f"not the {ref.current.form}'s {fmt_usd(cur)}.", o, ref, details)
                if concept != ref.current.concept:
                    return Explanation("alternate_concept", FindingStatus.supported,
                                       f"Matches {fmt_usd(o.value)} reported under {concept}, not the preferred "
                                       f"{ref.current.concept} ({fmt_usd(cur)}).", o, ref, details)
                later = ref.current.published_at
                if published_at and later and published_at < later:
                    return Explanation(
                        "stale_source", FindingStatus.supported,
                        f"Matches the originally reported {fmt_usd(o.value)} (filed {o.published_at}). The source was "
                        f"published {published_at}, before the {ref.current.form} filed {later} revised it to {fmt_usd(cur)}.",
                        o, ref, details)
                return Explanation("revision", FindingStatus.supported,
                                   f"Matches the originally reported {fmt_usd(o.value)}; a later filing revised it to {fmt_usd(cur)}.",
                                   o, ref, details)

    # Quarterly / year-to-date figures inside the same fiscal year.
    fy_start = ref.period_start
    for o in observations:
        if (o.metric == metric_key and is_primary(o) and o.period_type in ("quarterly", "ytd")
                and fy_start and o.period_end <= ref.period_end and o.period_end > fy_start
                and close(value, o.value)):
            return Explanation(
                "period_mismatch", FindingStatus.supported,
                f"Matches the {o.period_type} figure {fmt_usd(o.value)} for {o.period_start} to {o.period_end} "
                f"({o.form}), not the full-year {fmt_usd(cur)}.", o, ref, details)

    for scale, label in ((1e3, "thousands"), (1e6, "millions"), (1e9, "billions"), (1e-3, "a thousand times too large"),
                         (1e-6, "a million times too large")):
        if close(value * scale, cur):
            return Explanation("unit_scale", FindingStatus.supported,
                               f"Equals the filed {fmt_usd(cur)} if the number is read in {label}; "
                               f"the gap is a unit difference.", ref.current, ref,
                               {**details, "scale_applied": scale})

    for r in series:
        if r is not ref and close(value, r.current.value):
            return Explanation("fiscal_year_offset", FindingStatus.supported,
                               f"Matches {fmt_usd(r.current.value)} for {r.label}, a different fiscal year than requested.",
                               r.current, ref, details)

    pct = details["pct_difference"]
    pct_txt = f"{pct * 100:+.1f}%" if pct is not None else "n/a"
    if is_user_claim:
        return Explanation("unexplained", FindingStatus.contradicted,
                           f"The filed figure for {ref.label} is {fmt_usd(cur)} ({pct_txt} difference). No period, "
                           f"unit, revision or definition difference explains the claimed value.", ref.current, ref, details)
    return Explanation("unexplained", FindingStatus.unresolved,
                       f"Differs from the filed {fmt_usd(cur)} by {pct_txt}. FinSight found no period, unit, basis, "
                       f"revision or definition difference that explains it, so this stays unresolved.",
                       ref.current, ref, details)


def secondary_source_findings(observations: list[Observation], metric_key: str) -> list[Finding]:
    metric = METRIC_BY_KEY[metric_key]
    findings: list[Finding] = []
    for s in observations:
        if s.metric != metric_key or is_primary(s):
            continue
        scaled = "scaled x" in s.extraction_notes and "scaled x1 " not in s.extraction_notes
        exp = explain_value(
            s.value, observations, metric_key, period_end=s.period_end, basis=s.reporting_basis,
            published_at=s.published_at, was_unit_scaled=scaled,
        )
        support = [EvidenceRef(observation_id=s.id, note="secondary source")]
        if exp.matched:
            support.append(EvidenceRef(observation_id=exp.matched.id, note=f"explains via {exp.kind}"))
        counter = []
        if exp.reference and exp.matched and exp.reference.current.id != exp.matched.id:
            counter.append(EvidenceRef(observation_id=exp.reference.current.id, note="current filed figure"))
        elif exp.kind in ("unexplained", "basis") and exp.reference:
            counter.append(EvidenceRef(observation_id=exp.reference.current.id, note="filed figure"))
        findings.append(
            Finding(
                id=_fid("src", s.id),
                category="financial_truth",
                title=f"{s.source_name}: {fmt_usd(s.value)} {metric.label.lower()} vs filings ({exp.kind.replace('_', ' ')})",
                claim=f"{s.source_name} reports {metric.label.lower()} of {fmt_usd(s.value)} for "
                      f"{period_label(s.period_start, s.period_end, s.period_type)}. {exp.text}",
                classification=Classification.calculation,
                supporting_evidence=support,
                counterevidence=counter,
                calculation_details={"formula": "pct_difference = (source - filed) / |filed|",
                                     "explanation_kind": exp.kind, **exp.details},
                uncertainty_or_limitations=(
                    "Secondary sources are not primary filings. "
                    + ("No supported explanation was found; FinSight does not guess one." if exp.kind == "unexplained" else
                       "The explanation is the first documented cause that reproduces the source's number exactly.")
                ),
                why_it_matters="Knowing why figures differ tells you which number answers your question.",
                status=exp.status,
                severity="watch" if exp.kind in ("unexplained", "stale_source", "period_mismatch") else "info",
            )
        )
    return findings


def channel_cross_check(
    primary_counts: dict[tuple[str, str], int],
    check_counts: dict[tuple[str, str], int],
    primary_obs: list[Observation],
    check_obs: list[Observation],
    primary_name: str = "Zetaris",
    check_name: str = "SEC EDGAR (direct)",
) -> Finding:
    """Compare what two retrieval channels returned for the same SEC concepts."""
    keys = sorted(set(primary_counts) | set(check_counts))
    rows = []
    mismatched = []
    for k in keys:
        a, b = primary_counts.get(k), check_counts.get(k)
        rows.append({"metric": k[0], "concept": k[1], primary_name: a, check_name: b})
        # A concept the company doesn't report has 0 rows on one side and no table on the other: that agrees.
        if (a or 0) != (b or 0):
            mismatched.append(k)

    def keyset(obs: list[Observation]) -> dict[tuple, float]:
        return {(o.metric, o.concept, o.period_start, o.period_end, o.accession_number): o.value for o in obs}

    pa, pb = keyset(primary_obs), keyset(check_obs)
    common = set(pa) & set(pb)
    value_mismatch = [k for k in common if not close(pa[k], pb[k], 1e-9)]
    ok = not mismatched and not value_mismatch and bool(common)
    return Finding(
        id=_fid("xcheck", primary_name, check_name, len(keys)),
        category="integration",
        title=f"{primary_name} vs {check_name}: {'rows and values agree' if ok else 'differences found'}",
        claim=(
            f"Compared {len(keys)} concept queries. {len(mismatched)} had different row counts; "
            f"{len(value_mismatch)} of {len(common)} shared facts had different values."
        ),
        classification=Classification.calculation,
        calculation_details={"rows": rows, "shared_facts": len(common), "value_mismatches": len(value_mismatch)},
        uncertainty_or_limitations=(
            "Zetaris's getting-started guide recommends this row-count check before trusting a REST table. "
            "Small timing differences can appear if SEC published a filing between the two requests."
        ),
        why_it_matters="Confirms the federated query returned the complete, unaltered source data.",
        status=FindingStatus.supported if ok else FindingStatus.unresolved,
        severity="info" if ok else "watch",
    )
