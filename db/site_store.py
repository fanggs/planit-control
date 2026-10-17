"""Atomic, parameterized site upserts; old catalog rows remain for foreign keys."""
from get_data.sites import SITE_COLUMNS, validate_sites
from db.validation import aware_time


def load_sites(connection, rows):
    validate_sites(rows)
    ids = [row["site_id"] for row in rows]
    vintage = rows[0]["source_vintage"]
    if any(row["source_vintage"] != vintage for row in rows):
        raise ValueError("A load must use one source vintage")
    # Identifiers come only from checked-in constants, never external data.
    columns = ", ".join(SITE_COLUMNS)
    placeholders = ", ".join("%s" for _ in SITE_COLUMNS)
    assignments = ", ".join(f"{column} = EXCLUDED.{column}" for column in SITE_COLUMNS if column != "site_id")
    with connection.transaction():
        connection.execute("SELECT pg_advisory_xact_lock(781025)")
        newer = connection.execute(
            "SELECT count(*) FROM public.sites WHERE source_vintage > %s", (vintage,),
        ).fetchone()[0]
        if newer:
            raise ValueError("Refusing to replace a newer site catalog with older data")
        # Never delete old sites: crew reports and historical data reference them.
        connection.execute("UPDATE public.sites SET is_monitored = FALSE WHERE is_monitored AND NOT (site_id = ANY(%s))", (ids,))
        with connection.cursor() as cursor:
            cursor.executemany(
                f"INSERT INTO public.sites ({columns}) VALUES ({placeholders}) "
                f"ON CONFLICT (site_id) DO UPDATE SET {assignments}",
                [tuple(row[column] for column in SITE_COLUMNS) for row in rows],
            )
        stored = [dict(zip(SITE_COLUMNS, values)) for values in connection.execute(
            f"SELECT {columns} FROM public.sites WHERE is_monitored ORDER BY site_id"
        ).fetchall()]
        validate_sites(stored)
        if [item["site_id"] for item in stored] != sorted(ids):
            raise ValueError("Post-load monitored site IDs do not match the validated catalog")
        expected = {row["site_id"]: row for row in rows}
        for row in stored:
            for column in SITE_COLUMNS:
                actual, wanted = row[column], expected[row["site_id"]][column]
                if column == "retrieved_at":
                    actual, wanted = aware_time(actual), aware_time(wanted)
                if actual != wanted:
                    raise ValueError(f"Post-load field mismatch: {row['site_id']} {column}")
