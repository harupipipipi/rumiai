from __future__ import annotations

from blocks._common import error, ok
from blocks.agent._state import get_engine


def run(input_data, context):
    """Resume a blocked or interrupted completion gate with new evidence."""

    execution_id = input_data.get("execution_id") if isinstance(input_data, dict) else None
    if not execution_id:
        return error("execution_id is required")
    engine = get_engine(execution_id)
    if engine is None:
        return error("execution not found")
    evidence = input_data.get("evidence") if isinstance(input_data, dict) else None
    return ok(engine.resume_completion_gate(execution_id, evidence=evidence))
