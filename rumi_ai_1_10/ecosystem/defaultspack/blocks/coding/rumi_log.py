"""defaults.coding.rumi_log - local .rumi coding history."""

from __future__ import annotations

from blocks._common import error, ok
from blocks.coding._workspace import resolve_workspace, with_workspace, workspace_error_response
from domain.coding.rumi_log import DEFAULT_EVENT_LIMIT, RumiLogStore


METADATA_FIELDS = ("mentions", "task_id", "task_title", "task_status")


def _limit(value):
    try:
        return int(value)
    except Exception:
        return DEFAULT_EVENT_LIMIT


def _kinds(value):
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return value


def run(input_data, context=None):
    input_data = input_data or {}
    context = context or {}
    raw_action = str(input_data.get("action") or "").strip().lower()
    raw_method = input_data.get("_method") or input_data.get("method")
    if raw_method:
        method = str(raw_method).upper()
    else:
        method = "POST" if raw_action in {"append", "seed", "seed_local_plan", "ensure_plan"} else "GET"
    action = raw_action or ("list" if method == "GET" else "append")
    try:
        workspace = resolve_workspace(
            input_data,
            context,
            mutation=method != "GET",
            operation="rumi.log." + action,
        )
        store = RumiLogStore(workspace.root_path)
        if method == "GET" or action == "list":
            events = store.list_events(
                limit=_limit(input_data.get("limit")),
                kinds=_kinds(input_data.get("kind") or input_data.get("kinds")),
            )
            return ok(with_workspace({
                "rumi_dir": str(store.rumi_dir),
                "events_path": str(store.events_path),
                "events": events,
                "summary": store.summary(),
            }, workspace))
        if method != "POST":
            return error("unsupported method: " + method, code="INVALID_INPUT")
        if action in {"seed", "seed_local_plan", "ensure_plan"}:
            result = store.seed_local_plan()
            result.update({"rumi_dir": str(store.rumi_dir), "events_path": str(store.events_path)})
            return ok(with_workspace(result, workspace))
        if action != "append":
            return error("unsupported action: " + action, code="INVALID_INPUT")
        metadata = input_data.get("metadata") if isinstance(input_data.get("metadata"), dict) else {}
        metadata = dict(metadata)
        for field in METADATA_FIELDS:
            if input_data.get(field) is not None:
                metadata[field] = input_data.get(field)
        event = store.append_event(
            kind=input_data.get("kind") or "agent.note",
            actor_id=input_data.get("actor_id"),
            agent_role=input_data.get("agent_role"),
            session_id=input_data.get("session_id"),
            status=input_data.get("status") or "noted",
            message=input_data.get("message"),
            branch=input_data.get("branch"),
            commit_hash=input_data.get("commit_hash"),
            remote=input_data.get("remote"),
            paths=input_data.get("paths"),
            metadata=metadata,
        )
        events = store.list_events(limit=_limit(input_data.get("limit")))
        return ok(with_workspace({
            "rumi_dir": str(store.rumi_dir),
            "events_path": str(store.events_path),
            "event": event,
            "events": events,
            "summary": store.summary(),
        }, workspace))
    except ValueError as exc:
        return error(str(exc), code="INVALID_INPUT")
    except Exception as exc:
        workspace_error = workspace_error_response(exc, error)
        if workspace_error:
            return workspace_error
        return error(str(exc), code="RUMI_LOG_ERROR")
