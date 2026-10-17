"""
Tiger Data (PostgreSQL + TimescaleDB) connection for the API and jobs.

Reads DATABASE_URL (no password in it) and PGPASSWORD from the environment.
For local development they come from the repo's gitignored .env; on the server
they're set in the service environment. Nothing here prints or logs them.

    get_db()   request-scoped SQLAlchemy session (FastAPI dependency; Aryan's
               report routes use this)
    query()    small read helper returning plain dicts with ISO UTC timestamps
    execute()  small write helper in its own transaction

If DATABASE_URL isn't set, `configured()` is False and callers fall back to
the checked-in files, so the API still runs without database access.
"""
from __future__ import annotations

import os
from collections.abc import Iterator
from datetime import date, datetime, timezone
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine, make_url
from sqlalchemy.orm import Session, sessionmaker

ROOT = Path(__file__).resolve().parents[1]


def _load_env() -> None:
    env = ROOT / ".env"
    if not env.exists():
        return
    for line in env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())


_load_env()

_engine: Engine | None = None
_Session: sessionmaker | None = None


def configured() -> bool:
    return bool(os.environ.get("DATABASE_URL"))


def engine() -> Engine:
    global _engine, _Session
    if _engine is None:
        url = make_url(os.environ["DATABASE_URL"]).set(drivername="postgresql+psycopg")
        _engine = create_engine(
            url,
            pool_pre_ping=True,
            pool_size=2,  # per worker; the shared service has a connection limit
            max_overflow=2,
            connect_args={"connect_timeout": 15},
        )
        _Session = sessionmaker(bind=_engine, autoflush=False, expire_on_commit=False)
    return _engine


def get_db() -> Iterator[Session]:
    engine()
    with _Session() as session:
        yield session


def _plain(value):
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    if isinstance(value, date):
        return value.isoformat()
    return value


def query(sql: str, **params) -> list[dict]:
    with engine().connect() as conn:
        result = conn.execute(text(sql), params)
        return [{k: _plain(v) for k, v in row._mapping.items()} for row in result]


def execute(sql: str, **params) -> None:
    with engine().begin() as conn:
        conn.execute(text(sql), params)
