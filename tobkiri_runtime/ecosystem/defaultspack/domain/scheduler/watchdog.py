from __future__ import annotations


def watchdog_result(result: dict) -> dict:
    return {
        "ok": result.get("status") == "completed",
        "returncode": result.get("returncode"),
        "stderr": result.get("stderr", ""),
    }
