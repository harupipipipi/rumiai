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
    original = str(schedule or "").strip()
    text = original.lower()
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
    raise ValueError(f"unsupported schedule syntax: {original or '<empty>'}")


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
    return len(text.split()) == 5


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
    minute_expr, hour_expr, day_expr, month_expr, weekday_expr = text.split()
    minutes = _parse_cron_values(minute_expr, 0, 59, "minute")
    hours = _parse_cron_values(hour_expr, 0, 23, "hour")
    days = _parse_cron_values(day_expr, 1, 31, "day-of-month")
    months = _parse_cron_values(month_expr, 1, 12, "month")
    weekdays = _parse_cron_weekdays(weekday_expr)
    day_is_any = day_expr == "*"
    weekday_is_any = weekday_expr == "*"
    candidate = now.replace(second=0, microsecond=0) + timedelta(minutes=1)
    for _ in range(366 * 24 * 60 * 5):
        day_matches = candidate.day in days
        weekday_matches = candidate.weekday() in weekdays
        if day_is_any and weekday_is_any:
            calendar_day_matches = True
        elif day_is_any:
            calendar_day_matches = weekday_matches
        elif weekday_is_any:
            calendar_day_matches = day_matches
        else:
            # Match common cron behavior: day-of-month and day-of-week are ORed
            # when both are restricted.
            calendar_day_matches = day_matches or weekday_matches
        if (
            candidate.minute in minutes
            and candidate.hour in hours
            and candidate.month in months
            and calendar_day_matches
        ):
            return candidate
        candidate += timedelta(minutes=1)
    raise ValueError(f"cron schedule has no next run within five years: {text}")


def _parse_cron_values(expr: str, minimum: int, maximum: int, field_name: str) -> set[int]:
    expr = str(expr or "").strip()
    if not expr:
        raise ValueError(f"empty cron {field_name} field")
    values: set[int] = set()
    for raw_part in expr.split(","):
        part = raw_part.strip()
        if not part:
            raise ValueError(f"empty cron {field_name} list item")
        base, step = _split_cron_step(part, field_name)
        if base == "*":
            start, end = minimum, maximum
        elif "-" in base:
            start_text, end_text = base.split("-", 1)
            start = _parse_cron_int(start_text, minimum, maximum, field_name)
            end = _parse_cron_int(end_text, minimum, maximum, field_name)
            if end < start:
                raise ValueError(f"unsupported wrapping cron {field_name} range: {part}")
        else:
            start = end = _parse_cron_int(base, minimum, maximum, field_name)
        values.update(range(start, end + 1, step))
    if not values:
        raise ValueError(f"cron {field_name} field matched no values")
    return values


def _split_cron_step(part: str, field_name: str) -> tuple[str, int]:
    if "/" not in part:
        return part, 1
    base, step_text = part.split("/", 1)
    if not base:
        raise ValueError(f"unsupported cron {field_name} step: {part}")
    try:
        step = int(step_text)
    except ValueError as exc:
        raise ValueError(f"invalid cron {field_name} step: {part}") from exc
    if step <= 0:
        raise ValueError(f"cron {field_name} step must be positive: {part}")
    return base, step


def _parse_cron_int(value: str, minimum: int, maximum: int, field_name: str) -> int:
    try:
        number = int(value)
    except ValueError as exc:
        raise ValueError(f"invalid cron {field_name} value: {value}") from exc
    if number < minimum or number > maximum:
        raise ValueError(f"cron {field_name} value out of range: {number}")
    return number


def _parse_cron_weekdays(expr: str) -> set[int]:
    raw_values = _parse_cron_values(expr, 0, 7, "day-of-week")
    weekdays = set()
    for value in raw_values:
        # Cron accepts both 0 and 7 as Sunday; Python uses Monday=0.
        weekdays.add(6 if value in {0, 7} else value - 1)
    return weekdays
