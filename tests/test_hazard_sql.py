"""Validate PostgreSQL syntax without touching Sid's database."""

from pathlib import Path
import unittest
from uuid import uuid4

from pglast import ast, parse_sql
from sqlalchemy import BigInteger, Uuid, insert, select, update
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

    def test_foundation_site_and_alert_keys_match_report_storage(self):
        """Check Sid's schema contracts without opening or changing a database."""
        root = Path(__file__).resolve().parents[1]
        foundation = parse_sql(
            (root / "db/migrations/001_foundation.sql").read_text(encoding="utf-8")
        )
        report_sql = parse_sql((root / "db/hazard_report.sql").read_text(encoding="utf-8"))
        foundation_tables = {
            item.stmt.relation.relname: item.stmt
            for item in foundation
            if isinstance(item.stmt, ast.CreateStmt)
        }
        self.assertNotIn("hazard_reports", foundation_tables)
        sites = foundation_tables["sites"]
        alerts = foundation_tables["alerts"]
        report = next(item.stmt for item in report_sql if isinstance(item.stmt, ast.CreateStmt))
        self.assertEqual(
            {sites.relation.schemaname, alerts.relation.schemaname, report.relation.schemaname},
            {"public"},
        )

        def columns(table):
            return {item.colname: item for item in table.tableElts if isinstance(item, ast.ColumnDef)}

        site_columns = columns(sites)
        alert_columns = columns(alerts)
        report_columns = columns(report)
        for column in (
            site_columns["site_id"], alert_columns["id"],
            alert_columns["site_id"], report_columns["site_id"],
        ):
            self.assertEqual(tuple(part.sval for part in column.typeName.names), ("pg_catalog", "int8"))
        self.assertEqual(tuple(part.sval for part in report_columns["id"].typeName.names), ("uuid",))
        self.assertIsInstance(_reports.c.site_id.type, BigInteger)
        self.assertIsInstance(_reports.c.id.type, Uuid)
        self.assertTrue({"hazard_type", "level", "trigger", "ended_at"} <= alert_columns.keys())

        references = [
            constraint for constraint in report_columns["site_id"].constraints
            if constraint.contype.name == "CONSTR_FOREIGN"
        ]
        self.assertEqual(len(references), 1)
        self.assertEqual(
            (references[0].pktable.schemaname, references[0].pktable.relname),
            ("public", "sites"),
        )
        self.assertEqual(tuple(part.sval for part in references[0].pk_attrs), ("site_id",))

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
