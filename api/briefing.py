"""
Next-day safety briefing for one site (Sperry brief, requirement 3).

    forecast rows ──> daily_facts()   code computes every number
    NWS alerts, score ──> context_facts()   tomorrow's warnings and the screening index
                 ──> Gemini           writes the words around those numbers
                 ──> grounded()       every number in the text must be a fact
                 ──> retry once, else template_briefing() (no AI wording)

Gemini never supplies a number. `grounded` pulls every number out of the
briefing and checks it against the facts we gave it, so a made-up temperature
or distance can't reach a crew member.
"""
from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from api import llm

ROOT = Path(__file__).resolve().parents[1]
LATEST_WEATHER = ROOT / "data" / "raw" / "weather" / "latest.json"
# Numbers the safety rules themselves use; always fine to mention.
RULE_NUMBERS = {"10", "30"}


# ---------------------------------------------------------------- inputs

def latest_forecasts() -> tuple[list[dict], str | None]:
    """Each site's newest forecast run: from Tiger Data if connected, else Sid's newest local run."""
    from api import db
    if db.configured():
        rows = db.query("""
            SELECT f.site_id, f.issued_at, f.valid_at, f.provider, f.temperature_f, f.heat_index_f,
                   f.wind_mph, f.precip_1h_in, f.precip_24h_in, f.soil_moisture,
                   f.source_name, f.source_url, f.retrieved_at
            FROM public.weather_forecasts f
            JOIN (SELECT site_id, MAX(issued_at) AS issued_at
                  FROM public.weather_forecasts GROUP BY site_id) newest
              ON newest.site_id = f.site_id AND newest.issued_at = f.issued_at
            ORDER BY f.site_id, f.valid_at""")
        return rows, max((r["issued_at"] for r in rows), default=None)
    try:
        report = json.loads(LATEST_WEATHER.read_text())
        run_dir = ROOT / report["output_directory"]
        return json.loads((run_dir / "weather-forecasts.json").read_text()), report.get("as_of")
    except (FileNotFoundError, KeyError, json.JSONDecodeError):
        return [], None


def _hour(dt: datetime) -> str:
    return dt.strftime("%-I %p")


def daily_facts(site: dict, rows: list[dict], for_date: date) -> dict | None:
    """Summarize one site-local calendar day of hourly forecast rows.

    Returns None if there's no forecast for that day. Missing measurements stay
    None ("no data"), never zero.
    """
    tz = ZoneInfo(site["timezone"])
    day = []
    for r in rows:
        if r["site_id"] != site["site_id"]:
            continue
        local = datetime.fromisoformat(r["valid_at"].replace("Z", "+00:00")).astimezone(tz)
        if local.date() == for_date:
            day.append((local, r))
    if not day:
        return None

    def peak(field):
        vals = [(r[field], t) for t, r in day if r.get(field) is not None]
        if not vals:
            return None, None
        v, t = max(vals, key=lambda p: p[0])
        return v, _hour(t)

    temp, temp_at = peak("temperature_f")
    heat, heat_at = peak("heat_index_f")
    wind, wind_at = peak("wind_mph")
    rain_hours = [(t, r["precip_1h_in"]) for t, r in day if r.get("precip_1h_in") is not None]
    rainy = [(t, p) for t, p in rain_hours if p >= 0.01]
    soil = [r["soil_moisture"] for _, r in day if r.get("soil_moisture") is not None]

    return {
        "site": site["name"],
        "date": for_date.strftime("%A, %B %-d"),
        "timezone": site["timezone"],
        "high_temp_f": round(temp) if temp is not None else None,
        "high_temp_at": temp_at,
        "max_heat_index_f": round(heat) if heat is not None else None,
        "max_heat_index_at": heat_at,
        "max_wind_mph": round(wind) if wind is not None else None,
        "max_wind_at": wind_at,
        "total_rain_in": round(sum(p for _, p in rain_hours), 2) if rain_hours else None,
        "rain_hours": len(rainy) if rain_hours else None,
        "first_rain_at": _hour(rainy[0][0]) if rainy else None,
        "max_soil_moisture": round(max(soil), 2) if soil else None,
        "forecast_hours": len(day),
        "forecast_source": day[0][1]["source_name"],
    }


def _event_name(title: str) -> str:
    """NWS headlines read "Freeze Warning issued October 17 at ..."; keep the event."""
    return title.split(" issued ")[0].strip()


def nws_for_day(site: dict, events: list[dict], for_date: date) -> str | None:
    """NWS alerts in effect during the site's local day, as plain text with local hours."""
    tz = ZoneInfo(site["timezone"])
    day_start = datetime.combine(for_date, datetime.min.time(), tz)
    day_end = day_start + timedelta(days=1)
    parts = []
    for e in sorted(events, key=lambda e: e["starts_at"]):
        if e["site_id"] != site["site_id"]:
            continue
        start = datetime.fromisoformat(e["starts_at"].replace("Z", "+00:00")).astimezone(tz)
        end = datetime.fromisoformat(e["ends_at"].replace("Z", "+00:00")).astimezone(tz) if e.get("ends_at") else None
        if start >= day_end or (end is not None and end <= day_start):
            continue
        if start <= day_start and (end is None or end >= day_end):
            when = "all day"
        elif start <= day_start:
            when = f"until {_hour(end)}"
        elif end is None or end >= day_end:
            when = f"from {_hour(start)}"
        else:
            when = f"{_hour(start)} to {_hour(end)}"
        text = f"{_event_name(e['title'])}, {when}"
        if text not in parts:  # NWS lists an update and its original separately
            parts.append(text)
    return "; ".join(parts) or None


def context_facts(site: dict, events: list[dict], for_date: date) -> dict:
    """Tomorrow's NWS alerts and the current screening index, alongside the weather facts."""
    sc = site.get("screening") or {}
    shown = sc.get("score") is not None
    return {
        "nws_alerts": nws_for_day(site, events, for_date),
        "screening_index_0_to_10": round(sc["score"], 1) if shown else None,
        "screening_status": {"validated_prototype": "validated prototype", "research": "research prototype"}.get(
            sc.get("status"), "not available"),
    }


# ---------------------------------------------------------------- grounding

_NUM = re.compile(r"(?<![\w.])\d+(?:\.\d+)?")


def _forms(value) -> set[str]:
    """Ways a fact may legitimately appear in text: 92, 92.0, 0.5, .5 -> '0.5'."""
    out = set()
    if isinstance(value, bool) or value is None:
        return out
    if isinstance(value, (int, float)):
        f = float(value)
        out |= {f"{f:g}", f"{f:.1f}", f"{f:.2f}", str(round(f))}
    elif isinstance(value, str):
        out |= set(_NUM.findall(value))
    return out


def allowed_numbers(facts: dict, alerts: list[dict]) -> set[str]:
    allowed = set(RULE_NUMBERS)
    for v in facts.values():
        allowed |= _forms(v)
    for a in alerts:
        allowed |= _forms((a.get("trigger") or {}).get("distance_mi"))
        allowed |= _forms(a.get("message"))
    return {n.lstrip("0") or "0" for n in allowed} | allowed


def grounded(text: str, facts: dict, alerts: list[dict]) -> list[str]:
    """Numbers in `text` that don't come from the facts. Empty list = grounded."""
    allowed = allowed_numbers(facts, alerts)
    bad = []
    for n in _NUM.findall(text):
        if n not in allowed and (n.lstrip("0") or "0") not in allowed:
            bad.append(n)
    return bad


# ---------------------------------------------------------------- writing

PROMPT = """Write a next-day safety briefing for a utility field crew at {site}.
It is read by supervisors at 6 PM the evening before work.

Rules:
- Use ONLY the facts below. Every number you write must appear in the facts exactly.
- If a fact is null, say that data is not available. Never estimate or round differently.
- Do not invent times, temperatures, distances, or chances of rain.
- 3 to 5 short sentences, plain language, no headings or bullet points.
- If nws_alerts is not null, name each National Weather Service alert and its hours first.
- screening_index_0_to_10 is a prototype index of how likely an NWS warning or heat advisory
  covers the plant in the next 24 hours. If it is not null, mention it once as the
  "prototype screening index"; never call it injury risk, a probability of harm, or an all-clear.
- An active alert (below) is in effect now; a lightning stop_work alert means work stops.
- End with one practical recommendation (start time, hydration, shelter, equipment).

Facts (JSON):
{facts}

Active alerts at the site right now (JSON, may be empty):
{alerts}"""


def template_briefing(facts: dict, alerts: list[dict]) -> str:
    """Plain wording straight from the facts; used if Gemini can't stay grounded."""
    def val(v, unit=""):
        return f"{v}{unit}" if v is not None else "not available"
    parts = [f"Forecast for {facts['site']} on {facts['date']}."]
    parts.append(f"High temperature {val(facts['high_temp_f'], '°F')}"
                 + (f" around {facts['high_temp_at']}" if facts['high_temp_at'] else "") + ".")
    if facts["max_heat_index_f"] is not None:
        parts.append(f"Heat index up to {facts['max_heat_index_f']}°F around {facts['max_heat_index_at']}.")
    parts.append(f"Strongest wind {val(facts['max_wind_mph'], ' mph')}"
                 + (f" around {facts['max_wind_at']}" if facts['max_wind_at'] else "") + ".")
    if facts["total_rain_in"]:
        parts.append(f"Rain totaling {facts['total_rain_in']} in, starting around {facts['first_rain_at']}.")
    elif facts["total_rain_in"] is not None:
        parts.append("No rain in the forecast.")
    if facts.get("nws_alerts"):
        parts.append(f"National Weather Service alerts: {facts['nws_alerts']}.")
    if any(a["hazard_type"] == "lightning" and a["level"] == "stop_work" for a in alerts):
        parts.append("A lightning stop-work alert is active now.")
    for a in alerts:
        if a["level"] == "warning":
            parts.append(f"Active warning: {a['message'].rstrip('.')}.")
    if facts.get("screening_index_0_to_10") is not None:
        parts.append(f"Prototype screening index {facts['screening_index_0_to_10']} out of 10 "
                     f"({facts['screening_status']}); it does not clear any alert.")
    return " ".join(parts)


def write_briefing(site: dict, facts: dict, alerts: list[dict]) -> dict:
    """Gemini briefing if it passes the grounding check (2 tries), else the template."""
    shown = [{k: a.get(k) for k in ("hazard_type", "level", "message")} for a in alerts]
    prompt = PROMPT.format(site=site["name"], facts=json.dumps(facts, indent=1), alerts=json.dumps(shown))
    problems: list[str] = []
    for attempt in (1, 2):
        try:
            text = llm.ask_text(prompt if attempt == 1 else
                                prompt + f"\n\nYour last draft used numbers that are not in the facts: {problems}. Remove them.")
        except llm.LLMError:
            break
        problems = grounded(text, facts, alerts)
        if not problems:
            return {"text": text, "method": "gemini", "attempts": attempt, "ungrounded": []}
    return {"text": template_briefing(facts, alerts), "method": "template",
            "attempts": 2 if problems else 0, "ungrounded": problems}


def briefing_sources(site: dict, rows: list[dict], events: list[dict], for_date: date) -> list[dict]:
    """Retain supplied evidence for this site/day; never ask the LLM for URLs."""
    tz = ZoneInfo(site["timezone"])
    sources = {}
    applicable = [r for r in rows if r["site_id"] == site["site_id"]
                  and datetime.fromisoformat(r["valid_at"].replace("Z", "+00:00")).astimezone(tz).date() == for_date]
    applicable += [e for e in events if nws_for_day(site, [e], for_date)]
    for row in applicable:
        url = row.get("source_url")
        if not isinstance(url, str):
            continue
        try:
            parsed = urlsplit(url)
            valid = parsed.scheme in {"https", "http"} and parsed.hostname and not parsed.username and not parsed.password
        except ValueError:
            valid = False
        if valid:
            sources.setdefault(url, {"source_name": row.get("source_name") or "Source", "source_url": url})
    return list(sources.values())


def briefing_for(site: dict, rows: list[dict], alerts: list[dict], now: datetime | None = None,
                 events: list[dict] | None = None) -> dict | None:
    """Contract-shaped briefing for the site's next local day, or None without forecasts.

    events: live NWS rows from environmental_events (event_kind nws_*), any site.
    """
    now = now or datetime.now(timezone.utc)
    tomorrow = now.astimezone(ZoneInfo(site["timezone"])).date() + timedelta(days=1)
    facts = daily_facts(site, rows, tomorrow)
    if facts is None:
        return None
    facts |= context_facts(site, events or [], tomorrow)
    result = write_briefing(site, facts, [a for a in alerts if a["site_id"] == site["site_id"]])
    first = min((r["valid_at"] for r in rows if r["site_id"] == site["site_id"]), default=None)
    return {
        "site_id": site["site_id"],
        "for_date": tomorrow.isoformat(),
        "generated_at": now.isoformat(timespec="seconds").replace("+00:00", "Z"),
        "text": result["text"],
        "inputs": {"forecast_valid_from": first,
                   "score_scored_at": (site.get("screening") or {}).get("scored_at"),
                   "method": result["method"], "facts": facts,
                   "sources": briefing_sources(site, rows, events or [], tomorrow)},
    }
