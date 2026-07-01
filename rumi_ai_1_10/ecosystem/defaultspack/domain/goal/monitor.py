from __future__ import annotations

from typing import Any

from domain.goal.store import GoalStore, RUNNING_STATUSES


def start_goal(
    *,
    conversation_id: str,
    objective: str,
    checker_policy: dict[str, Any] | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    run = GoalStore().create_run(
        conversation_id=conversation_id,
        objective=objective,
        checker_policy=checker_policy,
        metadata=metadata,
    )
    return {
        "goal_run": run,
        "goal_run_id": run["goal_run_id"],
        "conversation_id": run["conversation_id"],
        "status": run["status"],
        "message": "Goal monitor started.",
        "effects": [goal_surface_effect(run)],
    }


def monitor_after_assistant_message(
    conversation_id: str,
    message: dict[str, Any],
    *,
    context: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    if not _is_final_assistant_message(message):
        return []
    message_id = str(message.get("id") or "").strip()
    if not message_id:
        return []
    store = GoalStore()
    results = []
    for run in store.list_runs(conversation_id=conversation_id, statuses=set(RUNNING_STATUSES)):
        if str(run.get("last_checked_message_id") or "") == message_id:
            continue
        try:
            from domain.goal.checker import run_goal_checker

            results.append(
                run_goal_checker(
                    str(run.get("goal_run_id") or ""),
                    message_id=message_id,
                    context=context or {},
                )
            )
        except Exception as exc:
            store.record_check_error(
                str(run.get("goal_run_id") or ""),
                str(exc),
                message_id=message_id,
            )
            results.append({"status": "error", "message": str(exc)})
    return results


def goal_surface_effect(run: dict[str, Any]) -> dict[str, Any]:
    goal_run_id = str(run.get("goal_run_id") or "")
    conversation_id = str(run.get("conversation_id") or "")
    return {
        "type": "surface.open",
        "surface": {
            "id": f"goal:{goal_run_id}",
            "kind": "goal_monitor",
            "title": "Goal",
            "sourcePackId": "defaultspack",
            "renderer": "defaultspack.goal_monitor",
            "conversationId": conversation_id,
            "resourceId": goal_run_id,
            "payload": {
                "goal_run_id": goal_run_id,
                "objective": str(run.get("objective") or ""),
                "status": str(run.get("status") or "running"),
            },
            "layoutMode": "split",
            "chatPlacement": "left",
        },
    }


def _is_final_assistant_message(message: dict[str, Any]) -> bool:
    if not isinstance(message, dict) or message.get("role") != "assistant":
        return False
    if str(message.get("finish_reason") or "") == "streaming":
        return False
    metadata = message.get("metadata") if isinstance(message.get("metadata"), dict) else {}
    return not (metadata.get("streaming") is True or metadata.get("draft") is True)
