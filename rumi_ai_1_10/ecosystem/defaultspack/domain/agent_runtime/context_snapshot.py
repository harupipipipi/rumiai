from __future__ import annotations

from typing import Any

from core_runtime.runtime_audit_helpers import redact_sensitive

from .models import json_dumps
from .run_store import AgentRunStore


FILE_KEYS = {
    "changed_files",
    "created_files",
    "files_modified",
    "modified_files",
    "updated_files",
}
NEXT_STEP_KEYS = {"next_steps", "next_recommendation", "recommendations"}
TERMINAL_TOOL_HINTS = ("terminal", "shell", "command", "pytest", "test")
TERMINAL_ARTIFACT_KEYS = (
    "output_artifact_path",
    "output_artifact_paths",
    "stdout_artifact_path",
    "stderr_artifact_path",
)
ACTIVE_RUN_CONTEXT_KEYS = (
    "active_run_id",
    "agent_run_id",
    "current_run_id",
    "run_id",
    "execution_id",
)


def build_run_context_snapshot(
    run_id: str,
    *,
    store: AgentRunStore | None = None,
    context: dict[str, Any] | None = None,
    require_context_match: bool = False,
    max_items: int = 8,
    max_text_chars: int = 500,
) -> dict[str, Any]:
    """Build compact-packet-shaped context from a durable run without mutating it."""
    clean_run_id = str(run_id or "").strip()
    if not clean_run_id:
        return _empty_snapshot()

    store = store or AgentRunStore()
    run = store.get_run(clean_run_id)
    if not run:
        return _empty_snapshot()
    if require_context_match and not run_context_allows_snapshot(run, context, run_id=clean_run_id):
        return _empty_snapshot()

    execution = run.get("execution_json") if isinstance(run.get("execution_json"), dict) else {}
    result = run.get("result_json")
    steps = store.list_steps(clean_run_id, limit=max_items * 2)
    tool_calls = store.list_tool_calls(clean_run_id, limit=max_items * 2)
    events = store.events(clean_run_id, limit=max_items * 2)

    progress = _progress_from_run(run, steps, max_items=max_items, max_text_chars=max_text_chars)
    changed_files = _unique_limited(_collect_values([run, execution, result, steps], FILE_KEYS), max_items)
    next_steps = _unique_limited(_collect_values([result, execution, steps, events], NEXT_STEP_KEYS), max_items)
    tool_results = _tool_results(tool_calls, max_items=max_items, max_text_chars=max_text_chars)
    terminal_results = _terminal_results(tool_calls, result, max_items=max_items, max_text_chars=max_text_chars)

    critical_context = [
        item
        for item in [
            _non_empty(f"run_id: {clean_run_id}"),
            _non_empty(f"status: {run.get('status')}"),
            _non_empty(f"task: {_clip(run.get('task'), max_text_chars)}") if run.get("task") else None,
            _non_empty(f"error: {_clip(run.get('error'), max_text_chars)}") if run.get("error") else None,
        ]
        if item
    ][:max_items]

    return {
        "progress": progress,
        "changed_files": changed_files,
        "tool_results": tool_results,
        "terminal_results": terminal_results,
        "critical_context": critical_context,
        "next_steps": next_steps,
    }


def run_context_allows_snapshot(
    run: dict[str, Any] | None,
    context: dict[str, Any] | None,
    *,
    run_id: str | None = None,
) -> bool:
    """Return True when server context owns a run or names it as the active run."""
    if not isinstance(run, dict) or not isinstance(context, dict) or not context:
        return False

    clean_run_id = _clean(run_id or run.get("run_id"))
    if not clean_run_id:
        return False

    for key in ACTIVE_RUN_CONTEXT_KEYS:
        if _clean(context.get(key)) == clean_run_id:
            return True

    context_session = _clean(context.get("session_key"))
    if context_session and context_session == _clean(run.get("session_key")):
        return True

    context_conversation = _clean(context.get("conversation_id"))
    if context_conversation and context_conversation == _clean(run.get("conversation_id")):
        return True

    return False


def _clean(value: Any) -> str:
    return str(value or "").strip()


def _empty_snapshot() -> dict[str, Any]:
    return {
        "progress": {"done": [], "in_progress": [], "blocked": []},
        "changed_files": [],
        "tool_results": [],
        "terminal_results": [],
        "critical_context": [],
        "next_steps": [],
    }


def _progress_from_run(
    run: dict[str, Any],
    steps: list[dict[str, Any]],
    *,
    max_items: int,
    max_text_chars: int,
) -> dict[str, list[str]]:
    progress = {"done": [], "in_progress": [], "blocked": []}
    status = str(run.get("status") or "").lower()
    task = _clip(run.get("task"), max_text_chars)
    if status in {"completed", "planned"} and task:
        progress["done"].append(task)
    elif status in {"failed", "error", "cancelled", "stale"}:
        progress["blocked"].append(_clip(run.get("error") or task or status, max_text_chars))
    elif task:
        progress["in_progress"].append(task)

    for step in steps:
        content = step.get("content_json")
        label = _step_label(step, content, max_text_chars=max_text_chars)
        if not label:
            continue
        step_status = str(step.get("status") or "").lower()
        if step_status in {"completed", "done", "ok", "success"}:
            progress["done"].append(label)
        elif step_status in {"failed", "error", "blocked"}:
            progress["blocked"].append(label)
        else:
            progress["in_progress"].append(label)

    return {key: _unique_limited(values, max_items) for key, values in progress.items()}


def _step_label(step: dict[str, Any], content: Any, *, max_text_chars: int) -> str:
    if isinstance(content, dict):
        for key in ("summary", "title", "message", "action", "command"):
            if content.get(key):
                return _clip(content.get(key), max_text_chars)
    step_type = str(step.get("step_type") or "").strip()
    if step_type:
        return step_type
    return _clip(content, max_text_chars)


def _tool_results(
    tool_calls: list[dict[str, Any]],
    *,
    max_items: int,
    max_text_chars: int,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for call in tool_calls:
        if call.get("result_json") in (None, "", {}):
            continue
        results.append(
            {
                "tool": str(call.get("tool_name") or ""),
                "status": str(call.get("status") or ""),
                "result": _clip(call.get("result_json"), max_text_chars),
            }
        )
        if len(results) >= max_items:
            break
    return results


def _terminal_results(
    tool_calls: list[dict[str, Any]],
    result: Any,
    *,
    max_items: int,
    max_text_chars: int,
) -> list[dict[str, Any]]:
    terminal: list[dict[str, Any]] = []
    for call in tool_calls:
        name = str(call.get("tool_name") or "").lower()
        if not any(hint in name for hint in TERMINAL_TOOL_HINTS):
            continue
        entry = {
            "tool": str(call.get("tool_name") or ""),
            "status": str(call.get("status") or ""),
            "result": _clip(call.get("result_json"), max_text_chars),
        }
        artifact_paths = _terminal_artifact_paths(
            call.get("result_json"),
            max_text_chars=max_text_chars,
        )
        if artifact_paths:
            entry["output_artifact_paths"] = artifact_paths
        terminal.append(entry)
        if len(terminal) >= max_items:
            return terminal

    if isinstance(result, dict):
        command = result.get("command") or result.get("test_result")
        if command:
            entry = {
                "command": _clip(command, max_text_chars),
                "exit_code": result.get("exit_code"),
                "status": str(result.get("status") or ""),
            }
            artifact_paths = _terminal_artifact_paths(result, max_text_chars=max_text_chars)
            if artifact_paths:
                entry["output_artifact_paths"] = artifact_paths
            terminal.append(entry)
    return terminal[:max_items]


def _terminal_artifact_paths(value: Any, *, max_text_chars: int) -> list[str]:
    paths: list[Any] = []

    def visit(item: Any) -> None:
        if isinstance(item, dict):
            for key, child in item.items():
                if key in TERMINAL_ARTIFACT_KEYS:
                    paths.extend(_flatten_strings(child))
                elif isinstance(child, dict):
                    visit(child)
        elif isinstance(item, (list, tuple)):
            for child in item:
                visit(child)

    visit(value)
    return _unique_limited([_clip(path, max_text_chars) for path in paths], 8)


def _collect_values(values: list[Any], keys: set[str]) -> list[str]:
    found: list[str] = []

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                if key in keys:
                    found.extend(_flatten_strings(item))
                elif isinstance(item, (dict, list, tuple)):
                    visit(item)
        elif isinstance(value, (list, tuple)):
            for item in value:
                visit(item)

    visit(values)
    return found


def _flatten_strings(value: Any) -> list[str]:
    if value in (None, ""):
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [_clip(value, 500)]
    if isinstance(value, (list, tuple, set)):
        result: list[str] = []
        for item in value:
            result.extend(_flatten_strings(item))
        return result
    return [str(value)]


def _unique_limited(values: list[Any], limit: int) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
        if len(result) >= limit:
            break
    return result


def _clip(value: Any, max_text_chars: int) -> str:
    clean = redact_sensitive(value)
    if isinstance(clean, str):
        text = clean
    else:
        text = json_dumps(clean)
    text = text.strip()
    if len(text) <= max_text_chars:
        return text
    return text[: max(0, max_text_chars - 15)].rstrip() + "...(truncated)"


def _non_empty(value: str) -> str | None:
    text = str(value or "").strip()
    return text or None
