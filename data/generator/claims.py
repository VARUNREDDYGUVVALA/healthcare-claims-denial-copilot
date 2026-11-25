"""Generate and ingest fictional billing extracts."""
from datetime import date, timedelta
import random

from data.policies.catalog import policy_sections

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

    data["policies"] = policy_sections()

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
