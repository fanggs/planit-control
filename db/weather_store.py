"""Atomic weather upserts with a complete post-load round-trip check."""
from db.validation import aware_time
from get_data.weather_values import (READING_COLUMNS, FORECAST_COLUMNS, PROVIDER,
                                     validate_weather_rows)


def _key(row, kind):
    times = ("observed_at",) if kind == "weather_readings" else ("valid_at", "issued_at")
    return (row["site_id"], row["provider"], *(aware_time(row[name]) for name in times))


def load_weather(connection, readings, forecasts, site_ids, *, as_of, hours=48):
    validate_weather_rows(readings, forecasts, site_ids, as_of=as_of, hours=hours)
    with connection.transaction():
        connection.execute("SELECT pg_advisory_xact_lock(781026)")
        existing = connection.execute(
            "SELECT site_id FROM public.sites WHERE site_id = ANY(%s) AND is_monitored FOR KEY SHARE", (site_ids,),
        ).fetchall()
        if {item[0] for item in existing} != set(site_ids):
            raise ValueError("Load the matching monitored plant catalog before loading weather")
        for table, rows, columns, key_columns in (
            ("weather_readings", readings, READING_COLUMNS, ("site_id", "observed_at", "provider")),
            ("weather_forecasts", forecasts, FORECAST_COLUMNS, ("site_id", "valid_at", "issued_at", "provider")),
        ):
            # All identifiers are checked-in constants; source values are parameters.
            names = ", ".join(columns)
            assignments = ", ".join(f"{name} = EXCLUDED.{name}" for name in columns if name not in key_columns)
            statement = (f"INSERT INTO public.{table} ({names}) VALUES ({', '.join('%s' for _ in columns)}) "
                         f"ON CONFLICT ({', '.join(key_columns)}) DO UPDATE SET {assignments} "
                         f"WHERE EXCLUDED.retrieved_at >= {table}.retrieved_at")
            with connection.cursor() as cursor:
                cursor.executemany(statement, [tuple(row[name] for name in columns) for row in rows])
            time_column = "observed_at" if table == "weather_readings" else "valid_at"
            parameters = [site_ids, PROVIDER, sorted({aware_time(row[time_column]) for row in rows})]
            condition = "site_id = ANY(%s) AND provider = %s AND " + time_column + " = ANY(%s)"
            if table == "weather_forecasts":
                condition += " AND issued_at = ANY(%s)"
                parameters.append(sorted({aware_time(row["issued_at"]) for row in rows}))
            stored = { _key(row, table): row for row in (
                dict(zip(columns, values)) for values in connection.execute(
                    f"SELECT {names} FROM public.{table} WHERE {condition}", parameters,
                ).fetchall())}
            for expected in rows:
                actual = stored.get(_key(expected, table))
                if actual is None:
                    raise ValueError(f"Missing post-load row in {table}")
                for column in columns:
                    left, right = actual[column], expected[column]
                    if column.endswith("_at"):
                        left, right = aware_time(left), aware_time(right)
                    if left != right:
                        raise ValueError(f"Weather post-load mismatch: {table} {column}")
