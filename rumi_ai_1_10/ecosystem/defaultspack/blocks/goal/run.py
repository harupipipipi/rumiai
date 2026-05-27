"""/goal slash command implementation.

Drives a goal-pursuit loop with two roles:

* a *Worker* agent that produces the next concrete contribution toward the goal;
* a third-party *Evaluator* agent that, after each Worker turn, decides whether
  the goal has been achieved and otherwise emits the next instruction.

The loop runs until the evaluator confirms the goal is achieved or until a hard
iteration cap is reached. The block is invoked via the ``pack_block`` slash
command execution type, so it lives entirely as file additions under
``blocks/goal/`` (no existing-file modifications required to add the feature).
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any

# blocks/_common is colocated with this package; the parent imports here mirror
# the convention used by every other block module in the pack.
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from blocks._common import error, ok  # noqa: E402  (import after sys.path tweak)
from domain.ai_client.model_call import call_model  # noqa: E402

DEFAULT_MAX_ITERATIONS = 5
HARD_MAX_ITERATIONS = 20

WORKER_SYSTEM_PROMPT = (
    "You are a Worker agent pursuing a user-defined goal. "
    "Each turn, produce the next concrete contribution toward the goal. "
    "Be direct and produce actionable output, not meta-commentary."
)

EVALUATOR_SYSTEM_PROMPT = (
    "You are an independent third-party Evaluator. "
    "Decide whether the Worker has achieved the stated goal yet. "
    "Reply with strict JSON only matching the schema: "
    '{"achieved": bool, "reason": string, "next_instruction": string}. '
    "If achieved is true, next_instruction may be empty. "
    "If achieved is false, next_instruction must tell the Worker exactly what "
    "to do next."
)

EVALUATOR_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "achieved": {"type": "boolean"},
        "reason": {"type": "string"},
        "next_instruction": {"type": "string"},
    },
    "required": ["achieved"],
}


def run(input_data: Any = None, context: Any = None) -> dict[str, Any]:
    data = input_data if isinstance(input_data, dict) else {}
    goal = str(data.get("goal") or "").strip()
    if not goal:
        return error("goal is required", "MISSING_PARAM")

    max_iterations = _coerce_iterations(data.get("max_iterations"))
    worker_model = str(data.get("worker_model") or data.get("model") or "").strip()
    evaluator_model = str(data.get("evaluator_model") or data.get("model") or "").strip()

    call_handler = None
    if isinstance(context, dict):
        call_handler = context.get("call_handler")

    iterations: list[dict[str, Any]] = []
    next_instruction = goal
    final_output = ""
    achieved = False
    reason = ""

    for index in range(max_iterations):
        worker_response = _call_worker(
            goal,
            iterations,
            next_instruction,
            worker_model,
            call_handler,
        )
        if not _is_ok_response(worker_response):
            iterations.append(
                {
                    "iteration": index + 1,
                    "phase": "worker_error",
                    "error": _response_error_payload(worker_response),
                }
            )
            return _failure_with_iterations(
                "worker model call failed",
                "WORKER_FAILED",
                iterations,
            )

        worker_output = _response_text(worker_response)
        final_output = worker_output

        evaluator_response = _call_evaluator(
            goal,
            worker_output,
            evaluator_model,
            call_handler,
        )
        if not _is_ok_response(evaluator_response):
            iterations.append(
                {
                    "iteration": index + 1,
                    "worker_output": worker_output,
                    "phase": "evaluator_error",
                    "error": _response_error_payload(evaluator_response),
                }
            )
            return _failure_with_iterations(
                "evaluator model call failed",
                "EVALUATOR_FAILED",
                iterations,
            )

        verdict = _parse_verdict(evaluator_response.get("output"))
        achieved = bool(verdict.get("achieved"))
        reason = str(verdict.get("reason") or "")
        next_instruction = str(verdict.get("next_instruction") or "")

        iterations.append(
            {
                "iteration": index + 1,
                "worker_output": worker_output,
                "verdict": verdict,
            }
        )

        if achieved:
            break
        if not next_instruction:
            next_instruction = (
                "Continue working toward the goal. Produce more concrete progress."
            )

    return ok(
        {
            "goal": goal,
            "achieved": achieved,
            "reason": reason,
            "iterations": iterations,
            "iteration_count": len(iterations),
            "final_output": final_output,
            "max_iterations": max_iterations,
            "stopped_reason": "achieved" if achieved else "max_iterations_reached",
        }
    )


def _coerce_iterations(value: Any) -> int:
    try:
        parsed = int(value) if value not in (None, "") else DEFAULT_MAX_ITERATIONS
    except (TypeError, ValueError):
        parsed = DEFAULT_MAX_ITERATIONS
    return max(1, min(parsed, HARD_MAX_ITERATIONS))


def _call_worker(
    goal: str,
    iterations: list[dict[str, Any]],
    instruction: str,
    model: str,
    call_handler: Any,
) -> dict[str, Any]:
    history = _format_history(iterations)
    prompt = (
        f"Goal: {goal}\n\n"
        f"History so far:\n{history if history else '(no prior iterations)'}\n\n"
        f"Next instruction from the Evaluator:\n{instruction}\n\n"
        "Produce your next contribution toward the goal."
    )
    return call_model(
        {
            "model_hint": model,
            "messages": [
                {"role": "system", "content": WORKER_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "max_tokens": 800,
            "thinking_level": "none",
        },
        {"_model_call_depth": 0},
        call_handler=call_handler,
    )


def _call_evaluator(
    goal: str,
    worker_output: str,
    model: str,
    call_handler: Any,
) -> dict[str, Any]:
    prompt = (
        f"Goal: {goal}\n\n"
        f"Worker's latest output:\n{worker_output or '(empty)'}\n\n"
        "Decide whether the goal has been achieved. Reply with strict JSON only."
    )
    return call_model(
        {
            "model_hint": model,
            "messages": [
                {"role": "system", "content": EVALUATOR_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "max_tokens": 400,
            "thinking_level": "none",
            "output_schema": EVALUATOR_OUTPUT_SCHEMA,
        },
        {"_model_call_depth": 0},
        call_handler=call_handler,
    )


def _format_history(iterations: list[dict[str, Any]]) -> str:
    if not iterations:
        return ""
    lines: list[str] = []
    for entry in iterations:
        idx = entry.get("iteration")
        worker_output = str(entry.get("worker_output") or "").strip()
        verdict = entry.get("verdict") if isinstance(entry.get("verdict"), dict) else {}
        verdict_reason = str(verdict.get("reason") or "")
        lines.append(f"--- Iteration {idx} ---")
        if worker_output:
            lines.append(f"Worker: {worker_output[:1000]}")
        if verdict_reason:
            lines.append(f"Evaluator reason: {verdict_reason}")
    return "\n".join(lines)


def _parse_verdict(output: Any) -> dict[str, Any]:
    if isinstance(output, dict):
        return output
    text = ""
    if isinstance(output, str):
        text = output.strip()
    elif output is not None:
        text = str(output).strip()
    if text.startswith("```"):
        lines = [line for line in text.splitlines() if not line.strip().startswith("```")]
        text = "\n".join(lines).strip()
    if text:
        try:
            parsed = json.loads(text)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass
    return {
        "achieved": False,
        "reason": "could not parse evaluator verdict",
        "next_instruction": "Continue working toward the goal.",
    }


def _is_ok_response(response: Any) -> bool:
    return isinstance(response, dict) and response.get("status") == "ok"


def _failure_with_iterations(
    message: str, code: str, iterations: list[dict[str, Any]]
) -> dict[str, Any]:
    """Return an error envelope that also surfaces partial loop progress."""
    payload = error(message, code)
    payload["error"]["iterations"] = iterations
    return payload


def _response_error_payload(response: Any) -> dict[str, Any]:
    if isinstance(response, dict):
        return {
            "code": response.get("code"),
            "error": response.get("error"),
        }
    return {"error": str(response)}


def _response_text(response: dict[str, Any]) -> str:
    output = response.get("output")
    if isinstance(output, str):
        return output.strip()
    if isinstance(output, dict):
        # call_model returns dicts when output_schema is set; the worker call
        # never sets one, but be defensive in case the gateway returns JSON.
        try:
            return json.dumps(output, ensure_ascii=False).strip()
        except (TypeError, ValueError):
            return str(output).strip()
    if output is None:
        return ""
    return str(output).strip()
