"""Apply checked-in migrations transactionally; never print connection secrets."""
import argparse
import hashlib
import os
from pathlib import Path

MIGRATIONS = Path(__file__).parent / "migrations"


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
    args = parser.parse_args()
    if args.list:
        for path in sorted(MIGRATIONS.glob("*.sql")):
            print(path.name)
        return
    url = os.environ.get("DATABASE_URL")
    if not url:
        parser.exit(2, "DATABASE_URL is not configured. No database changes made.\n")
    try:
        import psycopg
        with psycopg.connect(url, autocommit=True) as connection:
            migrate(connection)
    except ImportError:
        parser.exit(2, "Install db/requirements.txt in your project environment first.\n")
    except Exception:
        # Driver exceptions can contain hostnames or connection strings.
        parser.exit(1, "Migration failed; transaction rolled back. Check database access and schema with the owner.\n")


if __name__ == "__main__":
    main()
