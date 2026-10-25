"""Render the Zetaris Lightning SQL that federates SEC EDGAR into FinSight.

The statement shapes copy Zetaris's verified recipe
(getting-started/open_data/rest_apis/sql/rate_limited/01_edgar_company_facts_create.sql):

  CREATE LIGHTNING DATABASE <db> DESCRIBE BY "...";
  CREATE SCHEMASTORE CONTAINER <container>;
  CREATE LIGHTNING REST TABLE <t> FROM <db> REQUEST(endpoint "...", method "get",
      response_type "json", http_encoding "URLENCODED") HEADER (user-agent "...") BODY ();
  CREATE SCHEMASTORE VIEW <v> WITH CONTAINER <container> AS
      SELECT ... FROM <db>.<t> LATERAL VIEW explode(units.USD) AS fact;

Difference from the recipe: instant (balance-sheet) concepts have no `start` field in SEC's
JSON, so their views select NULL for period_start instead of fact.`start`.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.financial_data.companies import Company, MetricDef
from app.financial_data.normalize import concept_api_url

TAG_SLUGS = {
    "RevenueFromContractWithCustomerExcludingAssessedTax": "rev_asc606",
    "Revenues": "revenues",
    "SalesRevenueNet": "sales_revenue_net",
    "NetIncomeLoss": "net_income",
    "NetCashProvidedByUsedInOperatingActivities": "ocf",
    "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations": "ocf_cont",
    "LongTermDebtNoncurrent": "ltd_noncurrent",
    "LongTermDebt": "ltd",
    "AssetsCurrent": "assets_current",
    "LiabilitiesCurrent": "liabilities_current",
}

VIEW_COLUMNS = [
    "cik",
    "entity_name",
    "concept",
    "period_start",
    "period_end",
    "value_usd",
    "accession_number",
    "fiscal_year",
    "fiscal_period",
    "period_frame",
    "form_type",
    "filed_date",
]


@dataclass(frozen=True)
class ViewSpec:
    company: Company
    metric: MetricDef
    tag: str

    @property
    def rest_table(self) -> str:
        return f"{self.company.table_prefix}_{TAG_SLUGS[self.tag]}_facts"

    @property
    def view(self) -> str:
        return f"{self.company.table_prefix}_{TAG_SLUGS[self.tag]}"


def _quote(value: str) -> str:
    if '"' in value or "\n" in value:
        raise ValueError("Values embedded in Lightning SQL must not contain quotes or newlines.")
    return f'"{value}"'


def database_sql(db: str) -> str:
    # Zetaris accepts only letters, digits, spaces and _ . - , in a description (no colon).
    return f'CREATE LIGHTNING DATABASE {db} DESCRIBE BY "FinSight AI SEC EDGAR XBRL companyconcept REST source"'


def container_sql(container: str) -> str:
    return f"CREATE SCHEMASTORE CONTAINER {container}"


def rest_table_sql(spec: ViewSpec, db: str, user_agent: str) -> str:
    endpoint = concept_api_url(spec.company.cik, spec.tag)
    return (
        f"CREATE LIGHTNING REST TABLE {spec.rest_table} FROM {db} REQUEST(\n"
        f"    endpoint {_quote(endpoint)},\n"
        f'    method "get",\n'
        f'    response_type "json",\n'
        f'    http_encoding "URLENCODED"\n'
        f") HEADER (\n"
        f"    user-agent {_quote(user_agent)}\n"
        f") BODY ()"
    )


def view_sql(spec: ViewSpec, db: str, container: str) -> str:
    start_expr = "fact.`start`" if spec.metric.kind == "duration" else "CAST(NULL AS STRING)"
    return (
        f"CREATE SCHEMASTORE VIEW {spec.view} WITH CONTAINER {container} AS\n"
        f"SELECT\n"
        f"    cik,\n"
        f"    `entityName` AS entity_name,\n"
        f"    tag AS concept,\n"
        f"    {start_expr} AS period_start,\n"
        f"    fact.`end` AS period_end,\n"
        f"    fact.val AS value_usd,\n"
        f"    fact.accn AS accession_number,\n"
        f"    fact.fy AS fiscal_year,\n"
        f"    fact.fp AS fiscal_period,\n"
        f"    fact.frame AS period_frame,\n"
        f"    fact.form AS form_type,\n"
        f"    fact.filed AS filed_date\n"
        f"FROM {db.lower()}.{spec.rest_table}\n"
        f"LATERAL VIEW explode(units.USD) AS fact"
    )


def select_sql(spec: ViewSpec, container: str) -> str:
    cols = ", ".join(VIEW_COLUMNS)
    return f"SELECT {cols} FROM {container}.{spec.view}"
