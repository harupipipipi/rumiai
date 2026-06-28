"""
domain/agent/schedule_store.py - Schedule persistence layer

Stores and loads schedule definitions as individual JSON files
under user_data/shared/schedules/.
Each schedule is stored as {schedule_id}.json.
Execution history is stored as {schedule_id}_history.json.
"""

import json
import os
import threading


_SCHEDULES_DIR = os.path.join("user_data", "shared", "schedules")
_lock = threading.Lock()


def _schedules_dir():
    override = os.environ.get("RUMI_DEFAULTSPACK_AGENT_SCHEDULES_DIR", "").strip()
    if override:
        return override
    return _SCHEDULES_DIR


def current_schedules_dir():
    """Return the absolute directory currently used for schedule persistence."""
    return os.path.abspath(_schedules_dir())


def _sanitize_json_text(value):
    if isinstance(value, str):
        return value.encode("utf-8", errors="replace").decode("utf-8")
    if isinstance(value, list):
        return [_sanitize_json_text(item) for item in value]
    if isinstance(value, dict):
        return {
            _sanitize_json_text(key): _sanitize_json_text(item)
            for key, item in value.items()
        }
    return value


def _ensure_dir():
    """Create the schedules directory if it does not exist."""
    schedules_dir = _schedules_dir()
    if not os.path.isdir(schedules_dir):
        os.makedirs(schedules_dir, exist_ok=True)


def _schedule_path(schedule_id):
    """Return the file path for a given schedule ID."""
    return os.path.join(_schedules_dir(), schedule_id + ".json")


def _history_path(schedule_id):
    """Return the file path for a given schedule's execution history."""
    return os.path.join(_schedules_dir(), schedule_id + "_history.json")


def save_schedule(schedule_dict):
    """Persist a schedule dict to disk. Overwrites if exists."""
    _ensure_dir()
    sid = schedule_dict.get("id")
    if not sid:
        raise ValueError("schedule dict must have an 'id' field")
    path = _schedule_path(sid)
    with _lock:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(_sanitize_json_text(schedule_dict), f, ensure_ascii=False, indent=2)


def load_schedule(schedule_id):
    """Load a single schedule from disk. Returns None if not found."""
    path = _schedule_path(schedule_id)
    with _lock:
        if not os.path.isfile(path):
            return None
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)


def delete_schedule(schedule_id):
    """Remove a schedule file from disk. Returns True if deleted, False if not found."""
    path = _schedule_path(schedule_id)
    hist = _history_path(schedule_id)
    with _lock:
        found = False
        if os.path.isfile(path):
            os.remove(path)
            found = True
        if os.path.isfile(hist):
            os.remove(hist)
        return found


def load_all_schedules():
    """Load all schedule dicts from disk. Returns a list."""
    _ensure_dir()
    results = []
    with _lock:
        schedules_dir = _schedules_dir()
        for fname in os.listdir(schedules_dir):
            if fname.endswith(".json") and not fname.endswith("_history.json"):
                fpath = os.path.join(schedules_dir, fname)
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    results.append(data)
                except (json.JSONDecodeError, OSError):
                    continue
    return results


def append_history(schedule_id, entry):
    """Append an execution history entry for a schedule.

    entry is a dict with at minimum: execution_id, started_at, status.
    History is capped at 200 entries (oldest trimmed).
    """
    _ensure_dir()
    path = _history_path(schedule_id)
    max_entries = 200
    with _lock:
        history = []
        if os.path.isfile(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    history = json.load(f)
            except (json.JSONDecodeError, OSError):
                history = []
        if not isinstance(history, list):
            history = []
        history.append(entry)
        if len(history) > max_entries:
            history = history[-max_entries:]
        with open(path, "w", encoding="utf-8") as f:
            json.dump(_sanitize_json_text(history), f, ensure_ascii=False, indent=2)


def load_history(schedule_id, limit=50, offset=0):
    """Load execution history for a schedule. Returns (entries, total_count)."""
    path = _history_path(schedule_id)
    with _lock:
        if not os.path.isfile(path):
            return [], 0
        try:
            with open(path, "r", encoding="utf-8") as f:
                history = json.load(f)
        except (json.JSONDecodeError, OSError):
            return [], 0
    if not isinstance(history, list):
        return [], 0
    total = len(history)
    # Return in reverse chronological order
    reversed_hist = list(reversed(history))
    page = reversed_hist[offset:offset + limit]
    return page, total
