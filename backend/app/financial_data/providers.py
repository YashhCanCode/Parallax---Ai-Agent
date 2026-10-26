"""Data providers. Each returns normalized observations plus a receipt for every real call.

- SampleProvider:    offline fixtures in sample_data/ (fictional companies, labeled `sample`).
- SecDirectProvider: the public SEC EDGAR companyconcept API (labeled `live` or `cached`).
- ZetarisProvider:   the same SEC concepts federated through the user's Zetaris instance via
                     Lightning REST tables + schemastore views (labeled `live`).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Optional

from app.config import REPO_ROOT, Settings
from app.financial_data.companies import METRIC_BY_KEY, METRICS, Company, MetricDef
from app.financial_data.normalize import classify_period, normalize_facts, obs_id
from app.financial_data.sec_client import SecClient, SecError
from app.integrations.zetaris.client import ZetarisClient, ZetarisError
from app.integrations.zetaris.sql import ViewSpec, select_sql
from app.models.schemas import DataStatus, Observation, QueryReceipt

ZETARIS_MANIFEST = REPO_ROOT / "zetaris" / "registered_views.json"


@dataclass
class FetchResult:
    observations: list[Observation] = field(default_factory=list)
    receipts: list[QueryReceipt] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    events: list[str] = field(default_factory=list)
    channel: str = ""
    # (metric, tag) -> number of raw facts returned, used for the Zetaris vs SEC cross-check
    raw_counts: dict[tuple[str, str], int] = field(default_factory=dict)


def _now() -> datetime:
    return datetime.now(timezone.utc)


class SampleProvider:
    channel = "sample"

    def __init__(self, settings: Settings, apply_amendment: Optional[bool] = None):
        self.path = settings.sample_dir / "sample_companies.json"
        # None = read the persisted flag (set by "Publish fictional amended filing" in the Watchlist).
        self.apply_amendment = apply_amendment

    def _amendment_applied(self) -> bool:
        if self.apply_amendment is not None:
            return self.apply_amendment
        from app.db import get_state  # local import: the DB is only needed when the flag is not given

        return get_state("sample_amendment_applied") == "true"

    async def fetch(self, company: Company, metrics: list[MetricDef]) -> FetchResult:
        started = _now()
        data = json.loads(self.path.read_text())
        entry = data["companies"].get(company.ticker)
        amendment = data.get("amendments", {}).get(company.ticker)
        if entry is not None and amendment and self._amendment_applied():
            entry = json.loads(json.dumps(entry))
            for mkey, groups in amendment["filings"].items():
                existing = entry["filings"].setdefault(mkey, [])
                for g in groups:
                    target = next((x for x in existing if x["tag"] == g["tag"]), None)
                    if target is None:
                        existing.append(json.loads(json.dumps(g)))
                    else:
                        target["facts"] = target["facts"] + g["facts"]
        result = FetchResult(channel=self.channel)
        result.receipts.append(
            QueryReceipt(channel="sample", target=str(self.path.relative_to(REPO_ROOT)), started_at=started,
                         duration_ms=0, ok=entry is not None, rows=None)
        )
        if entry is None:
            result.limitations.append(f"No sample fixture exists for {company.ticker}.")
            return result
        retrieved = _now()
        for metric in metrics:
            groups = entry["filings"].get(metric.key, [])
            if not groups:
                result.limitations.append(f"Sample data has no {metric.label.lower()} facts for {company.ticker}.")
            for g in groups:
                obs = normalize_facts(
                    g["facts"], company=company, metric=metric, tag=g["tag"], unit="USD",
                    channel=self.channel, status=DataStatus.sample, retrieved_at=retrieved,
                    source_name_prefix="SAMPLE filing",
                )
                result.observations.extend(obs)
                result.raw_counts[(metric.key, g["tag"])] = len(g["facts"])
        for s in entry.get("secondary_sources", []):
            metric = METRIC_BY_KEY.get(s["metric"])
            if metric is None or metric not in metrics:
                continue
            start = date.fromisoformat(s["start"]) if s.get("start") else None
            end = date.fromisoformat(s["end"])
            scaled = float(s["value"]) * float(s.get("unit_scale", 1))
            result.observations.append(
                Observation(
                    id=obs_id(company.ticker, "secondary", s["source_name"], s["metric"], s.get("start"), s["end"]),
                    company=company.name,
                    ticker=company.ticker,
                    metric=metric.key,
                    concept=f"secondary:{s.get('definition', '')}",
                    value=scaled,
                    currency_or_unit="USD",
                    period_start=start,
                    period_end=end,
                    period_type=classify_period(start, end),  # type: ignore[arg-type]
                    fiscal_year=end.year,
                    form="secondary",
                    reporting_basis=s.get("reporting_basis", "consolidated"),
                    source_name=s["source_name"],
                    source_url=s.get("source_url"),
                    published_at=date.fromisoformat(s["published_at"]) if s.get("published_at") else None,
                    retrieved_at=retrieved,
                    data_status=DataStatus.sample,
                    retrieval_channel=self.channel,
                    extraction_notes=(
                        f"reported as {s['value']:,} {s.get('unit_label', 'USD')}; "
                        f"scaled x{float(s.get('unit_scale', 1)):,.0f} to USD; definition: {s.get('definition', 'n/a')}"
                    ),
                )
            )
        result.events.append(f"Loaded {len(result.observations)} sample observations for {company.ticker}.")
        return result


class SecDirectProvider:
    channel = "sec_direct"

    def __init__(self, settings: Settings):
        self.client = SecClient(settings.sec_user_agent, settings.cache_dir)

    async def fetch(self, company: Company, metrics: list[MetricDef],
                    only_tags: Optional[set[str]] = None) -> FetchResult:
        result = FetchResult(channel=self.channel)
        for metric in metrics:
            found_any = False
            for tag in metric.tags:
                if only_tags is not None and tag not in only_tags:
                    continue
                started = _now()
                try:
                    resp = await self.client.concept_rows(company.cik, tag)
                except SecError as exc:
                    result.receipts.append(QueryReceipt(channel="sec_direct", target=f"{company.cik}/{tag}",
                                                        started_at=started, duration_ms=0, ok=False, error=str(exc)))
                    result.limitations.append(f"SEC request failed for {tag}: {exc}")
                    continue
                status = resp["status"]
                if status == "missing":
                    result.receipts.append(QueryReceipt(channel="sec_direct", target=resp["url"], started_at=started,
                                                        duration_ms=resp.get("duration_ms", 0), ok=True, rows=0,
                                                        error="404: company does not report this concept"))
                    continue
                facts = resp["rows"]
                note = None if status == "live" else "served from local cache"
                if resp.get("fallback") == "companyfacts":
                    note = (f"companyconcept returned no rows for {tag}; used SEC companyfacts"
                            + (" (cached)" if status == "cached" else ""))
                result.receipts.append(QueryReceipt(channel="sec_direct", target=resp["url"], started_at=started,
                                                    duration_ms=resp.get("duration_ms", 0), ok=True, rows=len(facts),
                                                    error=note))
                result.raw_counts[(metric.key, tag)] = len(facts)
                obs = normalize_facts(
                    facts, company=company, metric=metric, tag=tag, unit="USD", channel=self.channel,
                    status=DataStatus.live if status == "live" else DataStatus.cached,
                    retrieved_at=datetime.fromisoformat(resp["retrieved_at"]),
                )
                if resp.get("fallback") == "companyfacts":
                    for o in obs:
                        o.extraction_notes += "; from SEC companyfacts (the companyconcept endpoint returned no rows)"
                if obs:
                    found_any = True
                result.observations.extend(obs)
            if not found_any and only_tags is None:
                result.limitations.append(
                    f"{company.name} reports none of the tags {', '.join(metric.tags)} for {metric.label.lower()}."
                )
        result.events.append(
            f"SEC EDGAR returned {len(result.observations)} observations across {len(result.receipts)} requests."
        )
        return result


def load_zetaris_manifest(path: Path = ZETARIS_MANIFEST) -> dict[str, Any]:
    if not path.exists():
        return {"views": []}
    return json.loads(path.read_text())


class ZetarisProvider:
    channel = "zetaris"

    def __init__(self, settings: Settings, client: ZetarisClient | None = None, manifest: dict[str, Any] | None = None,
                 auto_register: Optional[bool] = None):
        self.s = settings
        self.client = client or ZetarisClient(settings)
        # A manifest passed in (tests) is never written back to disk.
        self.persist = manifest is None
        self.manifest = manifest if manifest is not None else load_zetaris_manifest()
        self.auto_register = settings.zetaris_auto_register if auto_register is None else auto_register

    def registered_specs(self, company: Company, metric: MetricDef) -> list[ViewSpec]:
        names = {(v["ticker"], v["metric"], v["tag"]) for v in self.manifest.get("views", [])}
        return [ViewSpec(company, metric, tag) for tag in metric.tags if (company.ticker, metric.key, tag) in names]

    def _known(self, company: Company) -> bool:
        """True if this company was registered or probed before (views or recorded no-data concepts)."""
        return any(v["ticker"] == company.ticker
                   for k in ("views", "no_data", "rejected", "concept_api_empty") for v in self.manifest.get(k, []))

    def _unseen(self, company: Company, metrics: list[MetricDef]) -> list[MetricDef]:
        """Figures none of whose tags were ever registered or probed for this company (e.g. figures added later)."""
        seen = {v["tag"] for k in ("views", "no_data", "rejected", "concept_api_empty")
                for v in self.manifest.get(k, []) if v["ticker"] == company.ticker}
        return [m for m in metrics if not any(t in seen for t in m.tags)]

    def _api_empty_tags(self, company: Company) -> set[str]:
        return {v["tag"] for v in self.manifest.get("concept_api_empty", []) if v["ticker"] == company.ticker}

    async def fetch(self, company: Company, metrics: list[MetricDef]) -> FetchResult:
        from app.integrations.zetaris.registry import register_company, save_merged

        self.client.ensure_configured()
        result = FetchResult(channel=self.channel)
        container = self.manifest.get("container", self.s.zetaris_container)
        pending: dict[str, int] = {}
        no_data_now: list[dict[str, Any]] = []
        api_empty_now: list[dict[str, Any]] = []
        probed: list[tuple[str, str]] = []
        new_figures = self._unseen(company, metrics) if self._known(company) else []
        if self.auto_register and (not self._known(company) or new_figures):
            # A company seen before only gets views for the figures it is missing.
            reg = await register_company(company, self.s, self.client, metrics=new_figures or None)
            probed = reg.probed
            result.receipts += reg.receipts
            result.events += reg.events
            result.limitations += [f"Zetaris registration problem: {e}" for e in reg.errors]
            pending, no_data_now, api_empty_now = reg.pending, reg.no_data, reg.api_empty
            self.manifest = {**self.manifest, "no_data": self.manifest.get("no_data", []) + no_data_now,
                             "concept_api_empty": self.manifest.get("concept_api_empty", []) + api_empty_now}
        verified: list[dict[str, Any]] = []
        rejected: list[dict[str, Any]] = []
        api_empty = self._api_empty_tags(company)
        unregistered: list[MetricDef] = []
        for metric in metrics:
            specs = self.registered_specs(company, metric) + [ViewSpec(company, metric, t) for t in metric.tags if t in pending]
            if not specs and any(t in api_empty for t in metric.tags):
                continue  # fetched directly from SEC below
            if not specs:
                no_data = {(v["ticker"], v["tag"]) for v in self.manifest.get("no_data", [])}
                if all((company.ticker, t) in no_data for t in metric.tags):
                    result.limitations.append(
                        f"{company.name} reports none of the tags {', '.join(metric.tags)} for "
                        f"{metric.label.lower()} (checked against SEC during Zetaris setup)."
                    )
                else:
                    unregistered.append(metric)
                continue
            for spec in specs:
                sql = select_sql(spec, container)
                started = _now()
                try:
                    q = await self.client.run_query(sql)
                except ZetarisError as exc:
                    result.receipts.append(QueryReceipt(channel="zetaris", target=sql, started_at=started,
                                                        duration_ms=0, ok=False, error=str(exc)))
                    result.limitations.append(f"Zetaris query for {spec.view} failed: {exc}")
                    continue
                result.receipts.append(QueryReceipt(channel="zetaris", target=sql, started_at=started,
                                                    duration_ms=q.duration_ms, ok=True, rows=len(q.rows),
                                                    request_id=q.request_id))
                if spec.tag in pending:
                    entry = {"ticker": company.ticker, "metric": metric.key, "tag": spec.tag, "view": spec.view,
                             "zetaris_rows": len(q.rows), "sec_rows": pending[spec.tag]}
                    if len(q.rows) != pending[spec.tag]:
                        rejected.append({**entry, "match": False})
                        result.limitations.append(
                            f"New Zetaris view {spec.view} returned {len(q.rows)} rows but SEC has {pending[spec.tag]}; "
                            f"its data was not used.")
                        continue
                    verified.append(entry)
                result.raw_counts[(metric.key, spec.tag)] = len(q.rows)
                obs = normalize_facts(
                    q.rows, company=company, metric=metric, tag=spec.tag, unit="USD", channel=self.channel,
                    status=DataStatus.live, retrieved_at=_now(), source_name_prefix="SEC EDGAR via Zetaris",
                )
                for o in obs:
                    o.extraction_notes += f"; Zetaris view {container}.{spec.view}, request {q.request_id}"
                result.observations.extend(obs)
        # Concepts whose SEC companyconcept endpoint returns no rows (so a Zetaris REST table on it would be
        # empty) are fetched directly from SEC companyfacts and labeled as not coming through Zetaris.
        direct_metrics = [m for m in metrics if any(t in api_empty and t not in pending for t in m.tags)]
        if direct_metrics:
            direct = await SecDirectProvider(self.s).fetch(company, direct_metrics, only_tags=api_empty)
            result.observations += direct.observations
            result.receipts += direct.receipts
            result.raw_counts.update(direct.raw_counts)
            result.limitations.append(
                f"Not via Zetaris: {', '.join(m.label.lower() for m in direct_metrics)} for {company.ticker} came directly "
                f"from SEC companyfacts, because SEC's per-concept endpoint (which the Zetaris REST tables read) "
                f"currently returns no rows for them.")
        if unregistered:
            # No Zetaris view yet (registration off or failed): use SEC directly and say so, rather than drop the figure.
            direct = await SecDirectProvider(self.s).fetch(company, unregistered)
            result.observations += direct.observations
            result.receipts += direct.receipts
            result.raw_counts.update(direct.raw_counts)
            result.limitations.append(
                f"Not via Zetaris: {', '.join(m.label.lower() for m in unregistered)} for {company.ticker} came directly "
                f"from SEC, because no Zetaris view is registered for them yet (run scripts/zetaris_setup.py, or keep "
                f"ZETARIS_AUTO_REGISTER on).")
        if pending or no_data_now or api_empty_now:
            result.events.append(f"Verified {len(verified)} new Zetaris view(s) against SEC row counts"
                                 + (f"; {len(rejected)} rejected." if rejected else "."))
            if self.persist:
                self.manifest = await save_merged(
                    self.s, probed=probed or [(company.ticker, t) for m in METRICS for t in m.tags],
                    verified=verified, rejected=rejected, no_data=no_data_now, api_empty=api_empty_now)
        result.events.append(
            f"Zetaris returned {len(result.observations)} observations across "
            f"{sum(1 for r in result.receipts if r.ok and r.target.startswith('SELECT'))} successful queries."
        )
        return result
