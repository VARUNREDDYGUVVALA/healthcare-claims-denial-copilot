"""Validate and import immutable synthetic extracts into DuckDB."""
import duckdb

from data.generator.claims import TABLES

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

def connect(path=":memory:", *, read_only=False):
    return duckdb.connect(str(path), read_only=read_only)

def rows(db, query, params=None):
    result = db.execute(query, params or [])
    return [dict(zip([col[0] for col in result.description], row)) for row in result.fetchall()]
