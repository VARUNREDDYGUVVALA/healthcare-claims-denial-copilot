"""Deterministic DuckDB batch generation for the fictional claims lakehouse."""
from dataclasses import dataclass
from datetime import date
from hashlib import file_digest
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import duckdb


@dataclass(frozen=True)
class Preset:
    claims: int
    members: int
    months: int


PRESETS = {
    "small": Preset(1_250, 250, 12),
    "medium": Preset(25_000, 5_000, 24),
    "large": Preset(250_000, 50_000, 36),
    "extra-large": Preset(500_000, 100_000, 36),
}
START = date(2023, 1, 1)
LINES_PER_CLAIM = 4
VERSION = 1
BRONZE = {
    "payers": "payer_id", "plans": "plan_id", "members": "member_id", "providers": "provider_id",
    "eligibility": "member_id", "policies": "policy_id", "claims": "claim_id", "claim_lines": "line_id",
    "authorizations": "line_id", "responses": "line_id", "payments": "line_id", "appeals": "line_id",
}


def materialize(db, name, query, parameters=None):
    db.execute(f"CREATE TABLE {name} AS {query}", parameters or [])


def bronze(db, size, seed):
    db.execute("""
        CREATE TABLE payers AS SELECT * FROM (VALUES
            (1, 'Northstar Health'), (2, 'Juniper Mutual'), (3, 'Fictional Harbor Assurance')
        ) AS v(payer_id, payer_name);
        CREATE TABLE plans AS SELECT payer_id * 10 + band AS plan_id, payer_id,
            'Fictional plan ' || payer_id || '-' || band AS plan_name
        FROM payers CROSS JOIN range(1, 3) b(band);
        CREATE TABLE providers AS SELECT i AS provider_id, 'Fictional provider ' || i AS provider_name
        FROM range(1, 101) t(i);
    """)
    materialize(db, "members", """
        SELECT i AS member_id, 'Fictional member ' || i AS member_name,
               ((i - 1) % 3 + 1) * 10 + ((i - 1) // 3 % 2 + 1) AS plan_id
        FROM range(1, ?) t(i)
    """, [size.members + 1])
    materialize(db, "eligibility", """
        SELECT member_id, plan_id, ?::DATE AS effective_start,
               CASE WHEN member_id % 23 = 0 THEN (?::DATE + (INTERVAL '1 month' * (? // 2)))::DATE
                    ELSE (?::DATE + (INTERVAL '1 month' * ?))::DATE END AS effective_end,
               ?::DATE - 1 AS recorded
        FROM members
    """, [START, START, size.months, START, size.months, START])
    materialize(db, "policies", """
        SELECT plan_id * 100 + version * 10 + procedure_index AS policy_id, plan_id,
               codes.procedure_code, version + 1 AS version,
               (?::DATE + INTERVAL '1 month' * (12 * version))::DATE AS effective_start,
               (?::DATE + INTERVAL '1 month' * least(12 * (version + 1), ?))::DATE AS effective_end,
               'Fictional policy ' || (version + 1) || ' for ' || codes.procedure_code AS section,
               (CASE WHEN codes.procedure_code = 'IMG-01'
                     THEN 'Confirm that imaging authorization is recorded before submission. '
                     ELSE 'Verify coverage on the service date and check for duplicate submissions. '
                END) ||
               CASE version WHEN 0 THEN 'Use the eligibility extract for initial review.'
                            WHEN 1 THEN 'Record the source reference in the review notes.'
                            ELSE 'Escalate conflicting records for manual verification.' END AS excerpt
        FROM plans CROSS JOIN range(?) y(version)
        CROSS JOIN (VALUES (1, 'IMG-01'), (2, 'LAB-02'), (3, 'VIS-03'), (4, 'PT-04')) codes(procedure_index, procedure_code)
    """, [START, START, size.months, (size.months + 11) // 12])
    materialize(db, "claims", """
        WITH dates AS (
            SELECT i AS claim_id, (i - 1) % ? + 1 AS member_id,
                   (hash(i, ?, 'provider') % 100 + 1)::BIGINT AS provider_id,
                   ?::DATE + (((i - 1) * 997 + ?) %
                   date_diff('day', ?::DATE, ?::DATE + INTERVAL '1 month' * ?))::INTEGER AS service_date
            FROM range(1, ?) t(i)
        )
        SELECT claim_id, member_id, plan_id, provider_id, service_date,
               service_date + (1 + hash(claim_id, ?, 'submit') % 14)::INTEGER AS submitted
        FROM dates JOIN members USING (member_id)
    """, [size.members, seed, START, seed, START, START, size.months, size.claims + 1, seed])
    materialize(db, "claim_lines", """
        WITH coded AS (
            SELECT claim_id, slot, (claim_id - 1) * 4 + slot AS line_id,
                   CASE WHEN slot = 4 AND hash(claim_id, ?, 'duplicate') % 50 = 0
                        THEN (claim_id + 3) % 4 ELSE (claim_id + slot) % 4 END AS code
            FROM claims CROSS JOIN range(1, 5) l(slot)
        )
        SELECT line_id, claim_id, slot,
               ['IMG-01', 'LAB-02', 'VIS-03', 'PT-04'][code + 1] AS procedure_code,
               ([125000, 14500, 22000, 9500][code + 1] + 100 * (hash(line_id, ?, 'charge') % 65))::BIGINT AS billed_cents
        FROM coded
    """, [seed, seed])
    materialize(db, "authorizations", """
        SELECT line_id, claim_id, plan_id, procedure_code, service_date - 7 AS recorded,
               service_date - 6 AS effective_start, service_date + 5 AS effective_end
        FROM claim_lines JOIN claims USING (claim_id)
        WHERE procedure_code = 'IMG-01' AND hash(line_id, ?, 'authorization') % 100 < 82
    """, [seed])
    materialize(db, "responses", """
        WITH evidence AS (
            SELECT l.line_id, l.claim_id, c.submitted,
                   CASE WHEN c.service_date >= e.effective_end THEN 'ELIG'
                        WHEN l.slot = 4 AND l.procedure_code = previous.procedure_code THEN 'DUP'
                        WHEN l.procedure_code = 'IMG-01' AND a.line_id IS NULL THEN 'AUTH'
                   END AS reason
            FROM claim_lines l JOIN claims c USING (claim_id)
            JOIN eligibility e USING (member_id)
            LEFT JOIN claim_lines previous ON previous.line_id = l.line_id - 1 AND previous.claim_id = l.claim_id
            LEFT JOIN authorizations a ON a.line_id = l.line_id
        ), classified AS (
            SELECT *, CASE WHEN hash(line_id, ?, 'pending') % 100 < 2 THEN 'pending'
                           WHEN reason IS NOT NULL THEN 'denied' ELSE 'approved' END AS status
            FROM evidence
        )
        SELECT line_id, claim_id, status, CASE WHEN status = 'denied' THEN reason END AS reason,
               CASE WHEN status <> 'pending' THEN submitted + (2 + hash(line_id, ?, 'response') % 45)::INTEGER END AS received
        FROM classified
    """, [seed, seed])
    materialize(db, "payments", """
        SELECT line_id, claim_id, received + 7 AS paid_date, billed_cents * 80 // 100 AS paid_cents
        FROM responses JOIN claim_lines USING (line_id, claim_id) WHERE status = 'approved'
    """)
    materialize(db, "appeals", """
        SELECT line_id, claim_id, received + 5 AS filed_date,
               CASE WHEN hash(line_id, ?, 'appeal-outcome') % 3 = 0 THEN 'resolved' ELSE 'open' END AS status
        FROM responses WHERE status = 'denied' AND hash(line_id, ?, 'appeal') % 10 = 0
    """, [seed, seed])


def curate(db):
    materialize(db, "line_fact", """
        SELECT l.line_id, l.claim_id, c.member_id, c.provider_id, c.plan_id, p.payer_id,
               c.service_date, c.submitted, l.procedure_code, l.billed_cents,
               r.status AS recorded_status, r.reason AS recorded_reason, r.received, pol.policy_id,
               e.recorded < c.submitted AND c.service_date >= e.effective_start AND c.service_date < e.effective_end AS coverage_active,
               a.line_id IS NOT NULL AND a.recorded < c.submitted
                   AND c.service_date >= a.effective_start AND c.service_date < a.effective_end AS authorization_present,
               l.slot = 4 AND l.procedure_code = previous.procedure_code AS duplicate_in_claim,
               coalesce(pay.paid_cents, 0) AS paid_cents, ap.status AS appeal_status
        FROM claim_lines l JOIN claims c USING (claim_id)
        JOIN plans p USING (plan_id)
        JOIN eligibility e USING (member_id)
        JOIN responses r USING (line_id, claim_id)
        LEFT JOIN policies pol ON pol.plan_id = c.plan_id AND pol.procedure_code = l.procedure_code
             AND pol.effective_start <= c.service_date AND c.service_date < pol.effective_end
        LEFT JOIN claim_lines previous ON previous.line_id = l.line_id - 1 AND previous.claim_id = l.claim_id
        LEFT JOIN authorizations a ON a.line_id = l.line_id
        LEFT JOIN payments pay ON pay.line_id = l.line_id
        LEFT JOIN appeals ap ON ap.line_id = l.line_id
    """)
    materialize(db, "monthly_revenue", """
        SELECT date_trunc('month', service_date)::DATE AS service_month, payer_id, procedure_code,
               count(*) AS line_count, count(*) FILTER (WHERE recorded_status = 'denied') AS denied_lines,
               sum(billed_cents)::BIGINT AS billed_cents, sum(paid_cents)::BIGINT AS paid_cents,
               coalesce(sum(billed_cents) FILTER (WHERE recorded_status = 'denied'), 0)::BIGINT AS denied_billed_cents
        FROM line_fact GROUP BY ALL
    """)


def validate(db, size):
    expected = {"members": size.members, "claims": size.claims, "claim_lines": size.claims * LINES_PER_CLAIM}
    counts = {table: db.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
              for table in (*BRONZE, "line_fact", "monthly_revenue")}
    checks = {
        "exact_preset_counts": all(counts[key] == value for key, value in expected.items()),
        "four_lines_per_claim": not db.execute(
            "SELECT claim_id FROM claim_lines GROUP BY claim_id HAVING count(*) <> 4 LIMIT 1"
        ).fetchone(),
        "unique_line_ids": db.execute("SELECT count(DISTINCT line_id) FROM line_fact").fetchone()[0] == expected["claim_lines"],
        "no_missing_policy": not db.execute("SELECT 1 FROM line_fact WHERE policy_id IS NULL LIMIT 1").fetchone(),
        "response_completeness": counts["responses"] == expected["claim_lines"] == counts["line_fact"],
        "reference_integrity": not db.execute("""
            SELECT 1 FROM claims ANTI JOIN providers USING (provider_id)
            UNION ALL SELECT 1 FROM plans ANTI JOIN payers USING (payer_id)
            UNION ALL SELECT 1 FROM members ANTI JOIN plans USING (plan_id)
            UNION ALL SELECT 1 FROM line_fact ANTI JOIN claim_lines USING (line_id, claim_id)
            LIMIT 1
        """).fetchone(),
        "event_chronology": not db.execute("""
            SELECT 1 FROM payments p JOIN responses r USING (line_id, claim_id)
            WHERE r.received IS NULL OR p.paid_date < r.received
            UNION ALL
            SELECT 1 FROM appeals a JOIN responses r USING (line_id, claim_id)
            WHERE r.received IS NULL OR a.filed_date < r.received
            LIMIT 1
        """).fetchone(),
        "time_and_currency_rules": not db.execute("""
            SELECT 1 FROM line_fact WHERE submitted <= service_date OR received < submitted
            OR (received IS NULL) <> (recorded_status = 'pending')
            OR (recorded_reason IS NULL) <> (recorded_status <> 'denied')
            OR paid_cents < 0 OR paid_cents > billed_cents
            OR (recorded_status <> 'approved' AND paid_cents <> 0)
            OR (appeal_status IS NOT NULL AND recorded_status <> 'denied')
            LIMIT 1
        """).fetchone(),
        "month_coverage": db.execute("SELECT count(DISTINCT service_month) FROM monthly_revenue").fetchone()[0] == size.months,
        "gold_reconciliation": db.execute("SELECT sum(line_count), sum(billed_cents), sum(paid_cents) FROM monthly_revenue").fetchone() ==
                               db.execute("SELECT count(*), sum(billed_cents), sum(paid_cents) FROM line_fact").fetchone(),
    }
    failed = [name for name, ok in checks.items() if not ok]
    if failed:
        raise ValueError("Lakehouse validation failed: " + ", ".join(failed))
    return counts, checks


def sha(path):
    with path.open("rb") as stream:
        return file_digest(stream, "sha256").hexdigest()


def build_lakehouse(preset, seed, output):
    """Publish an immutable snapshot only after validation; verify exact reruns."""
    size = PRESETS[preset]
    if not 0 <= seed <= 2_147_483_647:
        raise ValueError("Seed must be between 0 and 2147483647.")
    output = Path(output).absolute()
    key = {"schema_version": VERSION, "preset": preset, "seed": seed, "duckdb": duckdb.__version__}
    if output.exists():
        manifest_path = output / "manifest.json"
        if not manifest_path.is_file():
            raise FileExistsError(f"Output exists without a manifest: {output}")
        previous = json.loads(manifest_path.read_text())
        expected_files = {f"bronze/{name}.parquet" for name in BRONZE} | {
            "silver/line_fact.parquet", "gold/monthly_revenue.parquet"
        }
        if previous.get("identity") != key or set(previous.get("files", {})) != expected_files:
            raise FileExistsError(f"Output contains a different snapshot: {output}")
        if not all((output / file).is_file() and sha(output / file) == checksum
                   for file, checksum in previous["files"].items()):
            raise ValueError(f"Snapshot checksum mismatch: {output}")
        return previous

    output.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".claims-build-", dir=output.parent) as temp:
        root = Path(temp)
        staging = root / "snapshot"
        with duckdb.connect(config={"threads": "2", "memory_limit": "512MB", "temp_directory": str(root / "spill")}) as db:
            bronze(db, size, seed)
            curate(db)
            counts, checks = validate(db, size)
            files = {}
            for layer, tables in (("bronze", BRONZE), ("silver", {"line_fact": "line_id"}),
                                  ("gold", {"monthly_revenue": "service_month, payer_id, procedure_code"})):
                (staging / layer).mkdir(parents=True)
                for table, order in tables.items():
                    relative = f"{layer}/{table}.parquet"
                    db.execute(f"COPY (SELECT * FROM {table} ORDER BY {order}) TO ? (FORMAT PARQUET, COMPRESSION ZSTD)",
                               [str(staging / relative)])
                    files[relative] = sha(staging / relative)
        end = date(START.year + size.months // 12, 1, 1)
        manifest = {
            "identity": key, "service_start": START.isoformat(), "service_end_exclusive": end.isoformat(),
            "service_months": size.months, "counts": counts, "checks": checks, "files": files,
        }
        (staging / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        staging.rename(output)
    return manifest
