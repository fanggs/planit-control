import contextlib
import io
import unittest
from unittest.mock import MagicMock, patch

from db.migrate import check_connection, main, safe_failure


class DatabaseFailure(Exception):
    def __init__(self, text, sqlstate=None):
        super().__init__(text)
        self.sqlstate = sqlstate


class DiagnosticTests(unittest.TestCase):
    def test_error_categories_do_not_expose_driver_message(self):
        secret = "postgresql://private-user:never-print-this@private-host/db"
        cases = [
            (DatabaseFailure(secret,"28P01"),"password"),
            (DatabaseFailure(secret,"42501"),"permission"),
            (DatabaseFailure(secret,"42P07"),"already exists"),
            (DatabaseFailure("could not translate host " + secret),"hostname"),
            (DatabaseFailure("certificate verify failed " + secret),"SSL"),
            (DatabaseFailure("timeout expired " + secret),"timed out"),
            (DatabaseFailure(secret,"XX000"),"XX000"),
            (DatabaseFailure(secret),"recognized error category"),
        ]
        for error, expected in cases:
            with self.subTest(expected=expected):
                message=safe_failure(error)
                self.assertIn(expected,message)
                for private in (secret,"private-user","never-print-this","private-host"):
                    self.assertNotIn(private,message)

    def test_connection_check_only_issues_read_only_statements(self):
        connection=MagicMock()
        # Use a distinct response for each read-only inspection.
        version, extension, tables=MagicMock(),MagicMock(),MagicMock()
        version.fetchone.return_value=("17.0",)
        extension.fetchone.return_value=("2.30.2",)
        tables.fetchone.return_value=(0,)
        connection.execute.side_effect=[None,version,extension,tables]
        output=io.StringIO()
        with contextlib.redirect_stdout(output):
            check_connection(connection)
        statements=[call.args[0] for call in connection.execute.call_args_list]
        self.assertEqual(statements[0],"SET TRANSACTION READ ONLY")
        self.assertTrue(all(sql.startswith(("SET TRANSACTION READ ONLY","SHOW ","SELECT ")) for sql in statements))
        self.assertIn("TimescaleDB version: 2.30.2",output.getvalue())
        self.assertIn("No database changes made",output.getvalue())


try:
    import psycopg
except ImportError:
    psycopg=None


@unittest.skipIf(psycopg is None,"Use the project virtual environment with db/requirements.txt installed")
class CommandTests(unittest.TestCase):
    def test_prompt_supplies_password_directly_without_echoing_it(self):
        output=io.StringIO()
        url="postgresql://test@private.invalid/tsdb"
        with patch.dict("os.environ",{"DATABASE_URL":url,"PGPASSWORD":"old-value"}), patch("sys.argv",["db.migrate","--check","--prompt-password"]), patch("sys.stdin.isatty",return_value=True), patch("db.migrate.getpass.getpass",return_value="direct-test-secret"), patch.object(psycopg,"connect",return_value=MagicMock()) as connect, patch("db.migrate.check_connection"), patch("db.migrate.migrate") as migration, contextlib.redirect_stdout(output):
            main()
        self.assertEqual(connect.call_args.kwargs["password"],"direct-test-secret")
        self.assertNotIn("direct-test-secret",output.getvalue())
        migration.assert_not_called()

    def test_empty_password_prompt_never_attempts_connection(self):
        output=io.StringIO()
        with patch.dict("os.environ",{"DATABASE_URL":"postgresql://test@private.invalid/tsdb"}), patch("sys.argv",["db.migrate","--check","--prompt-password"]), patch("sys.stdin.isatty",return_value=True), patch("db.migrate.getpass.getpass",return_value=""), patch.object(psycopg,"connect") as connect, contextlib.redirect_stderr(output), self.assertRaises(SystemExit):
            main()
        connect.assert_not_called()

    def test_check_mode_never_runs_migrations_and_handles_uri_timeout(self):
        client=MagicMock()
        output=io.StringIO()
        url="postgresql://test:never-print-this@private.invalid/tsdb?connect_timeout=9"
        with patch.dict("os.environ",{"DATABASE_URL":url}), patch("sys.argv",["db.migrate","--check"]), patch.object(psycopg,"connect",return_value=client) as connect, patch("db.migrate.migrate") as migration, patch("db.migrate.check_connection") as check, contextlib.redirect_stdout(output):
            main()
        migration.assert_not_called()
        check.assert_called_once()
        self.assertEqual(connect.call_args.kwargs["connect_timeout"],"15")
        self.assertNotIn("never-print-this",output.getvalue())

    def test_connection_failure_output_is_safe(self):
        secret="postgresql://test:never-print-this@private.invalid/tsdb"
        output=io.StringIO()
        with patch.dict("os.environ",{"DATABASE_URL":secret}), patch("sys.argv",["db.migrate","--check"]), patch.object(psycopg,"connect",side_effect=psycopg.OperationalError("password authentication failed " + secret)), contextlib.redirect_stderr(output), self.assertRaises(SystemExit) as result:
            main()
        self.assertEqual(result.exception.code,1)
        self.assertIn("Database connection failed",output.getvalue())
        self.assertIn("password",output.getvalue())
        self.assertNotIn(secret,output.getvalue())
        self.assertNotIn("never-print-this",output.getvalue())
        self.assertNotIn("private.invalid",output.getvalue())

    def test_accidentally_pasted_psql_command_is_rejected_before_connect(self):
        output=io.StringIO()
        with patch.dict("os.environ",{"DATABASE_URL":"psql 'postgresql://test:never-print-this@private.invalid/tsdb'"}), patch("sys.argv",["db.migrate","--check"]), patch.object(psycopg,"connect") as connect, contextlib.redirect_stderr(output), self.assertRaises(SystemExit) as result:
            main()
        self.assertEqual(result.exception.code,2)
        connect.assert_not_called()
        self.assertIn("Paste only the PostgreSQL URI",output.getvalue())
        self.assertNotIn("never-print-this",output.getvalue())


if __name__ == "__main__":
    unittest.main()
