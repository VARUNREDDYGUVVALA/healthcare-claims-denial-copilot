"""Generate and ingest fictional billing extracts."""
from datetime import date, timedelta
import random

import duckdb

TABLES = {
    "claims": "id VARCHAR PRIMARY KEY, member VARCHAR NOT NULL, payer VARCHAR NOT NULL, submitted DATE NOT NULL",
    "lines": "id VARCHAR PRIMARY KEY, claim_id VARCHAR NOT NULL, procedure VARCHAR NOT NULL, service DATE NOT NULL, amount INTEGER NOT NULL",
    "eligibility": "id VARCHAR PRIMARY KEY, member VARCHAR NOT NULL, payer VARCHAR NOT NULL, starts DATE NOT NULL, ends DATE NOT NULL, recorded DATE NOT NULL",
    "authorizations": "id VARCHAR PRIMARY KEY, member VARCHAR NOT NULL, payer VARCHAR NOT NULL, procedure VARCHAR NOT NULL, starts DATE NOT NULL, ends DATE NOT NULL, recorded DATE NOT NULL",
    "responses": "id VARCHAR PRIMARY KEY, line_id VARCHAR NOT NULL, status VARCHAR NOT NULL, reason VARCHAR NOT NULL, received DATE NOT NULL",
    "policies": "id VARCHAR PRIMARY KEY, payer VARCHAR NOT NULL, procedure VARCHAR NOT NULL, starts DATE NOT NULL, ends DATE NOT NULL, section VARCHAR NOT NULL, excerpt VARCHAR NOT NULL",
    "decisions": "id VARCHAR PRIMARY KEY, line_id VARCHAR NOT NULL, action VARCHAR NOT NULL, note VARCHAR NOT NULL",
}
ACTIONS = ["Verify authorization", "Verify coverage", "Check for duplicate", "Request payer clarification", "Close review"]
PROCEDURES = {"IMG-01": "MRI, knee", "LAB-02": "Metabolic panel", "VIS-03": "Office visit"}
REASONS = {
    "AUTH": "Prior authorization required",
    "ELIG": "Coverage inactive on service date",
    "DUP": "Duplicate service",
}

def generate(seed=43):
    rng = random.Random(seed)
    data = {name: [] for name in TABLES}
    def add(table, **row):
        data[table].append(row)

    for version, start, end, clause in [
        ("v1", "2025-01-01", "2025-07-01", "Authorization may be obtained up to two business days after service."),
        ("v2", "2025-07-01", "2026-01-01", "Authorization must be on file before the service. If it is missing, verify the payer portal before requesting reconsideration."),
        ("2026-v1", "2026-01-01", "2026-04-01", "Authorization may be obtained up to two business days after service."),
        ("2026-v2", "2026-04-01", "2026-07-01", "Authorization must be on file before the service. If it is missing, verify the payer portal before requesting reconsideration."),
    ]:
        add("policies", id=f"NS-IMG-{version}", payer="Northstar Health", procedure="IMG-01",
            starts=start, ends=end, section=f"Imaging § 4.2 · {version}", excerpt=clause)
    add("policies", id="NS-VIS-v1", payer="Northstar Health", procedure="VIS-03",
        starts="2025-01-01", ends="2026-01-01", section="Professional services § 2.1",
        excerpt="Coverage must be active on the service date. Review prior submissions for the same service before resubmitting.")

    def claim(key, service, cases, payer, authorization_recorded=None, response_days=10):
        member = f"Fictional member {key}"
        submitted = service + timedelta(days=3)
        add("claims", id=f"CLM-{key}", member=member, payer=payer, submitted=str(submitted))
        # Each ordinary claim uses a distinct fictional member. Duplicate lines share the member and service.
        if not cases[0][1]:
            add("eligibility", id=f"E-{key}", member=member, payer=payer,
                starts=str(service - timedelta(days=30)), ends=str(service + timedelta(days=90)),
                recorded=str(service - timedelta(days=32)))
        for j, (procedure, no_elig, no_auth, status, reason) in enumerate(cases, 1):
            line = f"CLM-{key}-{j}"
            add("lines", id=line, claim_id=f"CLM-{key}", procedure=procedure, service=str(service),
                amount={"IMG-01": 1250, "LAB-02": 145, "VIS-03": 220}[procedure])
            if procedure == "IMG-01" and not no_auth:
                add("authorizations", id=f"A-{key}-{j}", member=member, payer=payer, procedure=procedure,
                    starts=str(authorization_recorded or service - timedelta(days=3)), ends=str(service + timedelta(days=14)),
                    recorded=str(authorization_recorded or service - timedelta(days=4)))
            add("responses", id=f"R-{key}-{j}", line_id=line, status=status, reason=reason,
                received=str(submitted + timedelta(days=response_days)))
            if key.isdecimal() and status == "denied" and int(key) % 17 == 0:
                add("decisions", id=f"D-{key}-{j}", line_id=line, action="Request payer clarification",
                    note="Synthetic historical review")

    for d in range(345):
        service = date(2025, 1, 2) + timedelta(days=d)
        for i in range(9):
            payer = rng.choice(["Northstar Health", "Juniper Mutual"])
            procedure = rng.choices(list(PROCEDURES), weights=[4, 3, 3])[0]
            no_elig, no_auth = rng.random() < .18, rng.random() < .38
            candidates = [(procedure, False)]
            if rng.random() < .34:
                candidates.append((procedure if rng.random() < .37 else ("LAB-02" if procedure != "LAB-02" else "VIS-03"), True))
            cases = []
            for code, second in candidates:
                reason = ""
                if no_elig and rng.random() < .61:
                    reason = "ELIG"
                elif second and code == procedure and rng.random() < .82:
                    reason = "DUP"
                elif code == "IMG-01" and no_auth and rng.random() < (.79 if payer == "Northstar Health" else .52):
                    reason = "AUTH"
                elif rng.random() < .022:
                    reason = rng.choice(["ELIG", "DUP"])
                status = "pending" if rng.random() < .045 else ("denied" if reason else "approved")
                cases.append((code, no_elig, no_auth, status, reason if status == "denied" else ""))
            claim(f"{d * 9 + i:04}", service, cases, payer)
    for key, service in [("GUIDE", date(2025, 9, 16)), ("EARLY", date(2025, 6, 30))]:
        claim(key, service, [("IMG-01", False, True, "denied", "AUTH"),
                            ("LAB-02", False, False, "approved", "")], "Northstar Health")
    claim("LEDGER", date(2026, 3, 30), [("IMG-01", False, False, "denied", "AUTH")],
          "Northstar Health", authorization_recorded=date(2026, 1, 9), response_days=11)
    add("responses", id="R-UNMATCHED", line_id="CLM-NOT-IN-EXTRACT-1", status="denied",
        reason="ELIG", received="2025-12-20")
    return data

def import_data(db, data):
    """Validate and insert an immutable extract atomically, accepting identical replays."""
    if set(data) != set(TABLES):
        raise ValueError("Unexpected table set")
    db.execute("BEGIN")
    try:
        for name, schema in TABLES.items():
            db.execute(f"CREATE TABLE IF NOT EXISTS {name} ({schema})")
            columns = [field.split()[0] for field in schema.split(", ")]
            rows = data[name]
            if any(set(row) != set(columns) or not row.get("id") for row in rows):
                raise ValueError(f"Invalid fields in {name}")
            if len({row["id"] for row in rows}) != len(rows):
                raise ValueError(f"Duplicate identifier within {name} extract")
            if rows:
                placeholders = ", ".join("?" for _ in columns)
                db.execute(f"CREATE TEMP TABLE incoming AS SELECT * FROM {name} WHERE false")
                db.executemany(f"INSERT INTO incoming VALUES ({placeholders})",
                               [[row[col] for col in columns] for row in rows])
                changed = " OR ".join(f"old.{col} IS DISTINCT FROM new.{col}" for col in columns)
                if db.execute(f"SELECT 1 FROM {name} old JOIN incoming new USING (id) WHERE {changed} LIMIT 1").fetchone():
                    raise ValueError(f"Conflicting identifier in {name}")
                db.execute(f"INSERT INTO {name} SELECT * FROM incoming ON CONFLICT DO NOTHING")
                db.execute("DROP TABLE incoming")
        validations = [
            "SELECT 1 FROM lines l LEFT JOIN claims c ON c.id=l.claim_id WHERE c.id IS NULL OR amount <= 0 OR l.service > c.submitted",
            "SELECT 1 FROM responses WHERE status NOT IN ('approved','denied','pending') OR (status = 'denied' AND reason NOT IN ('AUTH','ELIG','DUP')) OR (status <> 'denied' AND reason <> '')",
            "SELECT 1 FROM responses GROUP BY line_id HAVING count(*) > 1",
            "SELECT 1 FROM responses r JOIN lines l ON l.id=r.line_id JOIN claims c ON c.id=l.claim_id WHERE r.received < c.submitted",
            "SELECT 1 FROM decisions d LEFT JOIN responses r ON r.line_id=d.line_id WHERE r.line_id IS NULL OR r.status <> 'denied'",
            *[f"SELECT 1 FROM {table} WHERE starts >= ends" for table in ("eligibility", "authorizations", "policies")],
        ]
        for query in validations:
            if db.execute(query + " LIMIT 1").fetchone():
                raise ValueError(f"Extract failed validation: {query}")
        db.execute("COMMIT")
    except Exception:
        db.execute("ROLLBACK")
        raise

def connect(path=":memory:"):
    return duckdb.connect(str(path))

def rows(db, query, params=None):
    result = db.execute(query, params or [])
    return [dict(zip([col[0] for col in result.description], row)) for row in result.fetchall()]
