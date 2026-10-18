"""
POST /ask: a plain-English question about our data (Sperry brief, requirement 6).

    question ──> Gemini writes one SELECT        (write_sql)
             ──> Sid's guarded executor runs it  (db.ask_query: planit_ask login,
                                                  allowlisted tables, read-only,
                                                  5 s timeout, 100 rows max)
             ──> Gemini answers from the rows    (write_answer)
             ──> number check: every number in the answer must be in the rows,
                 else a plain listing of the rows (no AI wording)

Gemini never touches the database directly and never supplies a number. The
SQL runs only under the restricted planit_ask login, never the app's write
login, so a bad query can't change data or read crew reports.
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime, timezone
from decimal import Decimal

import psycopg
from pydantic import BaseModel

from api import llm
from api.briefing import _NUM, _forms
from db import ask_query
from db.access import ALLOWED

MAX_ROWS_TO_MODEL = 40
MAX_SOURCES = 5


class AskUnavailable(RuntimeError):
    """The /ask login, database, or Gemini is down: a service error, not an answer."""


# What Gemini needs to write SQL. Only tables the planit_ask login can read.
SCHEMA = """
Tables (PostgreSQL, schema public). Times are UTC timestamptz.

sites: one row per power plant. site_id (EIA plant ID), name, utility, state (2-letter),
  county, latitude, longitude, timezone, plant_type, hazard_region, is_monitored (use
  WHERE is_monitored), source_name, source_url
weather_readings: observed weather. site_id, observed_at, temperature_f, heat_index_f,
  wind_mph, precip_1h_in, precip_24h_in, soil_moisture, source_name, source_url
weather_forecasts: hourly forecasts. site_id, issued_at, valid_at (the hour forecast),
  temperature_f, heat_index_f, wind_mph, precip_1h_in, precip_24h_in, soil_moisture,
  source_name, source_url. Use the newest issued_at per site.
screening_predictions: hazard screening index, 0-10 = 10 x model probability that an
  NWS warning or heat advisory covers the plant in the next 24 hours. site_id,
  scored_at, score, baseline, status ('research' = prototype), target. Use the newest
  scored_at per site. This is NOT an injury probability.
alerts: safety alerts. id, site_id, hazard_type (lightning, heat, flooding, wildfire,
  soil_saturation, wildlife, other), level (warning, stop_work), message, started_at,
  clear_at, ended_at (NULL = still active)
environmental_events: site_id, hazard_type, event_kind, title, severity, starts_at, ends_at,
  source_name, source_url. Live National Weather Service alerts have event_kind LIKE 'nws_%'
  (nws_warning, nws_advisory, nws_watch, nws_statement); 'historical_storm_event' rows are past
  storm records. For "active" or "current" NWS alerts, select ends_at > now() (or NULL) and
  include starts_at, so alerts starting soon are listed too and can be called upcoming.
"""

SQL_PROMPT = """You turn a question about utility power plant safety data into ONE PostgreSQL SELECT.
{schema}
Rules:
- Exactly one SELECT. No WITH/CTEs, no semicolons, no comments, no writes.
- Always write table names as public.<table>. Only the tables above.
- Allowed functions only: count, sum, avg, min, max, abs, round, date_trunc, extract,
  date_part, now, greatest, least, coalesce. No JSON operators.
- For "latest"/"current" values (scores, readings), take the newest row per site with
  DISTINCT ON (site_id) ... ORDER BY site_id, <time> DESC inside a subquery.
- For forecasts over a period ("tomorrow", "next 24 hours"), use the newest run, written
  flat like this example (no derived tables):
    SELECT s.name, max(f.wind_mph) AS max_wind_mph
    FROM public.weather_forecasts f JOIN public.sites s ON s.site_id = f.site_id
    WHERE f.issued_at = (SELECT max(issued_at) FROM public.weather_forecasts)
      AND f.valid_at >= now() AND f.valid_at < now() + interval '24 hours'
    GROUP BY s.name ORDER BY max_wind_mph DESC NULLS LAST LIMIT 5
- Join to public.sites for plant names. Include source_name and source_url columns when
  the table has them and the query is not an aggregate.
- Keep the query flat (the safety check rejects deep nesting): join tables directly in the
  main FROM, use at most one subquery, and never put a subquery inside another subquery.
- Keep results small: ORDER BY the most relevant column and LIMIT 20 or fewer.
- Measurements can be NULL (no data; heat_index_f is only set when it's hot). When ranking
  by a measurement, filter "<column> IS NOT NULL" and sort with NULLS LAST, including
  inside DISTINCT ON subqueries.
- If the data above cannot answer the question, return sql = null.

Question: {question}"""

ANSWER_PROMPT = """Answer a utility supervisor's question using ONLY the query result below.

Rules:
- Every number you write must appear in the result rows exactly as given (you may round
  to the shown decimals). Do not compute new numbers, percentages, or averages.
- 1 to 4 short plain sentences. Name plants by name and include the key values.
- Write units in plain words (°F, mph, inches), never column names like wind_mph.
- null means no data: say so, never treat it as zero.
- A screening score is a 0-10 prototype index of NWS warning/advisory likelihood, not an
  injury probability. Say "prototype" when you mention it.
- If the result is empty, say no matching records were found. If it has fewer rows than
  the question asked for, say only that many matched.
{truncated}
Question: {question}
SQL: {sql}
Result rows (JSON): {rows}"""


class _SQL(BaseModel):
    sql: str | None


class _Answer(BaseModel):
    answer: str


# Where a table's facts come from, for tables that don't store a source per row.
PROVENANCE = {
    "screening_predictions": {"label": "ForeSite screening model (research prototype)",
                              "url": "https://github.com/fanggs/planit-control/blob/main/model/README.md"},
    "alerts": {"label": "NOAA GOES GLM lightning, 10-mile / 30-minute rule",
               "url": "https://www.goes-r.gov/spacesegment/glm.html"},
}
SOURCED_TABLES = ("sites", "weather_readings", "weather_forecasts", "environmental_events")


# ---------------------------------------------------------------- helpers

def _plain(value):
    if isinstance(value, (Decimal, float)):
        return round(float(value), 2)  # model output precision beyond this is noise
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    if isinstance(value, date):
        return value.isoformat()
    return value


def tables_in(sql: str) -> list[str]:
    return [t for t in ALLOWED if re.search(rf"\bpublic\.{t}\b", sql, re.IGNORECASE)]


def ungrounded(text: str, rows: list[dict], question: str) -> list[str]:
    """Numbers in the answer that aren't in the rows (or the question)."""
    allowed = {str(len(rows))} | set(_NUM.findall(question))
    for row in rows:
        for v in row.values():
            allowed |= _forms(v)
            if isinstance(v, str):  # every digit group, so "T02:00" allows the hour "2"
                allowed |= set(re.findall(r"\d+", v))
    allowed |= {n.lstrip("0") or "0" for n in allowed}
    return [n for n in _NUM.findall(text) if n not in allowed and (n.lstrip("0") or "0") not in allowed]


def listing(rows: list[dict], truncated: bool) -> str:
    """Plain answer straight from the rows, used if Gemini's wording isn't grounded."""
    if not rows:
        return "No matching records were found."
    shown = rows[:5]
    lines = ["; ".join(f"{k}: {v}" for k, v in r.items() if k not in ("source_url",)) for r in shown]
    more = len(rows) - len(shown)
    tail = f" (and {more} more{'+' if truncated else ''} rows)" if more or truncated else ""
    return " | ".join(lines) + tail


# ---------------------------------------------------------------- steps

def write_sql(question: str, problem: str | None = None) -> str | None:
    prompt = SQL_PROMPT.format(schema=SCHEMA, question=question)
    if problem:
        prompt += f"\n\nYour last query was rejected: {problem}. Write a corrected query."
    return llm.ask_json(prompt, _SQL).sql


def run(sql: str) -> dict:
    """Execute through the restricted login. Guard/SQL errors raise ValueError."""
    try:
        conn = ask_query.connect()
    except (ValueError, psycopg.Error) as e:  # not configured, or can't connect
        raise AskUnavailable("The /ask database login is unavailable") from e
    try:
        with conn:
            result = ask_query.execute(conn, sql)
    except psycopg.OperationalError as e:
        raise AskUnavailable("The /ask database connection dropped") from e
    except psycopg.Error as e:  # bad column, type error, timeout: the query's fault
        raise ValueError(type(e).__name__) from e
    result["rows"] = [{k: _plain(v) for k, v in r.items()} for r in result["rows"]]
    return result


def sources(sql: str, rows: list[dict]) -> list[dict]:
    out: dict[str, str] = {}
    for r in rows:
        if r.get("source_name") and r.get("source_url"):
            out.setdefault(r["source_name"], r["source_url"])
    for t in tables_in(sql):
        if t in PROVENANCE:
            out.setdefault(PROVENANCE[t]["label"], PROVENANCE[t]["url"])
        elif t in SOURCED_TABLES and not any("source_name" in r for r in rows):
            # The query didn't select its sources: read them from the same table.
            stored = run(f"SELECT source_name, min(source_url) AS source_url FROM public.{t} GROUP BY source_name")
            for s in stored["rows"]:
                out.setdefault(s["source_name"], s["source_url"])
    return [{"label": k, "url": v} for k, v in list(out.items())[:MAX_SOURCES]]


def write_answer(question: str, sql: str, rows: list[dict], truncated: bool) -> str:
    note = "- The result was cut off at 100 rows; say the list may be incomplete." if truncated else ""
    prompt = ANSWER_PROMPT.format(question=question, sql=sql, truncated=note,
                                  rows=json.dumps(rows[:MAX_ROWS_TO_MODEL], default=str))
    problems: list[str] = []
    for attempt in (1, 2):
        text = llm.ask_json(prompt if attempt == 1 else
                            prompt + f"\n\nYour last answer used numbers not in the rows: {problems}. Remove them.",
                            _Answer).answer.strip()
        problems = ungrounded(text, rows, question)
        if not problems:
            return text
    return listing(rows, truncated)


# ---------------------------------------------------------------- entry point

def answer(question: str) -> dict:
    """Contract response: {answer, sql, sources} or {answer: null, reason: cannot_answer}."""
    try:
        sql, problem = None, None
        for _ in (1, 2, 3):  # retries if the guard or database rejects the query
            sql = write_sql(question, problem)
            if not sql:
                return {"answer": None, "reason": "cannot_answer"}
            try:
                result = run(sql)
                break
            except ValueError as e:
                problem = str(e)
        else:
            return {"answer": None, "reason": "cannot_answer"}
        rows = result["rows"]
        return {"answer": write_answer(question, sql, rows, result["truncated"]),
                "sql": sql, "sources": sources(sql, rows)}
    except llm.LLMError as e:
        raise AskUnavailable("The question service is unavailable") from e
