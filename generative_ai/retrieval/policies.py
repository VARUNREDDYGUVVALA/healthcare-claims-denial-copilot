"""Temporal policy matching and evidence-bound explanations."""
import re

from data.generator.claims import REASONS
from data_engineering.ingestion.duckdb_extract import rows

POLICY_TERMS = {"AUTH": {"authorization", "preauthorization"},
                "ELIG": {"coverage", "eligibility"}, "DUP": {"duplicate", "resubmitting"}}
SUGGESTIONS = {"AUTH": "Verify authorization", "ELIG": "Verify coverage", "DUP": "Check for duplicate"}


def policy(db, line):
    if not line["reason"]:
        return None
    candidates = rows(db, """
        SELECT * FROM policies WHERE payer=? AND procedure=? AND starts<=? AND ends>?
    """, [line["payer"], line["procedure"], line["service"], line["service"]])
    tokens = POLICY_TERMS[line["reason"]]
    def relevance(candidate):
        return len(tokens & set(re.findall(r"\w+", candidate["excerpt"].lower())))
    ranked = [candidate for candidate in candidates if relevance(candidate)]
    return min(ranked, key=lambda candidate: (-relevance(candidate), candidate["id"]), default=None)

def explain(db, line):
    if line["status"] != "denied":
        return None
    citation = policy(db, line)
    return {"reason": REASONS[line["reason"]], "code": line["reason"], "policy": citation,
            "action": SUGGESTIONS[line["reason"]] if citation else "Request payer clarification"}
