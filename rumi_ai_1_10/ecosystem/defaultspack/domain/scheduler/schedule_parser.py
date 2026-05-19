from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone


_WEEKDAYS = {
    "mon": 0,
    "monday": 0,
    "月": 0,
    "月曜": 0,
    "月曜日": 0,
    "tue": 1,
    "tuesday": 1,
    "火": 1,
    "火曜": 1,
    "火曜日": 1,
    "wed": 2,
    "wednesday": 2,
    "水": 2,
    "水曜": 2,
    "水曜日": 2,
    "thu": 3,
    "thursday": 3,
    "木": 3,
    "木曜": 3,
    "木曜日": 3,
    "fri": 4,
    "friday": 4,
    "金": 4,
    "金曜": 4,
    "金曜日": 4,
    "sat": 5,
    "saturday": 5,
    "土": 5,
    "土曜": 5,
    "土曜日": 5,
    "sun": 6,
    "sunday": 6,
    "日": 6,
    "日曜": 6,
    "日曜日": 6,
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def parse_next_run(schedule: str, *, now: datetime | None = None) -> datetime:
    now = now or utc_now()
    text = str(schedule or "").strip().lower()
    if not text or text in {"now", "once", "one_shot"}:
        return now
    match = re.match(r"(?:in|after)\s+(\d+)\s*([smhd])", text)
    if match:
        return _add_interval(now, int(match.group(1)), match.group(2))
    match = re.match(r"every\s+(\d+)\s*([smhd])", text)
    if match:
        return _add_interval(now, int(match.group(1)), match.group(2))
    match = re.match(r"every\s+([a-z\u3040-\u30ff\u3400-\u9fff]+)(?:\s+at)?\s+(\d{1,2})(?::(\d{2}))?", text)
    if match and match.group(1) in _WEEKDAYS:
        return _next_weekly(now, _WEEKDAYS[match.group(1)], int(match.group(2)), int(match.group(3) or 0))
    if text.startswith("interval:"):
        return parse_next_run("every " + text.split(":", 1)[1], now=now)
    if _looks_like_cron(text):
        return _next_cron(text, now)
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
    return len(parts) == 5 and all(_cron_part_supported(part) for part in parts)


def _cron_part_supported(part: str) -> bool:
    return part == "*" or part.isdigit() or "," in part


def _add_interval(now: datetime, amount: int, unit: str) -> datetime:
    if unit == "s":
        return now + timedelta(seconds=amount)
    if unit == "m":
        return now + timedelta(minutes=amount)
    if unit == "h":
        return now + timedelta(hours=amount)
    return now + timedelta(days=amount)


def _next_weekly(now: datetime, weekday: int, hour: int, minute: int) -> datetime:
    hour = max(0, min(hour, 23))
    minute = max(0, min(minute, 59))
    candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    days = (weekday - candidate.weekday()) % 7
    candidate = candidate + timedelta(days=days)
    if candidate <= now:
        candidate += timedelta(days=7)
    return candidate


def _next_cron(text: str, now: datetime) -> datetime:
    minute_expr, hour_expr, _day_expr, _month_expr, weekday_expr = text.split()
    candidate = now.replace(second=0, microsecond=0) + timedelta(minutes=1)
    for _ in range(366 * 24 * 60):
        if (
            _matches_cron_value(candidate.minute, minute_expr)
            and _matches_cron_value(candidate.hour, hour_expr)
            and _matches_cron_weekday(candidate.weekday(), weekday_expr)
        ):
            return candidate
        candidate += timedelta(minutes=1)
    return now + timedelta(days=1)


def _matches_cron_value(value: int, expr: str) -> bool:
    if expr == "*":
        return True
    options = {int(part) for part in expr.split(",") if part.isdigit()}
    return value in options


def _matches_cron_weekday(value: int, expr: str) -> bool:
    if expr == "*":
        return True
    # Cron accepts both 0 and 7 as Sunday; Python uses Monday=0.
    cron_value = (value + 1) % 7
    options = {int(part) for part in expr.split(",") if part.isdigit()}
    return cron_value in options or (cron_value == 0 and 7 in options)
