"""block: blocks.agent.scheduler.trigger

Manually trigger a scheduled agent execution immediately.

input_data:
    schedule_id : str  (required)
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from blocks._common import ok, error
from domain.agent.scheduler import Scheduler


def _trigger_failure_response(history_entry):
    """Return a failing HTTP envelope for a failed manual start."""
    error_message = str(history_entry.get("error") or "schedule execution failed")
    response = error(
        "schedule trigger failed: " + error_message,
        "SCHEDULE_TRIGGER_FAILED",
    )
    response["data"] = {
        "history_entry": history_entry,
        "cause_code": history_entry.get("error_code"),
    }
    response["_http_status"] = (
        409
        if history_entry.get("error_code")
        in {
            "NOT_FOUND",
            "CONVERSATION_RUNNING",
            "ALREADY_RUNNING",
            "SCHEDULE_EXECUTION_CANCELLED",
            "SCHEDULE_EXECUTION_SUPERSEDED",
        }
        else 500
    )
    return response


def run(input_data, context):
    schedule_id = input_data.get("schedule_id") if isinstance(input_data, dict) else None
    if not schedule_id:
        return error("schedule_id is required")

    try:
        scheduler = Scheduler()
        history_entry = scheduler.trigger_now(schedule_id)
    except Exception as exc:
        return error("failed to trigger schedule: " + str(exc), "INTERNAL_ERROR")

    if history_entry is None:
        return error("schedule not found: " + schedule_id, "NOT_FOUND")

    if history_entry.get("trigger") == "manual" and history_entry.get("status") == "error":
        return _trigger_failure_response(history_entry)

    return ok(history_entry)
