"""Export the large queue as compressed static pages by fictional feed and service year."""
import argparse
import gzip
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import duckdb

from data_engineering.transformations.source_feeds import FEEDS, FEED_SQL
from data_engineering.transformations.synthetic_lakehouse import build_lakehouse

CHUNK_SIZE = 1000


def export(output):
    output = Path(output)
    if output.exists():
        raise FileExistsError(f"Choose a fresh archive directory: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    snapshot = Path("artifacts/lakehouse/extra-large-seed-43").resolve()
    manifest = build_lakehouse("extra-large", 43, snapshot)
    with TemporaryDirectory(prefix=".queue-build-", dir=output.parent) as temp:
        staging = Path(temp) / "archive"
        data = write_archive(staging, snapshot, manifest)
        staging.rename(output)
    return data


def write_archive(output, snapshot, manifest):
    with duckdb.connect(config={"threads": "1", "memory_limit": "512MB"}) as db:
        db.read_parquet(str(snapshot / "silver/line_fact.parquet")).create_view("claims")
        db.read_parquet(str(snapshot / "bronze/payers.parquet")).create_view("payers")
        db.execute(f"""
            CREATE VIEW browse AS SELECT {FEED_SQL} AS feed, year(service_date) AS service_year,
                line_id, claim_id, service_date, payer_id, procedure_code, recorded_status,
                coalesce(recorded_reason, '-') AS reason,
                (CASE WHEN NOT coverage_active THEN 4 ELSE 0 END +
                 CASE WHEN duplicate_in_claim THEN 2 ELSE 0 END +
                 CASE WHEN procedure_code = 'IMG-01' AND NOT authorization_present THEN 1 ELSE 0 END) AS priority
            FROM claims
        """)
        groups = db.execute("""
            SELECT feed, service_year, count(*) FROM browse GROUP BY 1, 2 ORDER BY 1, 2
        """).fetchall()
        payers = db.execute("SELECT payer_id, payer_name FROM payers ORDER BY 1").fetchall()
        db.execute(f"""
            COPY (
                SELECT *, ((row_number() OVER (
                    PARTITION BY feed, service_year ORDER BY priority DESC, line_id
                ) - 1) // {CHUNK_SIZE}) AS chunk
                FROM browse ORDER BY feed, service_year, chunk, priority DESC, line_id
            ) TO ? (FORMAT CSV, DELIMITER '\t', HEADER FALSE, COMPRESSION GZIP,
                    PARTITION_BY (feed, service_year, chunk), FILENAME_PATTERN 'rows_{{i}}')
        """, [str(output)])
    catalog = []
    for feed, year, count in groups:
        catalog.append({"feed": feed, "year": year, "lines": count})
        group = output / f"feed={feed}" / f"service_year={year}"
        for index, offset in enumerate(range(0, count, CHUNK_SIZE)):
            files = list((group / f"chunk={index}").glob("*.gz"))
            if len(files) != 1 or files[0].name != "rows_0.csv.gz":
                raise ValueError(f"Unexpected partition files: {group}, chunk {index}")
            with gzip.open(files[0], "rt") as rows:
                if sum(1 for _ in rows) != min(CHUNK_SIZE, count - offset):
                    raise ValueError(f"Partition row count mismatch: {group}, chunk {index}")
    if len(FEEDS) * manifest["service_months"] // 12 != len(catalog) or sum(item["lines"] for item in catalog) != manifest["counts"]["claim_lines"]:
        raise ValueError("Published archive counts do not reconcile.")
    data = {
        "lines": manifest["counts"]["claim_lines"], "claims": manifest["counts"]["claims"],
        "start": manifest["service_start"], "end_exclusive": manifest["service_end_exclusive"],
        "chunk_size": CHUNK_SIZE, "feeds": FEEDS, "payers": dict(payers), "groups": catalog,
    }
    (output / "index.json").write_text(json.dumps(data, indent=2) + "\n")
    return data


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("apps/frontend/public/claims-archive"))
    print(json.dumps(export(parser.parse_args().output), indent=2))


if __name__ == "__main__":
    main()
