from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def parse_next_run(schedule: str, *, now: datetime | None = None) -> datetime:
    now = now or utc_now()
    text = str(schedule or "").strip().lower()
    if not text or text in {"now", "once", "one_shot"}:
        return now
    match = re.match(r"every\s+(\d+)\s*([smhd])", text)
    if match:
        amount = int(match.group(1))
        unit = match.group(2)
        if unit == "s":
            return now + timedelta(seconds=amount)
        if unit == "m":
            return now + timedelta(minutes=amount)
        if unit == "h":
            return now + timedelta(hours=amount)
        return now + timedelta(days=amount)
    if text.startswith("interval:"):
        return parse_next_run("every " + text.split(":", 1)[1], now=now)
    if _looks_like_cron(text):
        minute, hour, *_ = text.split()
        candidate = now.replace(second=0, microsecond=0)
        if minute != "*":
            candidate = candidate.replace(minute=int(minute))
        if hour != "*":
            candidate = candidate.replace(hour=int(hour))
        if candidate <= now:
            candidate += timedelta(days=1 if hour != "*" else 1 if minute != "*" else 0, minutes=1 if minute == "*" else 0)
        return candidate
    return now


def is_due(next_run_at: str, *, now: datetime | None = None) -> bool:
    if not next_run_at:
        return True
    now = now or utc_now()
    try:
        value = datetime.fromisoformat(next_run_at.replace("Z", "+00:00"))
    except ValueError:
        return True
    return value <= now


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _looks_like_cron(text: str) -> bool:
    parts = text.split()
    return len(parts) == 5 and all(part == "*" or part.isdigit() for part in parts[:2])
