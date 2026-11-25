"""Compatibility imports for the original synthetic-data module."""
from data.generator.claims import ACTIONS, PROCEDURES, REASONS, TABLES, generate
from data_engineering.ingestion.duckdb_extract import connect, import_data, rows

__all__ = ["ACTIONS", "PROCEDURES", "REASONS", "TABLES", "generate", "connect", "import_data", "rows"]
