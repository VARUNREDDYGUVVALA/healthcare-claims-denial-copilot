"""Read-only stdio MCP tools for local synthetic claim evidence."""
from datetime import date

from mcp.server.fastmcp import FastMCP

from data_engineering.ingestion.duckdb_extract import connect, rows
from machine_learning.training.pipeline import ARTIFACTS
from machine_learning.feature_engineering.claims import claim_lines, features
from generative_ai.retrieval.policies import explain

server = FastMCP("Synthetic Claims Copilot")


def open_extract():
    path = ARTIFACTS / "claims.duckdb"
    if not path.is_file():
        raise ValueError("Initialize artifacts with python -m scripts.export_demo.")
    return connect(path, read_only=True)


@server.tool()
def applicable_policies(payer: str, procedure: str, service_date: date) -> list[dict]:
    """Return synthetic policies effective for a payer, procedure, and service date."""
    with open_extract() as db:
        return rows(db, """
            SELECT id, payer, procedure, starts, ends, section, excerpt FROM policies
            WHERE payer = ? AND procedure = ? AND starts <= ? AND ends > ? ORDER BY id
        """, [payer, procedure, service_date, service_date])


@server.tool()
def claim_evidence(line_id: str) -> dict:
    """Read a fictional claim's evidence, recorded response explanation, and scoring inputs."""
    with open_extract() as db:
        line = next((item for item in claim_lines(db) if item["id"] == line_id), None)
        if line is None:
            raise ValueError("Claim line not found.")
        return {
            "line_id": line_id, "service_date": line["service"], "payer": line["payer"],
            "procedure": line["procedure"], "recorded_status": line["status"],
            "eligibility": line["eligibility"], "authorizations": line["authorizations"],
            "duplicates": line["duplicates"], "features": features(line), "explanation": explain(db, line),
        }


if __name__ == "__main__":
    server.run(transport="stdio")
