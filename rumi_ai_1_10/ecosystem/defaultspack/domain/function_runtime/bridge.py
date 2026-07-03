from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path
from typing import Any

from .context import principal_from_context
from .response import error, normalize_output

logger = logging.getLogger(__name__)

_REQUEST_CONTEXT_KEYS = {
    "_tool_server_approved",
    "_authenticated_principal",
    "_authority_subject",
    "approval_id",
    "authority_principal_id",
    "conversation_id",
    "graph_id",
    "node_id",
    "profile_id",
    "request_id",
    "source",
    "tool_call_id",
    "user_id",
}
_AUTHORITY_CONTEXT_KEYS = {
    "approval_token",
    "conversation_id",
    "graph_id",
    "node_id",
    "permission_id",
    "principal_id",
    "profile_id",
    "request_id",
    "run_request_id",
}
_AUTHORITY_APPROVAL_KEYS = {"approval_token", "permission_id", "request_id", "token"}


def _sanitized_authority_approval(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    sanitized: dict[str, Any] = {}
    for key in _AUTHORITY_APPROVAL_KEYS:
        if key not in raw:
            continue
        value = raw.get(key)
        if isinstance(value, (str, int, float, bool)) or value is None:
            sanitized[key] = value
    return sanitized


def _sanitized_authority_context(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        return {}
    sanitized: dict[str, Any] = {}
    for key in _AUTHORITY_CONTEXT_KEYS:
        if key not in raw:
            continue
        value = raw.get(key)
        if isinstance(value, (str, int, float, bool)) or value is None:
            sanitized[key] = value
    approval_tokens = raw.get("approval_tokens")
    if isinstance(approval_tokens, dict):
        nested: dict[str, dict[str, Any]] = {}
        for permission_id, approval in approval_tokens.items():
            permission_key = str(permission_id or "").strip()
            sanitized_approval = _sanitized_authority_approval(approval)
            if permission_key and sanitized_approval:
                nested[permission_key] = sanitized_approval
        if nested:
            sanitized["approval_tokens"] = nested
    approvals = raw.get("approvals")
    if isinstance(approvals, list):
        nested_list = [
            _sanitized_authority_approval(item)
            for item in approvals
            if isinstance(item, dict) and _sanitized_authority_approval(item)
        ]
        if nested_list:
            sanitized["approvals"] = nested_list
    return sanitized


def _sanitized_request_context(context: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(context, dict):
        return {}
    sanitized: dict[str, Any] = {}
    for key in _REQUEST_CONTEXT_KEYS:
        if key in context:
            value = context[key]
            if isinstance(value, (str, int, float, bool)) or value is None:
                sanitized[key] = value
            elif key in {"_authenticated_principal", "_authority_subject"} and isinstance(value, dict):
                sanitized[key] = _sanitized_principal_context(value)
    authority = _sanitized_authority_context(context.get("authority"))
    if authority:
        sanitized["authority"] = authority
    return sanitized


def _sanitized_principal_context(raw: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "auth_mode",
        "token_id",
        "profile_id",
        "surface_id",
        "device_id",
        "role",
        "issued_at",
        "expires_at",
        "core_role",
        "principal_id",
    }
    sanitized: dict[str, Any] = {}
    for key in allowed:
        if key not in raw:
            continue
        value = raw.get(key)
        if isinstance(value, (str, int, float, bool)) or value is None:
            sanitized[key] = value
    audiences = raw.get("audiences")
    if isinstance(audiences, list):
        sanitized["audiences"] = [str(item) for item in audiences if str(item or "").strip()]
    facets = raw.get("facet_principal_ids")
    if isinstance(facets, list):
        sanitized["facet_principal_ids"] = [str(item) for item in facets if str(item or "").strip()]
    return sanitized


def ensure_defaultspack_functions_registered(container: Any | None = None) -> int:
    """Register generated defaultspack functions into the shared DI registry."""
    if container is None:
        try:
            from core_runtime.di_container import get_container

            container = get_container()
        except Exception:
            return 0
    try:
        registry = container.get_or_none("function_registry")
    except Exception:
        registry = None
    if registry is None:
        return 0

    registered = 0
    try:
        from .template_specs import register_template_functions

        registered += register_template_functions(registry)
    except Exception:
        pass
    functions_root = Path(__file__).resolve().parents[2] / "functions"
    if functions_root.is_dir():
        for function_dir in sorted(path for path in functions_root.iterdir() if path.is_dir()):
            manifest_path = function_dir / "manifest.json"
            if not manifest_path.is_file():
                continue
            try:
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            except Exception:
                continue
            function_id = str(manifest.get("function_id") or function_dir.name).strip()
            if not function_id:
                continue
            try:
                if registry.register(
                    pack_id="defaultspack",
                    function_id=function_id,
                    manifest=manifest,
                    function_dir=function_dir,
                ):
                    registered += 1
            except Exception:
                continue
    try:
        from core_runtime.function_registry import FunctionEntry

        from .manifest_factory import FUNCTION_SPECS, manifest_for

        runtime_dir = Path(__file__).resolve().parent
        runner_path = runtime_dir / "template_runner.py"
        for spec in FUNCTION_SPECS:
            manifest = manifest_for(spec)
            manifest["entrypoint"] = "template_runner.py:run"
            if registry.register(
                FunctionEntry(
                    function_id=spec.function_id,
                    pack_id="defaultspack",
                    description=manifest.get("description", ""),
                    requires=list(manifest.get("requires") or []),
                    caller_requires=list(manifest.get("caller_requires") or []),
                    host_execution=False,
                    tags=list(manifest.get("tags") or []),
                    input_schema=dict(manifest.get("input_schema") or {}),
                    output_schema=dict(manifest.get("output_schema") or {}),
                    function_dir=runtime_dir,
                    main_py_path=runner_path,
                    manifest=manifest,
                    runtime="python",
                    entrypoint="template_runner.py:run",
                    risk=manifest.get("risk"),
                    grant_config=manifest.get("grant_config"),
                    vocab_aliases=list(manifest.get("vocab_aliases") or []),
                    permission_id=manifest.get("permission_id"),
                    is_builtin=False,
                    grant_config_schema=manifest.get("grant_config_schema"),
                    calling_convention="subprocess",
                )
            ):
                registered += 1
    except Exception:
        pass
    return registered


def ensure_pack_functions_registered(
    pack_id: str,
    pack_root: Path | str | None = None,
    container: Any | None = None,
) -> int:
    """Register functions contributed by an activated sibling pack."""
    normalized_pack_id = str(pack_id or "").strip()
    if not normalized_pack_id:
        return 0
    if normalized_pack_id in {"default", "defaults", "defaultspack"}:
        return ensure_defaultspack_functions_registered(container)
    if pack_root is None:
        return 0
    if container is None:
        try:
            from core_runtime.di_container import get_container

            container = get_container()
        except Exception:
            return 0
    try:
        registry = container.get_or_none("function_registry")
    except Exception:
        registry = None
    if registry is None:
        return 0

    root = Path(pack_root)
    functions_root = root / "functions"
    if not functions_root.is_dir():
        return 0
    registered = 0
    for function_dir in sorted(path for path in functions_root.iterdir() if path.is_dir()):
        manifest_path = function_dir / "manifest.json"
        if not manifest_path.is_file():
            continue
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(manifest, dict):
            continue
        function_id = str(manifest.get("function_id") or function_dir.name).strip()
        if not function_id:
            continue
        try:
            if registry.register(
                pack_id=normalized_pack_id,
                function_id=function_id,
                manifest=manifest,
                function_dir=function_dir,
            ):
                registered += 1
        except Exception:
            continue
    return registered


def invoke_function(
    qualified_name: str,
    args: dict[str, Any] | None,
    context: dict[str, Any] | None = None,
    principal_id: str = "defaultspack",
    timeout_seconds: float | None = None,
    function_pack_root: Path | str | None = None,
) -> dict[str, Any]:
    """Invoke a Rumi function through the shared CapabilityExecutor."""
    try:
        from core_runtime.di_container import get_container
    except Exception as exc:
        return error(f"Capability runtime is unavailable: {exc}", "CAPABILITY_RUNTIME_UNAVAILABLE")

    principal = principal_id or principal_from_context(context)
    request = {
        "type": "function.call",
        "qualified_name": qualified_name,
        "args": dict(args or {}),
        "request_id": str((context or {}).get("request_id") or uuid.uuid4()),
    }
    sanitized_context = _sanitized_request_context(context)
    if sanitized_context:
        request["context"] = sanitized_context
    if timeout_seconds is not None:
        request["timeout_seconds"] = timeout_seconds
    try:
        container = get_container()
        pack_id = _pack_id_from_qualified_name(qualified_name)
        if qualified_name.startswith("defaultspack:") or qualified_name.startswith("defaults."):
            ensure_defaultspack_functions_registered(container)
        elif pack_id:
            ensure_pack_functions_registered(pack_id, function_pack_root, container)
        executor = container.get_or_none("capability_executor")
        if executor is None:
            from core_runtime.capability_executor import get_capability_executor

            executor = get_capability_executor()
        response = executor.execute(principal, request)
    except Exception as exc:
        return error(f"Capability execution failed: {exc}", "CAPABILITY_EXECUTION_FAILED")

    if not getattr(response, "success", False):
        if getattr(response, "error_type", None) == "caller_requires_denied":
            authority = sanitized_context.get("authority") if isinstance(sanitized_context.get("authority"), dict) else {}
            approval_tokens = authority.get("approval_tokens") if isinstance(authority.get("approval_tokens"), dict) else {}
            logger.warning(
                "function bridge caller_requires denied: function=%s principal=%s approved=%s source=%s approval_id=%s authority_principal=%s authority_permission=%s authority_has_token=%s approval_token_keys=%s context_keys=%s",
                qualified_name,
                principal,
                sanitized_context.get("_tool_server_approved") is True,
                str(sanitized_context.get("source") or ""),
                str(sanitized_context.get("approval_id") or ""),
                str(sanitized_context.get("authority_principal_id") or authority.get("principal_id") or ""),
                str(authority.get("permission_id") or ""),
                bool(authority.get("approval_token")),
                sorted(str(key) for key in approval_tokens.keys()),
                sorted(str(key) for key in sanitized_context.keys()),
            )
        return error(
            getattr(response, "error", None) or "Function call failed",
            (getattr(response, "error_type", None) or "FUNCTION_CALL_FAILED").upper(),
        )
    return normalize_output(getattr(response, "output", None))


def _pack_id_from_qualified_name(qualified_name: str) -> str:
    value = str(qualified_name or "").strip()
    if ":" in value:
        return value.split(":", 1)[0].strip()
    if "." in value:
        return value.split(".", 1)[0].strip()
    return ""


def invoke_defaultspack_function(
    function_id: str,
    args: dict[str, Any] | None,
    context: dict[str, Any] | None = None,
    principal_id: str = "defaultspack",
    timeout_seconds: float | None = None,
) -> dict[str, Any]:
    qualified_name = function_id if ":" in function_id else f"defaultspack:{function_id}"
    return invoke_function(
        qualified_name,
        args,
        context,
        principal_id,
        timeout_seconds=timeout_seconds,
    )
