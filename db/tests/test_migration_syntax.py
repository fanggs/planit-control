"""Parse SQL and procedural bodies; this does not replace a TimescaleDB run."""
from pathlib import Path
import unittest

try:
    from pglast import parse_sql,parse_plpgsql
except ImportError:
    parse_sql=parse_plpgsql=None


@unittest.skipIf(parse_sql is None,'Install db/requirements-dev.txt for PostgreSQL syntax checks')
class MigrationSyntaxTests(unittest.TestCase):
    def test_sql_and_procedural_blocks_parse(self):
        folder=Path(__file__).resolve().parents[1]/'migrations'
        for path in sorted(folder.glob('*.sql')):
            with self.subTest(migration=path.name):
                sql=path.read_text()
                self.assertTrue(parse_sql(sql))
                if 'DO $' in sql:
                    self.assertTrue(parse_plpgsql(sql))


if __name__=='__main__':unittest.main()
