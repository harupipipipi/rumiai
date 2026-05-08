from __future__ import annotations


def deliver(job: dict, result: dict) -> dict:
    return {"target": job.get("deliver", "local"), "delivered": True, "result": result}
