import duckdb
import pytest

from data_engineering.transformations.synthetic_lakehouse import build_lakehouse


def test_small_lakehouse_reconciles_and_can_be_reproduced(tmp_path):
    first = tmp_path / "first"
    manifest = build_lakehouse("small", 43, first)
    assert manifest["counts"]["claim_lines"] == 5000
    assert manifest["counts"]["claims"] == 1250
    assert manifest["counts"]["members"] == 250
    assert manifest["service_months"] == 12
    assert manifest["service_end_exclusive"] == "2024-01-01"
    assert all(manifest["checks"].values())
    assert build_lakehouse("small", 43, first) == manifest
    assert build_lakehouse("small", 43, tmp_path / "repeat") == manifest

    with duckdb.connect() as db:
        lines = first / "silver/line_fact.parquet"
        count, statuses, reasons, duplicates = db.execute("""
            SELECT count(*), count(DISTINCT recorded_status), count(DISTINCT recorded_reason),
                   count(*) FILTER (WHERE duplicate_in_claim)
            FROM read_parquet(?)
        """, [str(lines)]).fetchone()
    assert (count, statuses, reasons) == (5000, 3, 3)
    assert duplicates > 0


def test_snapshot_directory_cannot_be_reused_for_other_data_or_corrupt_files(tmp_path):
    output = tmp_path / "snapshot"
    build_lakehouse("small", 43, output)
    with pytest.raises(FileExistsError, match="different snapshot"):
        build_lakehouse("small", 44, output)
    (output / "bronze/plans.parquet").write_bytes(b"corrupt")
    with pytest.raises(ValueError, match="checksum mismatch"):
        build_lakehouse("small", 43, output)
