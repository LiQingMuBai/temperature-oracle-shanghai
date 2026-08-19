#!/usr/bin/env python3
"""Current-day ZSPD METAR observations from the official Aviation Weather API."""
import datetime as dt
import json
import subprocess
from zoneinfo import ZoneInfo


def current_day_max(target_date, now=None):
    raw = subprocess.check_output([
        "curl", "-fsS", "--max-time", "25", "-A", "Mozilla/5.0 temperature-oracle",
        "https://aviationweather.gov/api/data/metar?ids=ZSPD&format=json&hours=30"], timeout=30)
    records = json.loads(raw)
    local_tz = ZoneInfo("Asia/Shanghai")
    current = now or dt.datetime.now(dt.timezone.utc)
    same_day = []
    for row in records:
        stamp = dt.datetime.fromisoformat(row["reportTime"].replace("Z", "+00:00"))
        if stamp.astimezone(local_tz).date().isoformat() == target_date and row.get("temp") is not None:
            same_day.append((stamp, float(row["temp"])))
    if not same_day:
        return None
    latest = max(stamp for stamp, _ in same_day)
    age_hours = (current.astimezone(dt.timezone.utc) - latest).total_seconds() / 3600
    return {"max_temp_c": max(value for _, value in same_day),
            "latest_observation_at": latest.isoformat(), "age_hours": age_hours,
            "observation_count": len(same_day),
            "source": "NOAA Aviation Weather METAR API (ZSPD)"}
