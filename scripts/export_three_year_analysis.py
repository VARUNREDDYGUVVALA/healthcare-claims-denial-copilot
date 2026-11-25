"""Export claim IDs, claim-line IDs, and 36 months of synthetic denial analysis."""
import argparse
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZIP_DEFLATED, ZipFile

import duckdb

from data_engineering.transformations.synthetic_lakehouse import PRESETS, build_lakehouse


METRICS = """
    count(DISTINCT claim_id) AS claims,
    count(DISTINCT member_id) AS distinct_members,
    count(*) AS claim_lines,
    count(*) FILTER (WHERE recorded_status = 'approved') AS approved_lines,
    count(*) FILTER (WHERE recorded_status = 'denied') AS denied_lines,
    count(*) FILTER (WHERE recorded_status = 'pending') AS pending_lines,
    round(100.0 * count(*) FILTER (WHERE recorded_status = 'denied')
          / nullif(count(*) FILTER (WHERE recorded_status IN ('approved', 'denied')), 0), 2)
        AS denial_pct_of_finalized,
    sum(billed_cents)::BIGINT AS billed_cents,
    sum(paid_cents)::BIGINT AS paid_cents
"""

EXPORTS = {
    "claims": """
        SELECT 'CLM-' || lpad(claim_id::VARCHAR, 6, '0') AS claim_id,
               member_id, provider_id, plan_id, payer_id, service_date, submitted,
               count(*) AS line_count,
               count(*) FILTER (WHERE recorded_status = 'approved') AS approved_lines,
               count(*) FILTER (WHERE recorded_status = 'denied') AS denied_lines,
               count(*) FILTER (WHERE recorded_status = 'pending') AS pending_lines,
               sum(billed_cents)::BIGINT AS billed_cents, sum(paid_cents)::BIGINT AS paid_cents
        FROM source GROUP BY claim_id, member_id, provider_id, plan_id, payer_id, service_date, submitted
        ORDER BY service_date, claim_id
    """,
    "claim_lines": """
        SELECT 'LINE-' || lpad(line_id::VARCHAR, 7, '0') AS line_id,
               'CLM-' || lpad(claim_id::VARCHAR, 6, '0') AS claim_id,
               member_id, provider_id, plan_id, payer_id, service_date, submitted,
               procedure_code, billed_cents, recorded_status, recorded_reason, received,
               policy_id, coverage_active, authorization_present, duplicate_in_claim,
               paid_cents, appeal_status
        FROM source ORDER BY service_date, line_id
    """,
    "annual_summary": f"""
        SELECT year(service_date) AS service_year, {METRICS}
        FROM source GROUP BY 1 ORDER BY 1
    """,
    "monthly_summary": f"""
        SELECT date_trunc('month', service_date)::DATE AS service_month, {METRICS}
        FROM source GROUP BY 1 ORDER BY 1
    """,
    "payer_year_summary": f"""
        SELECT year(service_date) AS service_year, payer_id, payer_name, {METRICS}
        FROM source LEFT JOIN payers USING (payer_id) GROUP BY 1, 2, 3 ORDER BY 1, 2
    """,
    "annual_denial_reasons": """
        SELECT year(service_date) AS service_year, recorded_reason AS reason_code,
               count(*) AS denied_lines, sum(billed_cents)::BIGINT AS denied_billed_cents
        FROM source WHERE recorded_status = 'denied' GROUP BY 1, 2 ORDER BY 1, 2
    """,
}

DATA_GUIDE = """Synthetic Claims Denial Analysis
Source: validated {preset} lakehouse, seed 43. All records are fictional.

claims.csv contains one row per claim ID. claim_lines.{detail_format} contains four rows
per claim and one row per line ID. Join on claim_id. CLM- and LINE- IDs are
zero-padded renderings of the lakehouse's numeric IDs. The yearly, monthly,
and payer summaries are grouped by service date. January 2023 through
December 2025 are included. Later response or payment dates can appear
because those events follow service. Yearly member counts are non-additive
because the same members can appear in multiple years.

Denial rate is denied lines divided by approved plus denied lines. Pending
lines are shown separately and excluded from the denominator. Money fields
are integer cents, and the paid amounts are simulated. AUTH is authorization,
ELIG is eligibility, and DUP is duplicate. Read the Parquet manifest for
dataset lineage and integrity checks. The reports describe synthetic rules.
"""


def export(output, preset="large", detail_format="csv", summary_output=None):
    size = PRESETS[preset]
    snapshot = (Path("artifacts/lakehouse") / f"{preset}-seed-43").resolve()
    manifest = build_lakehouse(preset, 43, snapshot)
    output = Path(output).absolute()
    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".claims-analysis-", dir=output.parent) as work:
        folder = Path(work)
        with duckdb.connect(config={"threads": "2", "memory_limit": "512MB", "temp_directory": str(folder / "spill")}) as db:
            for table, path in (("source", snapshot / "silver/line_fact.parquet"),
                                ("payers", snapshot / "bronze/payers.parquet")):
                db.read_parquet(str(path)).create_view(table)
            lines, claims, members, months = db.execute("""
                SELECT count(*), count(DISTINCT claim_id), count(DISTINCT member_id),
                       count(DISTINCT date_trunc('month', service_date)) FROM source
            """).fetchone()
            if (lines, claims, members, months) != (size.claims * 4, size.claims, size.members, 36):
                raise ValueError("The source does not reconcile to the expected three-year snapshot.")
            if summary_output:
                summary = {"preset": preset, "claims": claims, "claim_lines": lines,
                           "members": members, "months": months,
                           "start": manifest["service_start"], "end_exclusive": manifest["service_end_exclusive"]}
                for table in ("annual_summary", "monthly_summary", "annual_denial_reasons"):
                    result = db.execute(EXPORTS[table])
                    columns = [column[0] for column in result.description]
                    summary[table] = [dict(zip(columns, row, strict=True)) for row in result.fetchall()]
            for name, query in EXPORTS.items():
                parquet = detail_format == "parquet" and name == "claim_lines"
                extension = "parquet" if parquet else "csv"
                options = "FORMAT PARQUET, COMPRESSION ZSTD" if parquet else "FORMAT CSV, HEADER TRUE"
                db.execute(f"COPY ({query}) TO ? ({options})", [str(folder / f"{name}.{extension}")])
        archive = folder / "analysis.zip"
        with ZipFile(archive, "w", compression=ZIP_DEFLATED, compresslevel=6) as bundle:
            for file in sorted([*folder.glob("*.csv"), *folder.glob("*.parquet")]):
                bundle.write(file, file.name)
            bundle.writestr("README.txt", DATA_GUIDE.format(preset=preset, detail_format=detail_format))
            bundle.writestr("manifest.json", json.dumps(manifest, indent=2) + "\n")
        archive.replace(output)
    if summary_output:
        Path(summary_output).write_text(json.dumps(summary, default=str, indent=2) + "\n")
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--preset", choices=("large", "extra-large"), default="large")
    parser.add_argument("--detail-format", choices=("csv", "parquet"), default="csv")
    parser.add_argument("--summary-output", type=Path)
    args = parser.parse_args()
    output = args.output or Path("artifacts") / f"claims-2023-2025-{args.preset}.zip"
    print(export(output, args.preset, args.detail_format, args.summary_output))


if __name__ == "__main__":
    main()
