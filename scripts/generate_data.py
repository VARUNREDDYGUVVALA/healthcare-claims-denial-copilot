"""Import the deterministic fictional extract into the local DuckDB database."""
from data.generator.claims import generate
from data_engineering.ingestion.duckdb_extract import connect, import_data
from machine_learning.training.pipeline import ARTIFACTS


def main():
    ARTIFACTS.mkdir(exist_ok=True)
    records = generate()
    with connect(ARTIFACTS / "claims.duckdb") as db:
        import_data(db, records)
    print(f"Prepared {len(records['lines']):,} fictional claim lines.")


if __name__ == "__main__":
    main()
