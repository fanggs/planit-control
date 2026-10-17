"""Apply checked-in migrations transactionally; never print connection secrets."""
import argparse
import getpass
import hashlib
import os
from pathlib import Path
import re
import sys
import warnings

MIGRATIONS = Path(__file__).parent / "migrations"


def safe_failure(exc):
    """Classify errors without echoing server/driver text or connection secrets."""
    state = getattr(exc, "sqlstate", None)
    messages = {
        "28P01": "The database rejected the password. Check the saved connection URI.",
        "28000": "The database rejected this login or its connection permissions.",
        "3D000": "The database name in the connection settings was not found.",
        "42501": "This database login lacks permission for the requested operation.",
        "25006": "The database is read-only; check service status and storage limits.",
        "42P07": "A table already exists. Inspect the existing schema before migrating; do not delete it.",
        "42710": "A database object already exists. Inspect the existing schema before migrating.",
        "42601": "PostgreSQL found a syntax error in the migration SQL.",
        "42P01": "A table needed by this operation does not exist.",
        "42883": "A required database function is unavailable.",
    }
    if state in messages:
        return f"SQLSTATE {state}: {messages[state]}"
    # Examine text only for classification; never include it in returned output.
    text = str(exc).lower()
    for needles, message in (
        (("password authentication failed", "no password supplied"), "The password is missing or was rejected. Check the connection URI locally."),
        (("could not translate host", "name or service not known", "nodename nor servname"), "The database hostname could not be resolved. Check the URI and network connection."),
        (("certificate verify failed", "certificate verification failed", "ssl error", "sslmode"), "The SSL connection failed. Check the SSL settings supplied by Tiger Data."),
        (("timeout expired", "timed out", "connection timeout"), "The connection timed out. Check that the service is Ready and reachable."),
        (("connection refused",), "The server refused the connection. Check service status and the connection port."),
        (("applied migration changed",), "An already applied migration was edited. Restore it and add a new migration instead."),
    ):
        if any(needle in text for needle in needles):
            return message
    if isinstance(state, str) and re.fullmatch(r"[A-Z0-9]{5}", state):
        return f"SQLSTATE {state}: Database operation failed; this code can be shared for diagnosis."
    return "The operation failed without a recognized error category. Connection details were not printed."


def check_connection(connection):
    """Read-only inspection: no migrations, tables, extensions or roles created."""
    with connection.transaction():
        connection.execute("SET TRANSACTION READ ONLY")
        version = connection.execute("SHOW server_version").fetchone()[0]
        extension = connection.execute(
            "SELECT extversion FROM pg_extension WHERE extname = 'timescaledb'"
        ).fetchone()
        tables = connection.execute(
            "SELECT count(*) FROM information_schema.tables "
            "WHERE table_schema = 'public' AND table_type = 'BASE TABLE'"
        ).fetchone()[0]
    print(f"PostgreSQL version: {version}")
    print(f"TimescaleDB version: {extension[0] if extension else 'not installed'}")
    print(f"Public tables: {tables}")
    print("Connection check passed. No database changes made.")


def migrate(connection):
    # Session lock serializes competing migration processes on this database.
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_lock(781024)")
    connection.commit()
    try:
        with connection.transaction():
            connection.execute("""CREATE TABLE IF NOT EXISTS public.planit_schema_migrations
                (name TEXT PRIMARY KEY, sha256 TEXT NOT NULL,
                 applied_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
        for path in sorted(MIGRATIONS.glob("*.sql")):
            sql = path.read_text()
            checksum = hashlib.sha256(sql.encode()).hexdigest()
            with connection.transaction():
                previous = connection.execute(
                    "SELECT sha256 FROM public.planit_schema_migrations WHERE name = %s",
                    (path.name,),
                ).fetchone()
                if previous:
                    if previous[0] != checksum:
                        raise RuntimeError(f"Applied migration changed: {path.name}")
                    continue
                connection.execute(sql)
                connection.execute(
                    "INSERT INTO public.planit_schema_migrations (name, sha256) VALUES (%s, %s)",
                    (path.name, checksum),
                )
            print(f"Applied {path.name}")
    finally:
        connection.execute("SELECT pg_advisory_unlock(781024)")
        connection.commit()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list", action="store_true", help="List migrations without a database connection")
    parser.add_argument("--check", action="store_true", help="Check connection and versions without changing the database")
    parser.add_argument("--prompt-password", action="store_true", help="Securely prompt for the database password, overriding other password settings")
    args = parser.parse_args()
    if args.list:
        for path in sorted(MIGRATIONS.glob("*.sql")):
            print(path.name)
        return
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        parser.exit(2, "DATABASE_URL is not configured. No database changes made.\n")
    try:
        import psycopg
        from psycopg.conninfo import conninfo_to_dict
    except ImportError:
        parser.exit(2, "Install db/requirements.txt in your project environment first.\n")
    try:
        settings = conninfo_to_dict(url)
    except Exception:
        parser.exit(2, "DATABASE_URL could not be parsed. Paste only the PostgreSQL URI, not a psql command, into the hidden prompt. No connection attempted.\n")
    if args.prompt_password:
        if not sys.stdin.isatty():
            parser.exit(2, "Run --prompt-password in your interactive Mac terminal. No connection attempted.\n")
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", getpass.GetPassWarning)
                password = getpass.getpass("Database password (hidden): ")
        except (EOFError, KeyboardInterrupt, getpass.GetPassWarning):
            parser.exit(2, "Secure password entry was unavailable or cancelled. No connection attempted.\n")
        if not password:
            parser.exit(2, "No password entered. No connection attempted.\n")
        settings["password"] = password
    connected = False
    settings["connect_timeout"] = "15"
    try:
        with psycopg.connect(**settings, autocommit=True) as connection:
            connected = True
            print("Connected to PostgreSQL.")
            if args.check:
                check_connection(connection)
            else:
                migrate(connection)
    except Exception as exc:
        phase = "Database check" if args.check else "Migration"
        if not connected:
            phase = "Database connection"
        detail = safe_failure(exc)
        if args.prompt_password and not connected:
            detail += " A password was supplied directly from the hidden prompt."
        parser.exit(1, f"{phase} failed. {detail}\n")


if __name__ == "__main__":
    main()
