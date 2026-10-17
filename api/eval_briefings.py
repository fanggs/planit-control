"""
Grounding eval for the briefing writer.

Runs the real briefing pipeline (real forecasts, real Gemini) across sites
from every hazard region and reports how often Gemini's text passes the
grounding check on the first try, after the retry, or falls back to the
template. A briefing that reaches users is always grounded; this measures how
often Gemini gets there on its own.

    .venv/bin/python -m api.eval_briefings            # 3 sites per region
    .venv/bin/python -m api.eval_briefings --per-region 10
"""
from __future__ import annotations

import argparse
import json
import os
import time
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from api.briefing import daily_facts, grounded, latest_forecasts, write_briefing
from api.site_data import ROOT, load_sites


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--per-region", type=int, default=3)
    args = parser.parse_args()
    for line in (ROOT / ".env").read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

    rows, as_of = latest_forecasts()
    by_region = defaultdict(list)
    for s in load_sites():
        by_region[s["hazard_region"]].append(s)
    sites = [s for region in sorted(by_region) for s in by_region[region][: args.per_region]]

    now = datetime.now(timezone.utc)
    outcomes, failures, times = Counter(), [], []
    for site in sites:
        tomorrow = now.astimezone(ZoneInfo(site["timezone"])).date() + timedelta(days=1)
        facts = daily_facts(site, rows, tomorrow)
        if facts is None:
            outcomes["no forecast"] += 1
            continue
        t = time.time()
        result = write_briefing(site, facts, [])
        times.append(time.time() - t)
        key = "template fallback" if result["method"] == "template" else f"gemini, try {result['attempts']}"
        outcomes[key] += 1
        if result["ungrounded"]:
            failures.append({"site": site["name"], "ungrounded": result["ungrounded"]})
        assert not grounded(result["text"], facts, []), "a delivered briefing must be grounded"
        print(f"  {site['hazard_region']:20} {site['name'][:28]:28} -> {key}", flush=True)

    total = sum(v for k, v in outcomes.items() if k != "no forecast")
    first = outcomes.get("gemini, try 1", 0)
    print(f"\nforecast run: {as_of} | model: {os.environ.get('GEMINI_MODEL')}")
    print(f"briefings: {total} | grounded on first try: {first}/{total} ({first / max(total, 1):.0%})")
    print("outcomes:", dict(outcomes))
    if times:
        print(f"avg time per briefing: {sum(times) / len(times):.1f}s")
    if failures:
        print("numbers Gemini invented (caught):", json.dumps(failures))
    print("delivered briefings grounded: 100% (checked)")


if __name__ == "__main__":
    main()
