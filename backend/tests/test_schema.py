"""The committed Supabase migration must match the ORM models exactly."""

from __future__ import annotations

from pathlib import Path

from app.models import Base
from scripts.export_schema import SERVER_ONLY, build

MIGRATION = Path(__file__).resolve().parents[2] / "supabase" / "migrations" / "20260924000000_nexus_init.sql"


def test_migration_is_up_to_date() -> None:
    assert MIGRATION.read_text().strip() == build().strip(), (
        "Models changed: run `python -m scripts.export_schema > ../supabase/migrations/<new>.sql`"
    )


def test_every_table_has_row_level_security() -> None:
    sql = MIGRATION.read_text()
    for table in Base.metadata.sorted_tables:
        assert f"ALTER TABLE {table.name} ENABLE ROW LEVEL SECURITY;" in sql
        if table.name not in SERVER_ONLY:
            assert f"CREATE POLICY {table.name}_owner ON {table.name}" in sql
