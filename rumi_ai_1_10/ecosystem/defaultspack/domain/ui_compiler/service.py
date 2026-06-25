from __future__ import annotations

from pathlib import Path
from typing import Any

from .artifact_store import UICompilerArtifactStore
from .models import UICompilerConfig
from .planner import RecursiveUIPlanner


def compile_ui_plan(arguments: dict[str, Any] | None, context: dict[str, Any] | None = None) -> dict[str, Any]:
    data = arguments if isinstance(arguments, dict) else {}
    root_payload = data.get("ui_tree") or data.get("uiTree") or data.get("root") or data.get("page")
    if not isinstance(root_payload, dict):
        return _error("ui_tree dict is required", "INVALID_UI_TREE")

    try:
        config = UICompilerConfig.from_dict(data.get("config") or {})
        run_id = str(data.get("run_id") or data.get("runId") or "").strip() or None
        plan = RecursiveUIPlanner(config).plan(root_payload, run_id=run_id)
    except (TypeError, ValueError) as exc:
        return _error(str(exc), "INVALID_UI_PLAN")

    payload: dict[str, Any] = {"plan": plan.to_dict()}
    if _truthy(data.get("persist")):
        if not _persistence_allowed(context):
            return _error(
                "persist requires an internal tool approval context",
                "APPROVAL_REQUIRED",
                data={"approval_required": True},
            )
        try:
            store_root = _store_root_from_arguments(data, context)
            payload["artifacts"] = UICompilerArtifactStore(store_root).save_plan(plan)
        except (OSError, ValueError) as exc:
            return _error(str(exc), "ARTIFACT_WRITE_FAILED")

    return {
        "status": "ok",
        "data": payload,
        "widget": {
            "type": "ui_compile_plan",
            "run_id": plan.run_id,
            "summary": payload["plan"]["summary"],
            "artifacts": payload.get("artifacts"),
        },
    }


def _store_root_from_arguments(data: dict[str, Any], context: dict[str, Any] | None) -> Path:
    raw_root = data.get("artifact_root") or data.get("artifactRoot")
    if not raw_root and isinstance(context, dict):
        raw_root = context.get("conversation_workspace_dir") or context.get("workspace_dir")
    base = Path(str(raw_root)).expanduser() if raw_root else Path.cwd()
    if base.name == "ui" and base.parent.name == ".rumi":
        return base
    return base / ".rumi" / "ui"


def _persistence_allowed(context: dict[str, Any] | None) -> bool:
    if not isinstance(context, dict):
        return False
    if context.get("_tool_server_approved") is True:
        return True
    profile_policy = context.get("profile_policy")
    if isinstance(profile_policy, dict) and profile_policy.get("yolo_mode") is True:
        return True
    return False


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def _error(message: str, code: str, *, data: dict[str, Any] | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {"status": "error", "error": {"code": code, "message": message}}
    if data:
        payload["data"] = data
    return payload
