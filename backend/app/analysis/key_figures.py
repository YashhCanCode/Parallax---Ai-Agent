"""Key figures: the facts sheet for one company, computed in code from filed observations.

For every figure Parallax tracks (and a few derived from them: margins, free cash flow, cash minus debt) this
gives the latest fiscal-year value, the year before, the change, and the value a few years back. Each value
names the filing it came from. The same rows feed the Key figures table, the AI's evidence (so it never has to
calculate anything itself) and the answers Parallax writes without a model.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Callable, Optional

from app.models.schemas import Observation
from app.reconciliation.engine import PeriodResolution, annual_series, consistent_window, fmt_usd


@dataclass
class Point:
    period_end: date
    value: float
    evidence: list[str] = field(default_factory=list)  # observation ids
    form: Optional[str] = None
    filed: Optional[str] = None

    @property
    def fy(self) -> str:
        return f"FY{self.period_end.year}"


@dataclass
class KeyFigure:
    key: str
    label: str
    unit: str  # "usd" | "pct" | "ratio"
    points: list[Point]  # oldest first, one per fiscal year
    formula: str = "as filed"
    note: str = ""
    stale: bool = False  # latest value is more than a year older than the company's latest filings

    @property
    def latest(self) -> Optional[Point]:
        return self.points[-1] if self.points else None

    @property
    def prior(self) -> Optional[Point]:
        return self.points[-2] if len(self.points) >= 2 else None

    @property
    def change(self) -> Optional[float]:
        """Relative change for money (0.085 = +8.5%); difference in points for percentages and ratios.

        Money changes are only given when both years are positive: a percentage change from a negative or zero
        value (free cash flow from -$0.2B to -$1.9B) reads as nonsense, so those show the two values instead."""
        a, b = self.prior, self.latest
        if not a or not b:
            return None
        if self.unit == "usd":
            return (b.value - a.value) / a.value if a.value > 0 and b.value > 0 else None
        return b.value - a.value

    @property
    def direction(self) -> Optional[str]:
        a, b = self.prior, self.latest
        if self.stale or not a or not b or a.value == b.value:
            return None
        return "up" if b.value > a.value else "down"

    def fmt(self, v: float) -> str:
        if self.unit == "usd":
            return fmt_usd(v)
        if self.unit == "pct":
            return f"{v * 100:.1f}%"
        return f"{v:.2f}x"

    def fmt_change(self) -> Optional[str]:
        c = self.change
        if c is None:
            return None
        if self.unit == "usd":
            return f"{c * 100:+.1f}%"
        if self.unit == "pct":
            return f"{c * 100:+.1f} points"
        return f"{c:+.2f}x"

    def _abs_change(self) -> Optional[str]:
        """The change without its sign, for sentences that already say "up" or "down"."""
        c = self.fmt_change()
        return c.lstrip("+-") if c else None

    def sentence(self) -> str:
        """One plain line with every number written out, e.g. for the AI's evidence and for coded answers."""
        b, a = self.latest, self.prior
        verb = "were" if self.key in PLURAL else "was"
        if not b:
            return f"{self.label}: not reported in the filings Parallax read."
        if self.stale:
            return (f"{self.label} was last reported for {b.fy} ({self.fmt(b.value)}); the company's newer filings "
                    f"don't report it under this definition, so there is no current figure.")
        s = f"{self.label} {verb} {self.fmt(b.value)} in {b.fy}"
        if a:
            if not self.direction:
                s += f", unchanged from {a.fy}"
            elif self._abs_change():
                s += f", {self.direction} {self._abs_change()} from {self.fmt(a.value)} in {a.fy}"
            else:
                s += f", {'up' if self.direction == 'up' else 'down'} from {self.fmt(a.value)} in {a.fy}"
        if len(self.points) >= 4:
            first = self.points[0]
            s += f"; {'they were' if self.key in PLURAL else 'it was'} {self.fmt(first.value)} in {first.fy}"
        s += "."
        if self.formula != "as filed":
            s += f" ({self.formula})"
        return s

    def as_dict(self) -> dict[str, Any]:
        def p(x: Optional[Point]) -> Optional[dict[str, Any]]:
            return None if x is None else {"fy": x.fy, "period_end": x.period_end.isoformat(), "value": x.value,
                                           "display": self.fmt(x.value), "form": x.form, "filed": x.filed,
                                           "evidence": x.evidence}
        return {"key": self.key, "label": self.label, "unit": self.unit, "latest": p(self.latest), "prior": p(self.prior),
                "change": None if self.stale else self.change, "change_display": None if self.stale else self.fmt_change(),
                "direction": self.direction, "stale": self.stale,
                "history": [p(x) for x in self.points], "formula": self.formula, "sentence": self.sentence(),
                "note": self.note}


# Figures a question can name, most specific first ("free cash flow margin" before "free cash flow" before
# "cash flow" before "cash"). Each match is removed before the next pattern runs.
QUESTION_PATTERNS: list[tuple[str, str]] = [
    ("fcf_margin", r"free cash ?flow margin|\bfcf margin"),
    ("free_cash_flow", r"free cash ?flow|\bfcf\b"),
    ("operating_cash_flow", r"(operating )?cash ?flows?( from operations)?|\bocf\b|backed by (real |actual )?cash|"
                            r"(turn|convert)\w* (its )?(profits?|earnings) into cash"),
    ("gross_margin", r"gross margins?"),
    ("gross_profit", r"gross profits?"),
    ("operating_margin", r"operating margins?"),
    ("operating_income", r"operating (income|profits?)"),
    ("net_margin", r"net margins?|profit margins?"),
    ("rnd_share", r"(r&d|research)[^.?]{0,30}(share|percent|%|proportion) of (revenue|sales)"),
    ("rnd", r"\br ?& ?d\b|research and development|research spending"),
    ("capex", r"capital (spending|expenditures?|investment)|\bcapex\b"),
    ("shareholder_returns", r"return(s|ing)? (cash|money|capital) to shareholders|shareholder returns"),
    ("net_cash", r"net cash|cash minus debt|cash (versus|vs\.?|compared (with|to)|against) (its )?debt"),
    ("cash", r"\bcash\b"),
    ("long_term_debt", r"long[- ]term debt|\bdebt\b|borrowings?"),
    ("buybacks", r"buy ?-?backs?|repurchas\w*"),
    ("dividends", r"dividends?"),
    ("net_income", r"net income|net profits?|\bprofits?\b|\bearnings\b"),
    ("revenue", r"revenues?|\bsales\b|top[- ]line"),
]


PLURAL = {"buybacks", "dividends", "shareholder_returns"}

# (key, label) for figures read straight from filings, in display order.
FILED: list[tuple[str, str]] = [
    ("revenue", "Revenue"), ("gross_profit", "Gross profit"), ("operating_income", "Operating income"),
    ("net_income", "Net income"), ("operating_cash_flow", "Operating cash flow"), ("capex", "Capital spending"),
    ("rnd", "R&D spending"), ("cash", "Cash and equivalents"), ("long_term_debt", "Long-term debt"),
    ("buybacks", "Share buybacks"), ("dividends", "Dividends paid"),
]


def _series(obs: list[Observation], key: str) -> dict[date, Point]:
    """Fiscal-year points for one filed figure, never mixing accounting definitions within the series."""
    rs: list[PeriodResolution] = consistent_window(annual_series(obs, key), 6)
    return {r.period_end: Point(r.period_end, r.current.value, [r.current.id], r.current.form,
                                r.current.published_at.isoformat() if r.current.published_at else None) for r in rs}


def _combine(a: dict[date, Point], b: dict[date, Point], fn: Callable[[float, float], Optional[float]]) -> list[Point]:
    out: list[Point] = []
    for end in sorted(set(a) & set(b)):
        v = fn(a[end].value, b[end].value)
        if v is not None:
            out.append(Point(end, v, a[end].evidence + b[end].evidence, b[end].form, b[end].filed))
    return out


def compute_key_figures(obs: list[Observation]) -> list[KeyFigure]:
    s = {k: _series(obs, k) for k, _ in FILED}
    ratio = lambda n, d: (n / d) if d else None  # noqa: E731
    out = [KeyFigure(k, label, "usd", [s[k][e] for e in sorted(s[k])]) for k, label in FILED]
    rev = s["revenue"]
    derived = [
        ("gross_margin", "Gross margin", "pct", _combine(s["gross_profit"], rev, ratio), "gross profit / revenue"),
        ("operating_margin", "Operating margin", "pct", _combine(s["operating_income"], rev, ratio), "operating income / revenue"),
        ("net_margin", "Net margin", "pct", _combine(s["net_income"], rev, ratio), "net income / revenue"),
        ("free_cash_flow", "Free cash flow", "usd", _combine(s["operating_cash_flow"], s["capex"], lambda o, c: o - c),
         "operating cash flow minus capital spending"),
        ("rnd_share", "R&D as a share of revenue", "pct", _combine(s["rnd"], rev, ratio), "R&D spending / revenue"),
        ("net_cash", "Cash minus long-term debt", "usd", _combine(s["cash"], s["long_term_debt"], lambda c, d: c - d),
         "cash and equivalents minus long-term debt"),
        ("shareholder_returns", "Buybacks plus dividends", "usd", _combine(s["buybacks"], s["dividends"], lambda a, b: a + b),
         "share buybacks plus dividends paid"),
    ]
    out += [KeyFigure(k, label, unit, pts, formula) for k, label, unit, pts, formula in derived]
    fcf = next(k for k in out if k.key == "free_cash_flow")
    fcf_margin = _combine({p.period_end: p for p in fcf.points}, rev, ratio)
    out.append(KeyFigure("fcf_margin", "Free cash flow margin", "pct", fcf_margin, "free cash flow / revenue"))
    # A figure that stopped being reported years ago (JPMorgan's long-term debt ends in FY2013) is not current.
    current = max((p.period_end.year for k in out if k.key in ("revenue", "net_income") for p in k.points[-1:]), default=None)
    for k in out:
        if current is not None and k.latest and k.latest.period_end.year < current - 1:
            k.stale = True
    return out


FILED_KEYS = {k for k, _ in FILED}


def facts_lines(figures: list[KeyFigure]) -> list[dict[str, str]]:
    """[{"id": "kf-revenue", "text": "Revenue was ..."}]. Filed figures with no data say so, so nobody invents one."""
    return [{"id": f"kf-{k.key}", "text": k.sentence()} for k in figures if k.points or k.key in FILED_KEYS]


def directions(figures: list[KeyFigure]) -> dict[str, str]:
    return {k.key: k.direction for k in figures if k.direction}
