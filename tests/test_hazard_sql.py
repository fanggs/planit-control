"""Validate PostgreSQL syntax without touching Sid's database."""

from pathlib import Path
import unittest
from uuid import uuid4

from pglast import ast, parse_sql
from sqlalchemy import insert, select, update
from sqlalchemy.dialects import postgresql

from api.services.hazard_report_service import _reports


class PostgreSQLContractTests(unittest.TestCase):
    def test_migration_parses_and_matches_query_mapping(self):
        path = Path(__file__).resolve().parents[1] / "db" / "hazard_report.sql"
        statements = parse_sql(path.read_text(encoding="utf-8"))
        creates = [item.stmt for item in statements if isinstance(item.stmt, ast.CreateStmt)]
        self.assertEqual(len(creates), 1)
        table = creates[0]
        self.assertEqual(table.relation.schemaname, "public")
        self.assertEqual(table.relation.relname, "hazard_reports")
        columns = {item.colname for item in table.tableElts if isinstance(item, ast.ColumnDef)}
        self.assertEqual(columns, set(_reports.c.keys()))

    def test_query_shapes_compile_for_postgresql(self):
        dialect = postgresql.dialect()
        create = insert(_reports).values(id=uuid4(), site_id=6045).returning(*_reports.c)
        resolve = update(_reports).where(_reports.c.id == uuid4()).values(status="resolved").returning(*_reports.c)
        lock = select(_reports).where(_reports.c.id == uuid4()).with_for_update()
        self.assertIn("RETURNING public.hazard_reports.id", str(create.compile(dialect=dialect)))
        self.assertIn("RETURNING public.hazard_reports.id", str(resolve.compile(dialect=dialect)))
        self.assertIn("FOR UPDATE", str(lock.compile(dialect=dialect)))


if __name__ == "__main__":
    unittest.main()
