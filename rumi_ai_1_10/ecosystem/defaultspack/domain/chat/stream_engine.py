from __future__ import annotations

import os
import threading
import time
from typing import Any, Iterator

from blocks._common import gen_id, timestamp
from blocks.chat.send import (
    _ai_error_after_tool_use_response,
    _ai_error_response,
    _ai_retry_attempts,
    _ai_retry_delay,
    _append_assistant_tool_use_message,
    _append_tool_result_message,
    _bounded_compact_tool_result,
    _compact_tool_log_value,
    _empty_response_message,
    _is_retryable_ai_error,
    _params_without_thinking,
    _redact_sensitive_value,
    _tool_blocked_response,
    _tool_limit_message,
    _tool_result_artifacts,
    _tool_result_is_error,
    _tool_result_recovery_kind,
    _tool_result_summary,
    _tool_use_blocks,
    _tool_visibility_message,
)
from domain.ai_client.bridge_plan import PlannedProviderRequest
from domain.ai_client.run_seal import (
    RunSealPolicy,
    RunSealService,
    apply_visible_text_to_response,
    append_run_seal_retry_note,
    build_run_seal_policy,
    response_has_structured_output,
)
from domain.ai_client.provider_compiler.registry import compile_complete, compiler_for_api_family
from domain.ai_client.provider_trace import redact_sensitive_value, write_provider_trace
from domain.ai_client.client import AIClient, AuthorityApprovalRequired
from domain.ai_client.authority_resource import build_provider_authority_resource, provider_authority_reason
from domain.ai_client.gateway import LLMGateway
from domain.chat.cancellation import get_chat_cancellation_registry
from domain.chat.ir_legacy_adapter import (
    append_assistant_tool_use_to_ir,
    append_tool_result_to_ir,
    legacy_standard_messages_to_ir,
)
from domain.chat.loop_guard import (
    LoopDecision,
    LoopGuard,
    build_loop_observation,
    emergency_budget_from_context,
    explicit_param_max_tool_calls,
    loop_guard_config_from_context,
)
from domain.chat.message_builder import build_assistant_message
from domain.chat.progress_tool import (
    ASSISTANT_PROGRESS_MAX_UPDATES,
    ASSISTANT_PROGRESS_TOOL_NAME,
    is_assistant_progress_tool_name,
    normalize_assistant_progress_payload,
)
from domain.chat.public_metadata import compact_provider_planning
from domain.chat.run_request import PreparedChatRun, prepare_chat_run
from domain.chat.tool_call_accumulator import ToolCallAccumulator
from domain.chat.store import ChatStore
from domain.kanban.chat_sync import sync_conversation_kanban
from domain.context_engine.compressor import ContextCompressor
from domain.dev.inspector import Inspector
from domain.stream.events import run_event, to_legacy_chat_stream_event
from domain.tool.executor import ToolExecutor
from domain.tool.schema_adapter import build_tool_execution_context, max_tool_calls, tool_name_from_definition


class _ChatCancelled(Exception):
    pass


_APPROVAL_WAITING_TEXT = "許可が必要なため、ユーザーが承認するまで待機します。承認後に続行します。"
_AUTHORITY_WAITING_TEXT = "モデル/API の使用許可が必要です。承認後に続行します。"
_APPROVAL_FOLLOWUP_ALREADY_HANDLED_TEXT = "承認済みの操作はすでに処理済みです。重複した承認再開リクエストは実行しません。"
_APPROVAL_FOLLOWUP_INVALID_TEXT = "承認再開トークンを検証できなかったため、操作を再実行しません。"


def _tool_selection_activity_message(selection: dict[str, Any]) -> str:
    services = selection.get("selected_services") if isinstance(selection.get("selected_services"), list) else []
    labels = [
        str(service.get("label") or service.get("service_id") or "").strip()
        for service in services
        if isinstance(service, dict) and str(service.get("label") or service.get("service_id") or "").strip()
    ]
    count = len(selection.get("selected_tool_ids") if isinstance(selection.get("selected_tool_ids"), list) else [])
    if labels:
        head = " と ".join(labels[:2])
        if len(labels) > 2:
            head = f"{head} など"
        return f"{head}を使用します"
    if count:
        return f"{count}個の機能を使用します"
    return "追加の機能なしで続行します"


def _tool_display_group(tool_name: str) -> dict[str, str]:
    lowered = str(tool_name or "").lower()
    rules = [
        (("calculator", "calc", "math"), "calculation", "計算"),
        (("web", "search", "reddit"), "web/search", "Web検索"),
        (("browser", "computer"), "browser", "ブラウザ"),
        (("todo", "task"), "planning/todo", "Todo"),
        (("delegate", "subagent", "agent"), "agent/delegation", "Delegation"),
        (("terminal", "shell", "exec"), "coding/terminal", "ターミナル"),
        (("file", "read", "write", "list"), "coding/files", "ファイル"),
        (("git", "branch", "commit", "diff"), "coding/git", "Git"),
    ]
    for keys, group_id, label in rules:
        if any(key in lowered for key in keys):
            return {"id": group_id, "label": label}
    return {"id": "tools", "label": "Tools"}


def _display_arg(arguments: dict[str, Any], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = arguments.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, (int, float, bool)):
            return str(value)
    return ""


def _basename(value: str) -> str:
    text = str(value or "").replace("\\", "/").rstrip("/")
    return text.split("/")[-1] if text else ""


def _terminal_action_label(command: str) -> str:
    text = str(command or "").strip()
    lowered = text.lower()
    if not text:
        return "ターミナルで作業"
    if lowered.startswith(("rg ", "grep ", "fd ", "find ")):
        return "コードを検索"
    if lowered.startswith(("sed ", "cat ", "less ", "head ", "tail ", "nl ")):
        return "ファイルを確認"
    if lowered.startswith(("git status", "git diff", "git show", "git log", "git branch", "git rev-parse")):
        return "Git 状態を確認"
    if lowered.startswith("git add"):
        return "変更をステージ"
    if lowered.startswith("git commit"):
        return "コミットを作成"
    if lowered.startswith("git push"):
        return "変更を push"
    if lowered.startswith(("npm test", "pnpm test", "yarn test", "python -m pytest", "pytest", "cargo test")):
        return "テストを実行"
    if lowered.startswith(("npm run build", "pnpm build", "pnpm run build", "yarn build", "cargo build")):
        return "ビルドを実行"
    if lowered.startswith(("npm run lint", "pnpm lint", "pnpm run lint", "yarn lint", "ruff ", "eslint ")):
        return "lint を実行"
    if lowered.startswith(("gh repo view", "gh pr view", "gh issue view")):
        return "GitHub 情報を確認"
    if lowered.startswith(("gh pr create", "gh pr edit")):
        return "PR を更新"
    return "ターミナルで作業"


def _tool_display_action(tool_name: str, arguments: dict[str, Any]) -> str:
    lowered = str(tool_name or "").lower()
    if not isinstance(arguments, dict):
        arguments = {}
    if "calculator" in lowered or "calc" in lowered:
        return _display_arg(arguments, ("expression", "expr", "input", "query"))
    if "search" in lowered or "web" in lowered or "reddit" in lowered:
        query = _display_arg(arguments, ("query", "q", "search_query", "text", "url"))
        return "検索: {}".format(query) if query else "検索"
    if "git" in lowered:
        if "push" in lowered:
            return "変更を push"
        if "commit" in lowered:
            return "コミットを作成"
        if "diff" in lowered:
            return "差分を確認"
        if "branch" in lowered:
            return "ブランチを確認"
        return "Git 状態を確認"
    if "file" in lowered:
        path = _display_arg(arguments, ("path", "filename", "directory", "glob"))
        label = _basename(path) or path
        if any(key in lowered for key in ("write", "patch", "create", "delete")):
            return "ファイルを編集: {}".format(label) if label else "ファイルを編集"
        if "list" in lowered:
            return "ファイル一覧を確認: {}".format(label) if label else "ファイル一覧を確認"
        return "ファイルを確認: {}".format(label) if label else "ファイルを確認"
    if "browser" in lowered or "computer" in lowered:
        action = _display_arg(arguments, ("action",)) or "画面操作"
        target = _display_arg(arguments, ("url", "app", "application", "browser", "name", "title"))
        text = _display_arg(arguments, ("text", "key"))
        return " ".join(part for part in (action, target, text) if part).strip()
    if "terminal" in lowered or "shell" in lowered or "exec" in lowered:
        command = _display_arg(arguments, ("command", "cmd"))
        return _terminal_action_label(command)
    if "todo" in lowered:
        return _display_arg(arguments, ("title", "task", "action", "todo_id")) or "Todo更新"
    if "delegate" in lowered or "subagent" in lowered or "agent" in lowered:
        return _display_arg(arguments, ("task", "title", "prompt")) or "委任実行"
    return ""


def _tool_display_payload(
    tool_name: str,
    arguments: dict[str, Any],
    *,
    status: str,
    summary: str = "",
) -> dict[str, Any]:
    group = _tool_display_group(tool_name)
    action = _tool_display_action(tool_name, arguments)
    if status == "running":
        display_text = "{}を進めています".format(action or tool_name or "tool")
        next_step = "結果が届き次第、次の判断に使います。"
    elif status == "failed":
        display_text = summary or "{} が失敗しました".format(tool_name or "tool")
        next_step = "失敗理由を確認して、必要なら止まります。"
    else:
        display_text = summary or "{} が完了しました".format(tool_name or "tool")
        next_step = "結果をもとに次の応答へ進みます。"
    return {
        "display_text": display_text,
        "status": status,
        "group": group,
        "action": action,
        "next_step": next_step,
    }


def _should_emit_model_routing_status(model_routing: dict[str, Any] | None) -> bool:
    if not isinstance(model_routing, dict) or not model_routing:
        return False
    if model_routing.get("bridge_required") or model_routing.get("warnings"):
        return True
    selected = str(model_routing.get("selected_model") or "")
    original = str(model_routing.get("original_model") or "")
    return bool(selected and original and selected != original)


def _provider_visible_params(params: dict[str, Any] | None) -> dict[str, Any]:
    clean = dict(params or {})
    clean.pop("_authority_context", None)
    return clean


def _provider_request_timeout_kwargs(params: dict[str, Any] | None) -> dict[str, float]:
    raw = params if isinstance(params, dict) else {}
    if "request_timeout" not in raw and "timeout" not in raw:
        return {}
    value = raw.get("request_timeout", raw.get("timeout", 120.0))
    try:
        timeout = float(value)
    except (TypeError, ValueError):
        timeout = 120.0
    return {"timeout": max(2.0, min(timeout, 120.0))}


def _authority_context_token_for_permission(context: dict[str, Any], permission_id: str) -> tuple[str, str]:
    permission_id = str(permission_id or "").strip()
    tokens = context.get("approval_tokens") if isinstance(context, dict) else None
    if isinstance(tokens, dict):
        raw = tokens.get(permission_id)
        if isinstance(raw, dict):
            request_id = str(raw.get("request_id") or raw.get("approval_request_id") or "").strip()
            token = str(raw.get("approval_token") or raw.get("token") or "").strip()
            if request_id and token:
                return request_id, token
    context_permission = str(context.get("permission_id") or "").strip() if isinstance(context, dict) else ""
    if context_permission and context_permission != permission_id:
        return "", ""
    request_id = str(context.get("request_id") or "").strip() if isinstance(context, dict) else ""
    token = str(context.get("approval_token") or "").strip() if isinstance(context, dict) else ""
    return request_id, token


def _normalize_tool_call_name_and_arguments(
    tool_name: str,
    arguments: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    name = str(tool_name or "").strip()
    if ":" not in name:
        return name, arguments
    base, suffix = name.split(":", 1)
    base = base.strip()
    suffix = suffix.strip()
    if base not in {"browser_computer", "browser_use", "computer_use"}:
        return name, arguments
    normalized_args = dict(arguments or {})
    action = str(normalized_args.get("action") or "").strip()
    if suffix and not action:
        normalized_args["action"] = suffix
    return base, normalized_args


def _approval_replay_executable_arguments(
    tool_name: str,
    arguments: dict[str, Any],
    *,
    action: str = "",
    operation: str = "",
) -> tuple[str, dict[str, Any]]:
    normalized_tool_name = str(tool_name or "").strip()
    executable = _strip_approval_tokens(arguments or {})
    raw_action = str(action or "").strip()
    scoped_operation = str(operation or "").strip()
    if normalized_tool_name == "browser_computer":
        payload_action = str(executable.get("action") or "").strip()
        if (
            payload_action.startswith(("browser.", "computer."))
            and isinstance(executable.get("payload"), dict)
        ):
            if not raw_action:
                raw_action = payload_action
            if not scoped_operation:
                scoped_operation = payload_action
            executable["action"] = (
                scoped_operation
                if raw_action.startswith("tool.") and scoped_operation
                else raw_action or scoped_operation or payload_action
            )
            return _normalize_tool_call_name_and_arguments(normalized_tool_name, executable)
    if normalized_tool_name in {"browser_use", "computer_use"}:
        for _ in range(3):
            payload_action = str(executable.get("action") or "").strip()
            nested = executable.get("payload")
            if not (
                payload_action.startswith(("browser.", "computer."))
                and isinstance(nested, dict)
            ):
                break
            executable = dict(nested)
            if not raw_action:
                raw_action = payload_action
            if not scoped_operation:
                scoped_operation = payload_action
            executable.setdefault("action", payload_action)
        final_action = (
            scoped_operation
            if raw_action.startswith("tool.") and scoped_operation
            else raw_action or scoped_operation
        )
        if final_action and not executable.get("action"):
            executable["action"] = final_action
    return _normalize_tool_call_name_and_arguments(normalized_tool_name, executable)


def _strip_approval_tokens(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _strip_approval_tokens(item)
            for key, item in value.items()
            if key != "approval_token"
        }
    if isinstance(value, list):
        return [_strip_approval_tokens(item) for item in value]
    return value


def _canonical_approval_replay_arguments(arguments: dict[str, Any]) -> dict[str, Any]:
    canonical = _strip_approval_tokens(arguments or {})
    payload = canonical.pop("payload", None)
    if isinstance(payload, dict):
        for key, value in payload.items():
            canonical.setdefault(key, value)
    action = str(canonical.get("action") or "").strip()
    action_aliases = {
        "browser.open_url": "open_url",
        "browser_open_url": "open_url",
        "open": "open_url",
        "computer.apps": "apps",
        "applications": "apps",
        "open_apps": "apps",
        "list_apps": "apps",
        "computer.windows": "windows",
        "computer.show_app": "show_app",
        "computer.select_app": "select_app",
        "computer.select_window": "select_window",
        "computer.screenshot": "screenshot",
        "computer.observe": "observe",
        "computer.type": "type",
        "computer.key": "key",
        "computer.click": "click",
        "computer.move": "move",
        "computer.drag": "drag",
        "computer.scroll": "scroll",
    }
    if action:
        canonical["action"] = action_aliases.get(action, action)
    return canonical


def _approval_tool_reference_key(value: Any) -> str:
    raw = str(value or "").strip()
    if raw.casefold().startswith("tool."):
        raw = raw[5:].strip()
    pieces: list[str] = []
    previous_separator = False
    for char in raw.casefold():
        if char.isalnum():
            pieces.append(char)
            previous_separator = False
        elif not previous_separator:
            pieces.append("_")
            previous_separator = True
    return "".join(pieces).strip("_")


def _approval_registry_tool_identity(value: Any) -> str:
    key = _approval_tool_reference_key(value)
    if not key:
        return ""
    try:
        from domain.tool.registry import ToolRegistry

        tools = ToolRegistry().list_tools()
    except Exception:
        return ""

    matches: set[str] = set()
    for tool in tools:
        if not isinstance(tool, dict):
            continue
        tool_id = str(tool.get("tool_id") or "").strip()
        if not tool_id:
            continue
        candidates: list[Any] = [
            tool_id,
            tool.get("name"),
            tool.get("display_name"),
        ]
        ui = tool.get("ui") if isinstance(tool.get("ui"), dict) else {}
        candidates.extend(
            [
                ui.get("composer_label"),
                ui.get("label"),
                ui.get("title"),
            ]
        )
        metadata = tool.get("metadata") if isinstance(tool.get("metadata"), dict) else {}
        aliases = metadata.get("aliases")
        if isinstance(aliases, list):
            candidates.extend(aliases)
        elif isinstance(aliases, dict):
            candidates.extend(aliases.keys())
            candidates.extend(aliases.values())
        elif isinstance(aliases, str):
            candidates.append(aliases)
        for candidate in candidates:
            if _approval_tool_reference_key(candidate) == key:
                matches.add(tool_id)
    return next(iter(matches)) if len(matches) == 1 else ""


def _approval_followup_tool_identity_matches(
    request_tool_name: str,
    followup_tool_name: str,
    *,
    details: dict[str, Any],
    operation: str,
) -> bool:
    request_tool_name = str(request_tool_name or "").strip()
    followup_tool_name = str(followup_tool_name or "").strip()
    if not request_tool_name or not followup_tool_name:
        return False
    if request_tool_name == followup_tool_name:
        return True

    followup_identity = _approval_registry_tool_identity(followup_tool_name)
    if not followup_identity:
        return False

    request_candidates = [
        request_tool_name,
        details.get("function_id") if isinstance(details, dict) else "",
        details.get("operation") if isinstance(details, dict) else "",
        operation,
    ]
    request_identities = {
        identity
        for candidate in request_candidates
        for identity in [_approval_registry_tool_identity(candidate)]
        if identity
    }
    return followup_identity in request_identities


def _duplicate_approval_replay_result(
    context: dict[str, Any] | None,
    tool_name: str,
    arguments: dict[str, Any],
) -> dict[str, Any] | None:
    if not isinstance(context, dict):
        return None
    replayed = context.get("approval_replayed")
    if not isinstance(replayed, dict):
        return None
    if str(replayed.get("tool_name") or "").strip() != tool_name:
        return None
    replayed_arguments = replayed.get("arguments")
    if not isinstance(replayed_arguments, dict):
        return None
    if _canonical_approval_replay_arguments(replayed_arguments) != _canonical_approval_replay_arguments(arguments):
        return None
    return {
        "result": "Skipped duplicate approval-followup tool call; the approved operation was already replayed once.",
        "is_error": False,
        "approval_replay_duplicate": True,
    }


def _approval_followup_tool_use(metadata: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(metadata, dict):
        return None
    followup = metadata.get("approval_followup")
    if not isinstance(followup, dict):
        return None
    token = str(followup.get("approval_token") or followup.get("token") or "").strip()
    tool_name = str(followup.get("tool_name") or "").strip()
    if not token or not tool_name:
        return None
    payload = followup.get("payload") if isinstance(followup.get("payload"), dict) else None
    if payload is None:
        payload = followup.get("arguments") if isinstance(followup.get("arguments"), dict) else None
    if payload is None:
        return None
    raw_action = str(followup.get("action") or "").strip()
    operation = str(followup.get("operation") or "").strip()
    action = operation if raw_action.startswith("tool.") and operation else raw_action or operation
    tool_name, arguments = _approval_replay_executable_arguments(
        tool_name,
        payload,
        action=action,
        operation=operation,
    )
    if tool_name in {"browser_computer", "browser_use", "computer_use"} and action and not arguments.get("action"):
        arguments["action"] = action
    token_map = {tool_name: token}
    request_id = str(followup.get("request_id") or followup.get("approval_request_id") or "").strip()
    for key in (action, operation, request_id):
        if key:
            token_map[key] = token
    if tool_name in {"computer_use", "browser_use", "browser_computer"}:
        for alias in ("computer_use", "browser_use", "browser_computer"):
            token_map[alias] = token
    return {
        "id": str(followup.get("tool_call_id") or followup.get("request_id") or gen_id()).strip(),
        "name": tool_name,
        "input": arguments,
        "approval_context": {"tool_approval_tokens": token_map},
    }


def _approval_followup_has_inline_payload(metadata: dict[str, Any] | None) -> bool:
    if not isinstance(metadata, dict):
        return False
    followup = metadata.get("approval_followup")
    if not isinstance(followup, dict):
        return False
    return isinstance(followup.get("payload"), dict) or isinstance(followup.get("arguments"), dict)


def _authority_followup_tool_use(metadata: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(metadata, dict):
        return None
    followup = metadata.get("authority_followup")
    if not isinstance(followup, dict):
        followup = metadata.get("authorityFollowup")
    if not isinstance(followup, dict):
        return None
    chat_display = metadata.get("chat_display")
    if not isinstance(chat_display, dict):
        chat_display = metadata.get("chatDisplay")
    hidden = bool(followup.get("hidden"))
    if isinstance(chat_display, dict):
        hidden = hidden or (
            bool(chat_display.get("hidden"))
            and str(chat_display.get("reason") or "").strip() == "authority_followup"
        )
    request_id = str(followup.get("request_id") or followup.get("approval_request_id") or "").strip()
    permission_id = str(followup.get("permission_id") or "").strip()
    if not (hidden and request_id and permission_id):
        return None
    return {
        "id": str(followup.get("tool_call_id") or request_id or gen_id()).strip(),
        "name": "job_resume",
        "input": {"job_id": request_id},
    }


def _merge_tool_context(base: dict[str, Any] | None, extra: dict[str, Any] | None) -> dict[str, Any]:
    merged = dict(base or {})
    if not isinstance(extra, dict):
        return merged
    for key, value in extra.items():
        if key == "tool_approval_tokens" and isinstance(value, dict):
            existing = merged.get(key) if isinstance(merged.get(key), dict) else {}
            merged[key] = {**existing, **value}
        else:
            merged[key] = value
    return merged


def _approval_request_from_tool_result(
    tool_name: str,
    tool_call_id: str,
    arguments: dict[str, Any],
    result: Any,
) -> dict[str, Any] | None:
    roots: list[dict[str, Any]] = []
    seen: set[int] = set()

    def add(value: Any) -> None:
        if not isinstance(value, dict):
            return
        marker = id(value)
        if marker in seen:
            return
        seen.add(marker)
        roots.append(value)

    add(result)
    if isinstance(result, dict):
        data = result.get("data")
        add(data)
        if isinstance(data, dict):
            nested_data = data.get("data")
            add(nested_data)
            if isinstance(nested_data, dict):
                add(nested_data.get("widget"))
                add(nested_data.get("result"))
            add(data.get("widget"))
            add(data.get("result"))
        add(result.get("widget"))
        for key in ("result", "output", "artifact", "capture"):
            add(result.get(key))

    for root in roots:
        requires_approval = bool(root.get("requires_approval") or root.get("approval_required"))
        if not requires_approval:
            continue
        payload = root.get("arguments")
        if not isinstance(payload, dict):
            root_payload = root.get("payload")
            if isinstance(root_payload, dict) and not root_payload.get("args_hash"):
                payload = root_payload
            else:
                payload = arguments
        action = str(root.get("action") or arguments.get("action") or tool_name).strip()
        return {
            "tool_name": tool_name,
            "tool_call_id": tool_call_id,
            "action": action,
            "operation": str(root.get("operation") or action).strip(),
            "payload": dict(payload or {}),
            "requires_approval": True,
            "approval_required": True,
            "approval_token": root.get("approval_token"),
            "approval_request_id": root.get("approval_request_id") or root.get("request_id"),
            "risk_level": root.get("risk_level"),
            "expires_at": root.get("expires_at"),
            "approval_expires_in_seconds": root.get("approval_expires_in_seconds"),
            "display_summary": root.get("display_summary"),
            "message": root.get("message") or root.get("approval_hint") or _APPROVAL_WAITING_TEXT,
        }
    return None


def _response_reasoning_content(response: dict[str, Any] | None) -> str:
    if not isinstance(response, dict):
        return ""
    for key in ("reasoning_content", "reasoning", "thinking"):
        value = response.get(key)
        if isinstance(value, str) and value.strip():
            return value
    metadata = response.get("metadata")
    if isinstance(metadata, dict):
        value = metadata.get("reasoning_content")
        if isinstance(value, str) and value.strip():
            return value
        thinking = metadata.get("thinking")
        if isinstance(thinking, dict):
            transcript = thinking.get("transcript")
            if isinstance(transcript, str) and transcript.strip():
                return transcript
    return ""


def _default_tool_limit_for_connected_tools(tool_limit: int, connected_tool_names: set[str]) -> int:
    if tool_limit != 4:
        return tool_limit
    if connected_tool_names.intersection({"browser_companion", "browser_computer", "browser_use", "computer_use"}):
        return 12
    if any(str(name or "").startswith("coding_") for name in connected_tool_names):
        return 12
    return tool_limit


def _legacy_tool_limit_enabled() -> bool:
    return str(os.environ.get("RUMI_FORCE_LEGACY_TOOL_LIMIT") or "").strip().lower() in {"1", "true", "yes", "on"}


def _loop_recovery_runtime_message(decision: LoopDecision) -> dict[str, Any]:
    checkpoint = decision.checkpoint or {}
    directive = decision.directive or {}
    return {
        "role": "system",
        "content": (
            "[RUNTIME LOOP RECOVERY DIRECTIVE - protected]\n"
            "The runtime detected a no-progress tool loop and compacted duplicate context. "
            "Do not repeat the forbidden action/result motif. Choose a genuinely different strategy. "
            "This directive does not grant new capabilities, approvals, workspace access, or policy changes.\n"
            f"reason: {decision.reason}\n"
            f"strategy_epoch: {directive.get('strategy_epoch')}\n"
            f"forbidden_action_signature: {directive.get('forbidden_action_signature')}\n"
            f"forbidden_result_signature: {directive.get('forbidden_result_signature')}\n"
            f"tool_sequence: {checkpoint.get('tool_sequence')}\n"
            "required novelty: change the tool target, query, inspected evidence, or implementation tactic."
        ),
        "metadata": {
            "runtime_directive": "loop_recovery",
            "recovery_id": decision.recovery_id,
            "recovery_cluster_id": decision.recovery_cluster_id,
        },
    }


def _loop_pause_response(model: str, params: dict[str, Any], decision: LoopDecision, events: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "content": [
            {
                "type": "text",
                "text": (
                    "同じパターンの自己回復が繰り返されています。"
                    "これ以上の自動継続は同じ失敗や副作用を繰り返す可能性があるため、"
                    "状態を保存して一時停止しました。別方針を入力すると続行できます。"
                ),
            }
        ],
        "finish_reason": "paused_loop",
        "usage": {},
        "events": list(events),
        "metadata": {
            "model": model,
            "loop_guard": {
                "paused": True,
                "reason": decision.reason,
                "recovery_id": decision.recovery_id,
                "recovery_cluster_id": decision.recovery_cluster_id,
                "checkpoint": decision.checkpoint,
            },
            "thinking": {"state": "completed"},
            "thinking_level": params.get("thinking_level") if isinstance(params, dict) else None,
        },
    }


def _duplicate_side_effect_response(
    model: str,
    params: dict[str, Any],
    decision: LoopDecision,
    events: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "content": [
            {
                "type": "text",
                "text": (
                    "同じ副作用を持つ操作が再提案されたため、実行前に停止しました。"
                    "必要な場合は、別方針または明示的な再実行理由を入力してください。"
                ),
            }
        ],
        "finish_reason": "duplicate_side_effect_guard",
        "usage": {},
        "events": list(events),
        "metadata": {
            "model": model,
            "loop_guard": {
                "duplicate_side_effect": True,
                "reason": decision.reason,
                "recovery_cluster_id": decision.recovery_cluster_id,
                "checkpoint": decision.checkpoint,
            },
            "thinking": {"state": "completed"},
            "thinking_level": params.get("thinking_level") if isinstance(params, dict) else None,
        },
    }


def _progress_loop_pause_response(
    model: str,
    params: dict[str, Any],
    *,
    events: list[dict[str, Any]],
    progress_state: dict[str, Any],
) -> dict[str, Any]:
    return {
        "content": [
            {
                "type": "text",
                "text": (
                    "作業状況の更新だけが続いたため、同じ状態表示を繰り返さないよう一時停止しました。"
                    "次は実際の確認・変更・検証操作に進む必要があります。"
                ),
            }
        ],
        "finish_reason": "paused_progress_loop",
        "usage": {},
        "events": list(events),
        "metadata": {
            "model": model,
            "progress_state": dict(progress_state or {}),
            "loop_guard": {"paused": True, "reason": "progress_loop"},
            "thinking": {"state": "completed"},
            "thinking_level": params.get("thinking_level") if isinstance(params, dict) else None,
        },
    }


def _external_provider_tools(provider_tools: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    return [
        tool
        for tool in provider_tools or []
        if not is_assistant_progress_tool_name(tool_name_from_definition(tool))
    ]


def _emergency_pause_response(
    model: str,
    params: dict[str, Any],
    *,
    reason: str,
    events: list[dict[str, Any]],
    tool_executions: int,
    model_turns: int,
) -> dict[str, Any]:
    return {
        "content": [
            {
                "type": "text",
                "text": (
                    "内部の安全予算に達したため、状態を保存して一時停止しました。"
                    "これは通常の max_tool_calls ではなく、資源暴走を防ぐ operator emergency brake です。"
                ),
            }
        ],
        "finish_reason": "paused_emergency_budget",
        "usage": {},
        "events": list(events),
        "metadata": {
            "model": model,
            "emergency_budget": {
                "paused": True,
                "reason": reason,
                "tool_executions": tool_executions,
                "model_turns": model_turns,
            },
            "thinking": {"state": "completed"},
            "thinking_level": params.get("thinking_level") if isinstance(params, dict) else None,
        },
    }


def _approval_waiting_response(
    model: str,
    approval_request: dict[str, Any],
    params: dict[str, Any],
    events: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "content": [{"type": "text", "text": _APPROVAL_WAITING_TEXT}],
        "finish_reason": "approval_required",
        "usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
        "metadata": {
            "model": model,
            "pending_approval": approval_request,
            "thinking_level": params.get("thinking_level"),
        },
        "events": list(events),
    }


def _approval_followup_terminal_response(
    model: str,
    params: dict[str, Any],
    events: list[dict[str, Any]],
    *,
    message: str,
    request_id: str,
    tool_name: str,
    operation: str,
    status: str,
    code: str = "",
) -> dict[str, Any]:
    return {
        "content": [{"type": "text", "text": message}],
        "finish_reason": "stop",
        "usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
        "metadata": {
            "model": model,
            "approval_followup": {
                "status": status,
                "code": code,
                "request_id": request_id,
                "tool_name": tool_name,
                "operation": operation,
            },
            "thinking": {"state": "completed"},
            "thinking_level": params.get("thinking_level") if isinstance(params, dict) else None,
        },
        "events": list(events),
    }


def _authority_waiting_response(
    model: str,
    approval_request: dict[str, Any],
    params: dict[str, Any],
    events: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "content": [{"type": "text", "text": _AUTHORITY_WAITING_TEXT}],
        "finish_reason": "authority_approval_required",
        "usage": {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
        "metadata": {
            "model": model,
            "pendingAuthorityApproval": approval_request,
            "thinking_level": params.get("thinking_level"),
        },
        "events": list(events),
    }


class _InlineThoughtFilter:
    _tag_pairs = (
        ("<thought>", "</thought>"),
        ("<think>", "</think>"),
    )

    def __init__(self) -> None:
        self._buffer = ""
        self._in_thought = False
        self._active_close_tag = ""
        self._thought_parts: list[str] = []
        self._streamed_thought_len = 0

    def push(self, text: Any) -> str:
        self._buffer += str(text or "")
        visible = []
        while self._buffer:
            if self._in_thought:
                close_index = self._buffer.find(self._active_close_tag)
                if close_index == -1:
                    self._thought_parts.append(self._buffer)
                    self._buffer = ""
                    break
                self._thought_parts.append(self._buffer[:close_index])
                self._buffer = self._buffer[close_index + len(self._active_close_tag):]
                self._in_thought = False
                self._active_close_tag = ""
                continue

            tag_match = self._next_open_tag(self._buffer)
            if tag_match is not None:
                open_index, open_tag, close_tag = tag_match
                visible.append(self._buffer[:open_index])
                self._buffer = self._buffer[open_index + len(open_tag):]
                self._in_thought = True
                self._active_close_tag = close_tag
                continue

            keep = self._partial_open_tag_suffix_len(self._buffer)
            if keep:
                visible.append(self._buffer[:-keep])
                self._buffer = self._buffer[-keep:]
                break
            visible.append(self._buffer)
            self._buffer = ""
            break
        return "".join(visible)

    def finish(self) -> str:
        visible = ""
        if self._buffer:
            if self._in_thought:
                self._thought_parts.append(self._buffer)
            else:
                visible = self._buffer
        self._buffer = ""
        return visible

    def pending_thinking_delta(self) -> str:
        transcript = "".join(self._thought_parts)
        delta = transcript[self._streamed_thought_len:]
        self._streamed_thought_len = len(transcript)
        return delta

    def transcript(self) -> str:
        return "".join(self._thought_parts).strip()

    @classmethod
    def _partial_open_tag_suffix_len(cls, text: str) -> int:
        keep = 0
        for open_tag, _ in cls._tag_pairs:
            max_len = min(len(text), len(open_tag) - 1)
            for size in range(max_len, 0, -1):
                if open_tag.startswith(text[-size:]):
                    keep = max(keep, size)
                    break
        return keep

    @classmethod
    def _next_open_tag(cls, text: str) -> tuple[int, str, str] | None:
        best: tuple[int, str, str] | None = None
        for open_tag, close_tag in cls._tag_pairs:
            index = text.find(open_tag)
            if index == -1:
                continue
            if best is None or index < best[0]:
                best = (index, open_tag, close_tag)
        return best


class _AssistantDraft:
    _min_sync_interval_seconds = 0.15

    def __init__(
        self,
        *,
        store: ChatStore,
        conversation_id: str,
        parent_id: str,
        sequence_number: int,
        model: str,
        params: dict[str, Any],
    ) -> None:
        self._store = store
        self._conversation_id = conversation_id
        self._model = model
        self._params = params
        self._last_sync_at = 0.0
        self._last_signature: tuple[Any, ...] | None = None
        self.message = store.add_message(
            conversation_id,
            {
                "role": "assistant",
                "parent_id": parent_id,
                "sequence_number": sequence_number,
                "content": [],
                "raw_text": "",
                "finish_reason": "streaming",
                "usage": {},
                "widget": None,
                "metadata": {
                    "model": model,
                    "streaming": True,
                    "draft": True,
                    "thinking": {"state": "running"},
                    "thinking_level": params.get("thinking_level"),
                },
                "events": [],
                "tool_logs": [],
                "model": model,
            },
        )

    @property
    def id(self) -> str:
        return str((self.message or {}).get("id") or "")

    def update(
        self,
        *,
        content_text: str,
        thinking_transcript: str,
        events: list[dict[str, Any]],
        tool_logs: list[dict[str, Any]],
        finish_reason: str = "streaming",
        thinking_state: str = "running",
        usage: dict[str, Any] | None = None,
        metadata_extra: dict[str, Any] | None = None,
        force: bool = False,
    ) -> None:
        if not self.message:
            return
        signature = self._signature(
            content_text=content_text,
            thinking_transcript=thinking_transcript,
            events=events,
            tool_logs=tool_logs,
            finish_reason=finish_reason,
            thinking_state=thinking_state,
            usage=usage,
            metadata_extra=metadata_extra,
        )
        now = time.monotonic()
        if signature == self._last_signature:
            return
        if not force and self._last_sync_at and (now - self._last_sync_at) < self._min_sync_interval_seconds:
            return
        metadata = {
            "model": self._model,
            "streaming": True,
            "draft": True,
            "thinking": {"state": thinking_state},
            "thinking_level": self._params.get("thinking_level"),
        }
        if thinking_transcript:
            metadata["thinking"]["transcript"] = thinking_transcript
        if isinstance(metadata_extra, dict):
            metadata.update(metadata_extra)
        updated = self._store.update_message(
            self._conversation_id,
            self.id,
            {
                "content": [{"type": "text", "text": content_text}],
                "raw_text": content_text,
                "finish_reason": finish_reason,
                "usage": usage if usage is not None else {},
                "metadata": metadata,
                "events": list(events),
                "tool_logs": list(tool_logs),
                "model": self._model,
            },
        )
        if updated is not None:
            self.message = updated
            self._last_signature = signature
            self._last_sync_at = now

    def finalize(self, assistant_message: dict[str, Any]) -> dict[str, Any] | None:
        if not self.message:
            return assistant_message
        updates = dict(assistant_message)
        metadata = dict(updates.get("metadata") or {})
        metadata.pop("streaming", None)
        metadata.pop("draft", None)
        updates["metadata"] = metadata
        return self._store.update_message(self._conversation_id, self.id, updates)

    def cancel(
        self,
        *,
        content_text: str,
        thinking_transcript: str,
        events: list[dict[str, Any]],
        tool_logs: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        if not self.message:
            return None
        final_text = content_text if content_text.strip() else "停止しました。"
        metadata = {
            "model": self._model,
            "thinking": {"state": "cancelled"},
            "thinking_level": self._params.get("thinking_level"),
            "cancelled": True,
        }
        if thinking_transcript:
            metadata["thinking"]["transcript"] = thinking_transcript
        updated = self._store.update_message(
            self._conversation_id,
            self.id,
            {
                "content": [{"type": "text", "text": final_text}],
                "raw_text": final_text,
                "finish_reason": "cancelled",
                "usage": {},
                "metadata": metadata,
                "events": list(events),
                "tool_logs": list(tool_logs),
                "model": self._model,
            },
        )
        if updated is not None:
            self.message = updated
        return updated

    def fail(
        self,
        *,
        content_text: str,
        thinking_transcript: str,
        events: list[dict[str, Any]],
        tool_logs: list[dict[str, Any]],
        reason: str = "stream_interrupted",
    ) -> dict[str, Any] | None:
        if not self.message:
            return None
        final_text = content_text.strip() or "応答ストリームが中断しました。最後の tool 結果を確認してください。"
        metadata = {
            "model": self._model,
            "thinking": {"state": "failed"},
            "thinking_level": self._params.get("thinking_level"),
            "interrupted": True,
            "interruption_reason": reason,
        }
        if thinking_transcript:
            metadata["thinking"]["transcript"] = thinking_transcript
        updated = self._store.update_message(
            self._conversation_id,
            self.id,
            {
                "content": [{"type": "text", "text": final_text}],
                "raw_text": final_text,
                "finish_reason": "error",
                "usage": {},
                "metadata": metadata,
                "events": list(events),
                "tool_logs": list(tool_logs),
                "model": self._model,
            },
        )
        if updated is not None:
            self.message = updated
        return updated

    def discard(self) -> None:
        if not self.message:
            return
        try:
            self._store.delete_message(self._conversation_id, self.id)
        except Exception:
            pass

    @staticmethod
    def _signature(
        *,
        content_text: str,
        thinking_transcript: str,
        events: list[dict[str, Any]],
        tool_logs: list[dict[str, Any]],
        finish_reason: str,
        thinking_state: str,
        usage: dict[str, Any] | None,
        metadata_extra: dict[str, Any] | None,
    ) -> tuple[Any, ...]:
        last_event = events[-1] if events else None
        last_tool_log = tool_logs[-1] if tool_logs else None
        usage_items = tuple(sorted((usage or {}).items())) if isinstance(usage, dict) else ()
        metadata_items = tuple(sorted((metadata_extra or {}).items())) if isinstance(metadata_extra, dict) else ()
        return (
            content_text,
            thinking_transcript,
            finish_reason,
            thinking_state,
            len(events),
            repr(last_event),
            len(tool_logs),
            repr(last_tool_log),
            usage_items,
            metadata_items,
        )


class ChatRunEngine:
    def __init__(
        self,
        *,
        store: ChatStore | None = None,
        client: AIClient | None = None,
        gateway: LLMGateway | None = None,
    ) -> None:
        self._store = store or ChatStore()
        self._gateway = gateway or LLMGateway(client=client)
        self._run_id = ""
        self._conversation_id = ""
        self._event_seq = 0
        self._cancel_event = threading.Event()
        self._current_stream: Any = None
        self._activity_events: list[dict[str, Any]] = []
        self._tool_logs: list[dict[str, Any]] = []
        self._thinking_transcript_parts: list[str] = []
        self._text_parts: list[str] = []
        self._started_tool_call_ids: set[str] = set()
        self._browser_state_revision = 0
        self._stream_mode = True
        self._progress_updates = 0
        self._progress_signatures: set[tuple[str, str, str, str]] = set()
        self._progress_without_external_tool = 0
        self._progress_state: dict[str, Any] = {}
        self._provider_trace_requests: list[dict[str, Any]] = []

    def stream(
        self,
        input_data: dict[str, Any],
        context: dict[str, Any] | None = None,
        *,
        stream_mode: bool = True,
    ) -> Iterator[dict[str, Any]]:
        prepared = prepare_chat_run(input_data, context)
        self._run_id = gen_id()
        self._conversation_id = prepared.conversation_id
        self._event_seq = 0
        self._activity_events = []
        self._tool_logs = []
        self._thinking_transcript_parts = []
        self._text_parts = []
        self._started_tool_call_ids = set()
        self._browser_state_revision = 0
        self._stream_mode = bool(stream_mode)
        self._progress_updates = 0
        self._progress_signatures = set()
        self._progress_without_external_tool = 0
        self._progress_state = {}
        self._provider_trace_requests = []
        self._cancel_event = threading.Event()
        self._current_stream = None

        cancellation_registry = get_chat_cancellation_registry()

        def request_cancel() -> None:
            self._cancel_event.set()
            close = getattr(self._current_stream, "close", None)
            if callable(close):
                try:
                    close()
                except Exception:
                    pass

        draft: _AssistantDraft | None = None
        draft_completed = False
        cancellation_registry.register(prepared.conversation_id, request_cancel)
        try:
            yield self._emit(
                "run_started",
                data={
                    "model": prepared.model,
                    "request_id": prepared.request_id,
                    "stream_mode": stream_mode,
                    "model_routing": prepared.model_routing,
                    "chat_references": dict(prepared.chat_references or {}),
                },
                message="chat run started",
            )
            if _should_emit_model_routing_status(prepared.model_routing):
                yield self._emit(
                    "status",
                    data=prepared.model_routing,
                    message="model routing prepared",
                    phase="model_routing",
                    model=prepared.model,
                )
            yield self._emit(
                "user_message_committed",
                data={"message": prepared.user_message},
                message="user message committed",
            )
            tool_selection = prepared.request_context.get("tool_selection") if isinstance(prepared.request_context, dict) else None
            if isinstance(tool_selection, dict) and tool_selection.get("selection_id"):
                yield self._emit(
                    "tool_selection_started",
                    data={
                        "selection_id": tool_selection.get("selection_id"),
                        "mode": tool_selection.get("mode"),
                        "strategy": tool_selection.get("strategy"),
                    },
                    message="機能を選定しています",
                    phase="tool_selection",
                )
                yield self._emit(
                    "tool_selection_completed",
                    data=tool_selection,
                    message=_tool_selection_activity_message(tool_selection),
                    phase="tool_selection",
                )

            assistant_seq = int(prepared.user_message.get("sequence_number", 1) or 1) + 1
            if stream_mode:
                draft = _AssistantDraft(
                    store=self._store,
                    conversation_id=prepared.conversation_id,
                    parent_id=str(prepared.user_message["id"]),
                    sequence_number=assistant_seq,
                    model=prepared.model,
                    params=prepared.params,
                )
                if draft.message is not None:
                    yield self._emit(
                        "assistant_message_started",
                        data={"message": draft.message},
                        message="assistant draft created",
                    )

            visible_provider_tools = _external_provider_tools(prepared.provider_tools)
            if visible_provider_tools:
                yield self._emit(
                    "status",
                    data={"model": prepared.model},
                    message="{} が考えています".format(prepared.model),
                    phase="thinking",
                    model=prepared.model,
                )
                yield self._emit(
                    "status",
                    data={"tool_count": len(visible_provider_tools)},
                    message="{} 個の tool を接続しました".format(len(visible_provider_tools)),
                    phase="tools_attached",
                )
            self._sync_draft(draft, force=True)

            try:
                self._raise_if_cancelled()
                try:
                    from domain.chat.run_request import prefocus_computer_use_target_window

                    prefocus_computer_use_target_window(prepared)
                except Exception:
                    pass
                response = yield from self._execute(prepared, draft)
            except _ChatCancelled:
                cancelled_event = self._emit(
                    "cancelled",
                    data={"reason": "cancelled"},
                    message="cancelled",
                    reason="cancelled",
                )
                if draft is not None:
                    draft.cancel(
                        content_text="".join(self._text_parts),
                        thinking_transcript="".join(self._thinking_transcript_parts),
                        events=list(self._activity_events),
                        tool_logs=list(self._tool_logs),
                    )
                    draft_completed = True
                yield cancelled_event
                return
            except RuntimeError as exc:
                task_failed_event = self._emit(
                    "task_failed",
                    data={"error": str(exc), "terminal": True},
                    message="APIエラーでタスクを終了しました",
                    phase="task_failed",
                    error=str(exc),
                    terminal=True,
                )
                yield task_failed_event
                response = _ai_error_response(
                    prepared.model,
                    str(exc),
                    prepared.params,
                    events=list(self._activity_events),
                )
            except Exception as exc:
                message_text = "AI request failed: " + str(exc)
                task_failed_event = self._emit(
                    "task_failed",
                    data={"error": message_text, "terminal": True},
                    message="APIエラーでタスクを終了しました",
                    phase="task_failed",
                    error=message_text,
                    terminal=True,
                )
                yield task_failed_event
                response = _ai_error_response(
                    prepared.model,
                    message_text,
                    prepared.params,
                    events=list(self._activity_events),
                )

            finalized_response = self._final_response(prepared, response)
            self._log_inspector(prepared, finalized_response)
            assistant_message = build_assistant_message(
                conversation_id=prepared.conversation_id,
                parent_id=prepared.user_message["id"],
                sequence_number=assistant_seq,
                response=finalized_response,
                model=prepared.model,
            )
            if draft is not None:
                stored = draft.finalize(assistant_message)
            else:
                stored = self._store.add_message(prepared.conversation_id, assistant_message)
            if stored is None:
                yield self._emit(
                    "error",
                    data={"error": {"message": "Failed to add assistant message"}},
                    message="Failed to add assistant message",
                )
                return
            sync_conversation_kanban(prepared.conversation_id, reason="stream_completed")
            draft_completed = True

            yield self._emit(
                "assistant_message_completed",
                data={"message": stored},
                message="assistant message completed",
            )
            steer_processed = self._process_conversation_steer(prepared.conversation_id, context or {})
            if steer_processed:
                yield self._emit(
                    "status",
                    data={"processed": steer_processed},
                    message="次の steer を送信しました",
                    phase="conversation_steer",
                )
            yield self._emit(
                "done",
                data={"message": stored},
                message="done",
            )
        finally:
            self._cancel_event.set()
            if draft is not None and not draft_completed:
                try:
                    draft.fail(
                        content_text="".join(self._text_parts),
                        thinking_transcript="".join(self._thinking_transcript_parts),
                        events=list(self._activity_events),
                        tool_logs=list(self._tool_logs),
                    )
                except Exception:
                    pass
            cancellation_registry.unregister(prepared.conversation_id, request_cancel)

    def _process_conversation_steer(self, conversation_id: str, context: dict[str, Any]) -> list[dict[str, Any]]:
        try:
            from domain.chat.steer import ConversationSteerStore

            return ConversationSteerStore().process_for_conversation(
                conversation_id,
                context=context,
            )
        except Exception as exc:
            self._emit(
                "status",
                data={"error": str(exc)},
                message="conversation steer の処理に失敗しました",
                phase="conversation_steer_failed",
            )
            return []

    @staticmethod
    def _is_assistant_progress_tool_use(block: dict[str, Any]) -> bool:
        name = str(block.get("name") or block.get("tool_name") or "").strip()
        return is_assistant_progress_tool_name(name)

    def _execute_assistant_progress_tool_use(
        self,
        working_messages: list[dict[str, Any]],
        working_ir: Any,
        draft: _AssistantDraft | None,
        block: dict[str, Any],
        *,
        has_external_tool_in_cycle: bool,
    ) -> Iterator[dict[str, Any]]:
        tool_call_id = str(block.get("id") or block.get("tool_call_id") or gen_id()).strip()
        payload, errors = normalize_assistant_progress_payload(self._tool_arguments(block))
        signature = (
            str(payload.get("phase") or ""),
            str(payload.get("status") or ""),
            str(payload.get("summary") or ""),
            str(payload.get("next_action") or ""),
        )
        result_status = "ok"
        result_reason = ""
        if signature in self._progress_signatures:
            result_status = "ignored"
            result_reason = "duplicate"
        elif self._progress_updates >= ASSISTANT_PROGRESS_MAX_UPDATES:
            result_status = "ignored"
            result_reason = "max_updates"
        elif not has_external_tool_in_cycle and self._progress_without_external_tool >= 2:
            result_status = "blocked"
            result_reason = "progress_loop"
        else:
            self._progress_signatures.add(signature)
            self._progress_updates += 1
            if has_external_tool_in_cycle:
                self._progress_without_external_tool = 0
            else:
                self._progress_without_external_tool += 1
            self._progress_state = {
                **payload,
                "updated_seq": self._event_seq + 1,
                "tool_call_id": tool_call_id,
            }
            yield self._emit(
                "assistant_progress",
                data={
                    **payload,
                    "tool_call_id": tool_call_id,
                    "validation_warnings": errors,
                },
                message=str(payload.get("summary") or ""),
                tool_call_id=tool_call_id,
            )
            self._sync_draft(draft, force=True)

        result = {
            "status": result_status,
            "summary": payload.get("summary"),
            "next_action": payload.get("next_action"),
            "reason": result_reason,
        }
        _append_tool_result_message(working_messages, ASSISTANT_PROGRESS_TOOL_NAME, result, tool_call_id)
        try:
            append_tool_result_to_ir(working_ir, ASSISTANT_PROGRESS_TOOL_NAME, result, tool_call_id)
        except Exception:
            pass
        if result_status == "blocked":
            yield self._emit(
                "run_paused_loop",
                data={"reason": result_reason, "progress_state": dict(self._progress_state or payload)},
                message="進捗更新だけが続いたため一時停止しました",
                phase="run_paused_loop",
            )
            self._sync_draft(draft, force=True)
            return {"blocked": True, "reason": result_reason, "progress_state": dict(self._progress_state or payload)}
        return None

    def _execute_tool_use(
        self,
        prepared: PreparedChatRun,
        working_messages: list[dict[str, Any]],
        working_ir: Any,
        draft: _AssistantDraft | None,
        block: dict[str, Any],
    ) -> Iterator[dict[str, Any]]:
        self._raise_if_cancelled()
        tool_name = str(block.get("name") or block.get("tool_name") or "").strip()
        if not tool_name:
            return None
        tool_call_id = str(block.get("id") or block.get("tool_call_id") or gen_id()).strip()
        arguments = self._tool_arguments(block)
        tool_name, arguments = _normalize_tool_call_name_and_arguments(tool_name, arguments)
        if tool_call_id not in self._started_tool_call_ids:
            self._started_tool_call_ids.add(tool_call_id)
            display_payload = _tool_display_payload(tool_name, arguments, status="running")
            event = self._emit(
                "tool_call_started",
                data={"tool_name": tool_name, "tool_call_id": tool_call_id, "arguments": arguments, **display_payload},
                message=display_payload["display_text"],
                phase="tool_call_started",
                tool_name=tool_name,
                tool_call_id=tool_call_id,
                arguments=arguments,
            )
            self._sync_draft(draft, force=True)
            yield event
        for event in self._before_tool_call(prepared, tool_name, tool_call_id, arguments):
            yield event
        result = _duplicate_approval_replay_result(prepared.tool_context, tool_name, arguments)
        if result is None:
            approval_context = block.get("approval_context") if isinstance(block.get("approval_context"), dict) else None
            original_tool_context = prepared.tool_context
            if approval_context:
                prepared.tool_context = _merge_tool_context(prepared.tool_context, approval_context)
            try:
                result = self._execute_tool(prepared, tool_name, tool_call_id, arguments)
            finally:
                if approval_context:
                    prepared.tool_context = original_tool_context
        self._raise_if_cancelled()
        summary = _tool_result_summary(tool_name, result)
        artifacts = _tool_result_artifacts(result)
        status = "failed" if _tool_result_is_error(result) else "completed"
        display_payload = _tool_display_payload(tool_name, arguments, status=status, summary=summary)
        for event in self._after_tool_call(prepared, tool_name, tool_call_id, arguments, result):
            yield event
        completed_event = self._emit(
            "tool_call_completed",
            data={
                "tool_name": tool_name,
                "tool_call_id": tool_call_id,
                "is_error": _tool_result_is_error(result),
                "recovery_kind": _tool_result_recovery_kind(result),
                "result_summary": summary,
                "summary": summary,
                **display_payload,
                "result": _bounded_compact_tool_result(result, summary, artifacts),
                "artifacts": artifacts,
                "artifact_paths": [artifact.get("path") for artifact in artifacts if artifact.get("path")],
            },
            message=display_payload["display_text"],
            phase="tool_call_completed",
            tool_name=tool_name,
            tool_call_id=tool_call_id,
            is_error=_tool_result_is_error(result),
        )
        self._sync_draft(draft, force=True)
        yield completed_event
        approval_request = _approval_request_from_tool_result(tool_name, tool_call_id, arguments, result)
        if approval_request is not None:
            approval_event = self._emit(
                "approval_requested",
                data=approval_request,
                message=_APPROVAL_WAITING_TEXT,
                phase="approval_requested",
                tool_name=tool_name,
                tool_call_id=tool_call_id,
                requires_approval=True,
            )
            self._sync_draft(draft, force=True)
            yield approval_event
            return _approval_waiting_response(
                prepared.model,
                approval_request,
                prepared.params,
                events=list(self._activity_events),
            )
        _append_tool_result_message(working_messages, tool_name, result, tool_call_id, model=prepared.model)
        try:
            append_tool_result_to_ir(working_ir, tool_name, result, tool_call_id, model=prepared.model)
        except Exception:
            pass

        recovery_kind = _tool_result_recovery_kind(result)
        if recovery_kind in {"visible_window_required", "focus_required"}:
            blocked_response = _tool_blocked_response(tool_name, result)
            yield self._emit(
                "status",
                data={"tool_name": tool_name, "tool_call_id": tool_call_id, "recovery_kind": recovery_kind},
                message="可視画面外の tool 実行要求のため停止しました",
                phase="tool_blocked",
                tool_name=tool_name,
                tool_call_id=tool_call_id,
            )
            return blocked_response
        return None

    def _execute(self, prepared: PreparedChatRun, draft: _AssistantDraft | None) -> Iterator[dict[str, Any]]:
        working_messages = list(prepared.standard_messages)
        working_ir = prepared.provider_chat_ir or prepared.chat_ir
        # Deterministic approval-followup replay (single-shot, before model loop).
        # When the UI delivers an ``approval_followup`` whose token + tool_name +
        # request_id resolve to an approved pending tool, we replay that exact
        # pending tool once with the stored approved arguments before letting
        # the model speak. This removes any reliance on the model deciding to
        # re-issue the tool call from natural-language hints, which was the
        # root cause of executed_tools=[] hallucinated commit-success bugs.
        #
        # If the replay surfaces an approval/blocked response (the tool itself
        # still needs approval, or recovery is blocked) the helper returns a
        # fully formed response and we short-circuit the model loop here.
        replay_blocked = yield from self._replay_approval_followup_if_present(
            prepared, working_messages, working_ir, draft,
        )
        if replay_blocked is not None:
            return replay_blocked
        tool_context_message = _tool_visibility_message(prepared.provider_tools)
        if tool_context_message is not None:
            insert_at = 1 if working_messages and working_messages[0].get("role") == "system" else 0
            working_messages.insert(insert_at, tool_context_message)

        response = None
        blocked_response = None
        tool_execution_limit = max_tool_calls(prepared.tool_context or {})
        if tool_execution_limit is None:
            tool_execution_limit = explicit_param_max_tool_calls(prepared.params)
        if tool_execution_limit is None and _legacy_tool_limit_enabled():
            tool_execution_limit = _default_tool_limit_for_connected_tools(4, prepared.connected_tool_names)
        emergency_budget = emergency_budget_from_context(prepared.tool_context or {})
        loop_guard = LoopGuard(
            run_id=self._run_id,
            conversation_id=prepared.conversation_id,
            task_lineage_id=str(prepared.request_context.get("task_lineage_id") or prepared.conversation_id),
            config=loop_guard_config_from_context(prepared.tool_context or {}),
        )

        approval_followup = _approval_followup_tool_use(prepared.user_message.get("metadata"))
        approval_replay_state = prepared.tool_context if isinstance(prepared.tool_context, dict) else {}
        allow_inline_followup = (
            approval_followup is not None
            and _approval_followup_has_inline_payload(prepared.user_message.get("metadata"))
            and not approval_replay_state.get("approval_replayed")
            and not approval_replay_state.get("_approval_followup_block_legacy")
        )
        if allow_inline_followup:
            _append_assistant_tool_use_message(working_messages, [approval_followup])
            try:
                append_assistant_tool_use_to_ir(working_ir, [approval_followup])
            except Exception:
                pass
            blocked_response = yield from self._execute_tool_use(
                prepared,
                working_messages,
                working_ir,
                draft,
                approval_followup,
            )
            if blocked_response is not None:
                response = blocked_response
                return response

        authority_followup = _authority_followup_tool_use(prepared.user_message.get("metadata"))
        if authority_followup is not None and isinstance(prepared.tool_context, dict):
            prepared.tool_context["authority_resume_followup_applied"] = {
                "request_id": authority_followup.get("input", {}).get("job_id"),
                "tool_name": authority_followup.get("name"),
            }

        model_turns = 0
        for step_index in range(max(1, emergency_budget.max_model_turns)):
            model_turns = step_index + 1
            self._raise_if_cancelled()
            for event in self._inject_conversation_steer(prepared.conversation_id, working_messages):
                yield event
            try:
                response, tool_uses = yield from self._model_turn(prepared, working_messages, draft)
            except AuthorityApprovalRequired as exc:
                approval_request = exc.decision.to_approval_event()
                approval_event = self._emit(
                    "approval_requested",
                    data=approval_request,
                    message=_AUTHORITY_WAITING_TEXT,
                    phase="approval_requested",
                    requires_approval=True,
                    authority=True,
                )
                self._sync_draft(draft, force=True)
                yield approval_event
                response = _authority_waiting_response(
                    prepared.model,
                    approval_request,
                    prepared.params,
                    events=list(self._activity_events),
                )
                tool_uses = []
            if tool_uses:
                external_tool_uses = [
                    block for block in tool_uses if not self._is_assistant_progress_tool_use(block)
                ]
                proposal_decision = loop_guard.inspect_proposal(external_tool_uses)
                if proposal_decision.kind == "duplicate_side_effect":
                    yield self._emit(
                        "run_paused_loop",
                        data=proposal_decision.event_data(),
                        message="同じ副作用操作の再実行を防ぐため停止しました",
                        phase="run_paused_loop",
                    )
                    response = _duplicate_side_effect_response(
                        prepared.model,
                        prepared.params,
                        proposal_decision,
                        list(self._activity_events),
                    )
                    self._sync_draft(draft, force=True)
                    break
            else:
                external_tool_uses = []

            planned_tool_executions = len(self._tool_logs) + len(external_tool_uses or [])
            if external_tool_uses and tool_execution_limit is not None and planned_tool_executions > tool_execution_limit:
                response = {
                    "content": [{"type": "text", "text": _tool_limit_message(tool_execution_limit, external_tool_uses)}],
                    "finish_reason": "tool_call_limit",
                    "usage": response.get("usage", {}) if isinstance(response, dict) else {},
                    "metadata": {
                        "max_tool_calls_reached": True,
                        "tool_executions": len(self._tool_logs),
                        "pending_tool_uses": [
                            {
                                "name": str(block.get("name") or block.get("tool_name") or ""),
                                "id": str(block.get("id") or block.get("tool_call_id") or ""),
                            }
                            for block in external_tool_uses
                        ],
                    },
                }
                yield self._emit(
                    "status",
                    data={"tool_count": len(self._tool_logs), "max_tool_calls": tool_execution_limit},
                    message="tool call の上限に達したため停止しました",
                    phase="tool_call_limit",
                )
                self._sync_draft(draft, force=True)
                break
            if external_tool_uses and model_turns >= emergency_budget.max_model_turns:
                yield self._emit(
                    "run_paused_emergency",
                    data={
                        "model_turns": model_turns,
                        "max_model_turns": emergency_budget.max_model_turns,
                        "pending_tool_uses": len(tool_uses),
                    },
                    message="内部安全予算に達したため一時停止しました",
                    phase="run_paused_emergency",
                )
                response = _emergency_pause_response(
                    prepared.model,
                    prepared.params,
                    reason="max_model_turns",
                    events=list(self._activity_events),
                    tool_executions=len(self._tool_logs),
                    model_turns=model_turns,
                )
                self._sync_draft(draft, force=True)
                break
            if external_tool_uses and planned_tool_executions > emergency_budget.max_tool_executions:
                yield self._emit(
                    "run_paused_emergency",
                    data={
                        "tool_executions": len(self._tool_logs),
                        "pending_tool_uses": len(tool_uses),
                        "max_tool_executions": emergency_budget.max_tool_executions,
                    },
                    message="内部安全予算に達したため一時停止しました",
                    phase="run_paused_emergency",
                )
                response = _emergency_pause_response(
                    prepared.model,
                    prepared.params,
                    reason="max_tool_executions",
                    events=list(self._activity_events),
                    tool_executions=len(self._tool_logs),
                    model_turns=model_turns,
                )
                self._sync_draft(draft, force=True)
                break
            if not tool_uses:
                break

            _append_assistant_tool_use_message(
                working_messages,
                tool_uses,
                reasoning_content=_response_reasoning_content(response),
            )
            try:
                append_assistant_tool_use_to_ir(
                    working_ir,
                    tool_uses,
                    reasoning_content=_response_reasoning_content(response),
                )
            except Exception:
                pass
            logs_before_cycle = len(self._tool_logs)
            for block in tool_uses:
                if self._is_assistant_progress_tool_use(block):
                    progress_blocked = yield from self._execute_assistant_progress_tool_use(
                        working_messages,
                        working_ir,
                        draft,
                        block,
                        has_external_tool_in_cycle=bool(external_tool_uses),
                    )
                    if isinstance(progress_blocked, dict) and progress_blocked.get("blocked"):
                        blocked_response = _progress_loop_pause_response(
                            prepared.model,
                            prepared.params,
                            events=list(self._activity_events),
                            progress_state=progress_blocked.get("progress_state") if isinstance(progress_blocked.get("progress_state"), dict) else {},
                        )
                        break
                else:
                    blocked_response = yield from self._execute_tool_use(
                        prepared,
                        working_messages,
                        working_ir,
                        draft,
                        block,
                    )
                    self._progress_without_external_tool = 0
                if blocked_response is not None:
                    break
            if blocked_response is not None:
                response = blocked_response
                break
            new_tool_logs = self._tool_logs[logs_before_cycle:]
            if new_tool_logs:
                observation = build_loop_observation(
                    tool_uses=tool_uses,
                    tool_logs=new_tool_logs,
                    response=response,
                )
                loop_decision = loop_guard.observe_cycle(observation)
                if loop_decision.kind == "recover":
                    yield self._emit(
                        "loop_recovery_started",
                        data=loop_decision.event_data(),
                        message="同じ操作が進展なく繰り返されたため、履歴を整理して別方針へ切り替えます",
                        phase="loop_recovery_started",
                    )
                    compacted: dict[str, Any] = {}
                    try:
                        compacted = ContextCompressor().compact(
                            working_messages,
                            metadata={
                                "run_id": self._run_id,
                                "conversation_id": prepared.conversation_id,
                                "goal": prepared.user_text,
                                "next_steps": loop_decision.directive.get("required_novelty_dimensions", []),
                            },
                        )
                        replacement_history = list(compacted.get("replacement_history") or working_messages)
                    except Exception as exc:
                        yield self._emit(
                            "run_paused_loop",
                            data={"error": str(exc), **loop_decision.event_data()},
                            message="loop recovery checkpoint の生成に失敗したため一時停止しました",
                            phase="run_paused_loop",
                        )
                        response = _loop_pause_response(
                            prepared.model,
                            prepared.params,
                            loop_decision,
                            list(self._activity_events),
                        )
                        break
                    replacement_history.append(_loop_recovery_runtime_message(loop_decision))
                    working_messages[:] = replacement_history
                    try:
                        working_ir = legacy_standard_messages_to_ir(working_messages, prepared.conversation_id)
                    except Exception:
                        pass
                    yield self._emit(
                        "loop_checkpoint_created",
                        data={
                            **loop_decision.event_data(),
                            "tokens_before": compacted.get("tokens_before"),
                            "tokens_after": compacted.get("tokens_after"),
                        },
                        message="重複した履歴を圧縮し、進捗を保持しました",
                        phase="loop_checkpoint_created",
                    )
                    yield self._emit(
                        "loop_strategy_changed",
                        data=loop_decision.event_data(),
                        message="別方針で続行します",
                        phase="loop_strategy_changed",
                    )
                    yield self._emit(
                        "loop_recovery_completed",
                        data=loop_decision.event_data(),
                        message="作業内容を保持したまま再開しました",
                        phase="loop_recovery_completed",
                    )
                    self._sync_draft(draft, force=True)
                    continue
                if loop_decision.kind == "pause":
                    yield self._emit(
                        "loop_recovery_recurred",
                        data=loop_decision.event_data(),
                        message="同じパターンの自己回復が繰り返されています",
                        phase="loop_recovery_recurred",
                    )
                    yield self._emit(
                        "run_paused_loop",
                        data={**loop_decision.event_data(), "recoverable": True, "requires_user_strategy": True},
                        message="loop guard により一時停止しました",
                        phase="run_paused_loop",
                    )
                    response = _loop_pause_response(
                        prepared.model,
                        prepared.params,
                        loop_decision,
                        list(self._activity_events),
                    )
                    self._sync_draft(draft, force=True)
                    break

        return response or _ai_error_response(
            prepared.model,
            "AI provider did not return a response",
            prepared.params,
            events=list(self._activity_events),
        )

    def _inject_conversation_steer(self, conversation_id: str, working_messages: list[dict[str, Any]]) -> Iterator[dict[str, Any]]:
        try:
            from domain.chat.steer import ConversationSteerStore

            items = ConversationSteerStore().consume_for_conversation(conversation_id)
        except Exception as exc:
            yield self._emit(
                "status",
                data={"error": str(exc)},
                message="conversation steer の取得に失敗しました",
                phase="conversation_steer_failed",
            )
            return
        prompts = [str(item.get("prompt") or "").strip() for item in items if isinstance(item, dict) and str(item.get("prompt") or "").strip()]
        if not prompts:
            return
        working_messages.append(
            {
                "role": "user",
                "content": "[RUNTIME INSTRUCTION - User steering while the task is running]\n" + "\n\n".join(prompts),
            }
        )
        yield self._emit(
            "status",
            data={"processed": items},
            message="ステアを次の判断に反映しました",
            phase="conversation_steer",
        )

    def _model_turn(
        self,
        prepared: PreparedChatRun,
        messages: list[dict[str, Any]],
        draft: _AssistantDraft | None,
    ) -> Iterator[tuple[dict[str, Any], list[dict[str, Any]]]]:
        seal_policy = self._run_seal_policy(prepared)
        if seal_policy.enabled:
            return (yield from self._model_turn_with_run_seal(prepared, messages, draft, seal_policy))
        if not self._stream_mode:
            return (yield from self._model_turn_via_complete(prepared, messages, draft))
        if prepared.provider_tools and not self._provider_supports_stream_tool_calls(prepared.model):
            return (yield from self._model_turn_via_complete(prepared, messages, draft))

        if not self._gateway.supports_stream(prepared.model):
            return (yield from self._model_turn_via_complete(prepared, messages, draft))

        thought_filter = _InlineThoughtFilter()
        accumulator = ToolCallAccumulator()
        finish_reason = "stop"
        usage = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
        attempts = _ai_retry_attempts(prepared.params)
        for attempt_index in range(attempts):
            try:
                self._current_stream = self._gateway.stream(
                    {
                        "model": prepared.model,
                        "messages": messages,
                        "tools": prepared.provider_tools,
                        "params": prepared.params,
                        "authority_context": prepared.request_context.get("authority", {}),
                    }
                )
                self._record_provider_request_for_trace(
                    messages=messages,
                    tools=prepared.provider_tools,
                    params=prepared.params,
                    transport="stream",
                )
                self._raise_if_cancelled()
                for chunk in self._current_stream:
                    self._raise_if_cancelled()
                    if not isinstance(chunk, dict):
                        continue
                    chunk_type = str(chunk.get("type") or "").strip()
                    if chunk_type == "content_delta":
                        delta = chunk.get("delta", {}) if isinstance(chunk.get("delta"), dict) else {}
                        text = delta.get("text", "")
                        if text:
                            visible_text = thought_filter.push(text)
                            thinking_text = thought_filter.pending_thinking_delta()
                            if thinking_text:
                                self._thinking_transcript_parts.append(str(thinking_text))
                                yield self._emit("thinking_delta", data={"delta": str(thinking_text)}, message="thinking delta")
                            if visible_text:
                                self._text_parts.append(str(visible_text))
                                yield self._emit("content_delta", data={"delta": str(visible_text)}, message="content delta")
                            self._sync_draft(draft, thinking_state="streaming")
                    elif chunk_type in {"thinking_delta", "reasoning_delta"}:
                        delta = chunk.get("delta", {}) if isinstance(chunk.get("delta"), dict) else {}
                        text = delta.get("text") or chunk.get("text") or chunk.get("thinking") or chunk.get("reasoning") or ""
                        if text:
                            self._thinking_transcript_parts.append(str(text))
                            yield self._emit("thinking_delta", data={"delta": str(text)}, message="thinking delta")
                            self._sync_draft(draft, thinking_state="streaming")
                    elif chunk_type in {"tool_call_start", "tool_call_delta", "tool_call_end", "tool_use"}:
                        accumulator.ingest(chunk)
                        call_id = str(chunk.get("id") or chunk.get("tool_call_id") or "").strip()
                        tool_name = str(chunk.get("name") or chunk.get("tool_name") or "").strip()
                        if chunk_type == "tool_call_start" and call_id and call_id not in self._started_tool_call_ids:
                            self._started_tool_call_ids.add(call_id)
                            display_payload = _tool_display_payload(tool_name or "tool", {}, status="running")
                            event = self._emit(
                                "tool_call_started",
                                data={"tool_name": tool_name, "tool_call_id": call_id, **display_payload},
                                message=display_payload["display_text"],
                                phase="tool_call_started",
                                tool_name=tool_name,
                                tool_call_id=call_id,
                            )
                            self._sync_draft(draft, thinking_state="streaming", force=True)
                            yield event
                        if chunk_type == "tool_call_delta":
                            arguments_chunk = str(chunk.get("arguments_chunk") or "")
                            event = self._emit(
                                "tool_call_delta",
                                data={
                                    "tool_name": tool_name,
                                    "tool_call_id": call_id,
                                    "arguments_chunk": arguments_chunk,
                                    "status": "running",
                                    "display_text": "{} の入力を受け取っています".format(tool_name or "tool"),
                                },
                                message="{} の入力を受け取っています".format(tool_name or "tool"),
                                phase="tool_call_delta",
                                tool_name=tool_name,
                                tool_call_id=call_id,
                            )
                            self._sync_draft(draft, thinking_state="streaming", force=True)
                            yield event
                    elif chunk_type == "stream_end":
                        finish_reason = str(chunk.get("finish_reason") or "stop")
                        usage = chunk.get("usage", usage) if isinstance(chunk.get("usage"), dict) else usage
                break
            except AuthorityApprovalRequired:
                raise
            except Exception as exc:
                self._raise_if_cancelled()
                message_text = "AI request failed: " + str(exc)
                can_retry = (
                    not "".join(self._text_parts).strip()
                    and attempt_index < attempts - 1
                    and _is_retryable_ai_error(message_text)
                )
                if can_retry:
                    delay = _ai_retry_delay(prepared.params, attempt_index)
                    yield self._emit(
                        "ai_retry_scheduled",
                        data={
                            "attempt": attempt_index + 1,
                            "max_attempts": attempts,
                            "delay_seconds": delay,
                            "error": message_text,
                        },
                        message="APIエラーのため少し待って再送信します",
                        phase="ai_retry_scheduled",
                    )
                    self._sync_draft(draft, thinking_state="running", force=True)
                    if delay > 0:
                        time.sleep(delay)
                    continue
                if self._tool_logs:
                    response = _ai_error_after_tool_use_response(message_text)
                    response["tool_logs"] = list(self._tool_logs)
                    response["events"] = list(self._activity_events)
                    return response, []
                raise RuntimeError(message_text)
            finally:
                self._current_stream = None

        trailing_text = thought_filter.finish()
        thinking_text = thought_filter.pending_thinking_delta()
        if thinking_text:
            self._thinking_transcript_parts.append(str(thinking_text))
            yield self._emit("thinking_delta", data={"delta": str(thinking_text)}, message="thinking delta")
        if trailing_text:
            self._text_parts.append(str(trailing_text))
            yield self._emit("content_delta", data={"delta": str(trailing_text)}, message="content delta")
        self._sync_draft(draft, thinking_state="streaming")

        tool_uses = accumulator.tool_uses()
        response_text = "".join(self._text_parts)
        if not response_text.strip() and not tool_uses:
            fallback_response = self._fallback_complete_without_thinking(
                prepared,
                messages,
                transcript="".join(self._thinking_transcript_parts),
            )
            fallback_tool_uses = (
                _tool_use_blocks(fallback_response)
                if isinstance(fallback_response, dict)
                else []
            )
            if fallback_tool_uses:
                tool_uses = fallback_tool_uses
            fallback_text = self._text_from_content_blocks(
                fallback_response.get("content") if isinstance(fallback_response, dict) else None
            )
            if fallback_text:
                self._text_parts.append(fallback_text)
                yield self._emit("content_delta", data={"delta": fallback_text}, message="content delta")
                response_text = "".join(self._text_parts)
            response = fallback_response
        else:
            response = None

        if response is None:
            if not response_text.strip() and not tool_uses:
                response_text = _empty_response_message(finish_reason)
            response = {
                "content": [{"type": "text", "text": response_text}],
                "finish_reason": finish_reason,
                "usage": usage,
                "metadata": {},
            }
        if not tool_uses:
            tool_uses = _tool_use_blocks(response)
        return response, tool_uses

    def _model_turn_via_complete(
        self,
        prepared: PreparedChatRun,
        messages: list[dict[str, Any]],
        draft: _AssistantDraft | None,
    ) -> Iterator[tuple[dict[str, Any], list[dict[str, Any]]]]:
        response = self._complete_turn(prepared, messages)
        tool_uses = _tool_use_blocks(response)
        if not tool_uses and self._stream_mode:
            text = self._response_text(response)
            if text:
                self._text_parts.append(text)
                yield self._emit("content_delta", data={"delta": text}, message="content delta")
                self._sync_draft(draft, thinking_state="completed")
        return response, tool_uses

    def _model_turn_with_run_seal(
        self,
        prepared: PreparedChatRun,
        messages: list[dict[str, Any]],
        draft: _AssistantDraft | None,
        seal_policy: RunSealPolicy,
    ) -> Iterator[tuple[dict[str, Any], list[dict[str, Any]]]]:
        del draft
        service = RunSealService.default()
        working_messages = list(messages)
        attempts = 0
        compacted = False
        while True:
            self._raise_if_cancelled()
            sealed = service.prepare_messages(run_id=self._run_id or prepared.request_id, messages=working_messages)
            response = self._complete_turn(prepared, sealed.messages)
            tool_uses = _tool_use_blocks(response)
            if tool_uses:
                return response, tool_uses
            check = service.verify_and_strip(
                text=self._response_text(response),
                seal=sealed.seal,
            )
            if check.ok:
                if check.thinking_transcript and not "".join(self._thinking_transcript_parts).strip():
                    self._thinking_transcript_parts.append(check.thinking_transcript)
                response = self._run_seal_success_response(
                    response,
                    seal=sealed.seal,
                    attempts=attempts + 1,
                    compacted=compacted,
                    visible_text=check.visible_text,
                    had_interior_seal=check.had_interior_seal,
                    thinking_transcript=check.thinking_transcript,
                )
                if self._stream_mode and check.visible_text:
                    self._text_parts.append(check.visible_text)
                    yield self._emit("content_delta", data={"delta": check.visible_text}, message="content delta")
                return response, []
            should_compact = self._should_compact_after_run_seal_failure(
                prepared,
                working_messages,
                finish_reason=str(response.get("finish_reason") or ""),
                attempts=attempts,
            )
            if should_compact and not compacted and seal_policy.compact_on_failure:
                compacted = True
                attempts += 1
                working_messages = self._compact_messages_for_run_seal(prepared, working_messages)
                yield self._emit(
                    "status",
                    data={"attempt": attempts, "reason": check.reason, "finish_reason": response.get("finish_reason")},
                    message="応答検証に失敗したため文脈を圧縮して再実行します",
                    phase="run_seal_compact",
                )
                continue
            if attempts < seal_policy.max_retries:
                attempts += 1
                working_messages = append_run_seal_retry_note(working_messages, sealed.seal)
                yield self._emit(
                    "status",
                    data={"attempt": attempts, "reason": check.reason},
                    message="応答検証に失敗したため再生成します",
                    phase="run_seal_retry",
                )
                continue
            if not compacted and seal_policy.compact_on_failure:
                compacted = True
                attempts += 1
                working_messages = self._compact_messages_for_run_seal(prepared, working_messages)
                yield self._emit(
                    "status",
                    data={"attempt": attempts, "reason": check.reason},
                    message="応答検証に失敗したため文脈を圧縮して再実行します",
                    phase="run_seal_compact",
                )
                continue
            raise RuntimeError("AI response failed internal validation after retry and compact.")

    def _complete_turn(self, prepared: PreparedChatRun, messages: list[dict[str, Any]]) -> dict[str, Any]:
        try:
            if self._use_provider_compiler(prepared):
                response = self._complete_turn_with_compiler(prepared, messages)
            else:
                self._record_provider_request_for_trace(
                    messages=messages,
                    tools=prepared.provider_tools,
                    params=prepared.params,
                    transport="complete",
                )
                response = self._call_ai_complete_with_retry(
                    prepared.model,
                    messages,
                    prepared.provider_tools,
                    prepared.params,
                    prepared.call_handler,
                    allow_retry=True,
                    authority_context=prepared.request_context.get("authority", {}),
                )
        except AuthorityApprovalRequired:
            raise
        except RuntimeError as exc:
            if self._tool_logs:
                response = _ai_error_after_tool_use_response(str(exc))
                response["tool_logs"] = list(self._tool_logs)
                response["events"] = list(self._activity_events)
                return response
            raise
        if not isinstance(response, dict):
            response = _ai_error_response(
                prepared.model,
                "AI provider returned an invalid response",
                prepared.params,
                events=list(self._activity_events),
            )
        if not _tool_use_blocks(response) and not self._response_text(response).strip():
            retry_params = _params_without_thinking(prepared.params)
            if retry_params != prepared.params:
                retry_visible_params = _provider_visible_params(retry_params)
                self._record_provider_request_for_trace(
                    messages=messages,
                    tools=prepared.provider_tools,
                    params=retry_visible_params,
                    transport="complete",
                    reason="empty_response_retry",
                )
                retry_response = self._call_ai_complete_with_retry(
                    prepared.model,
                    messages,
                    prepared.provider_tools,
                    retry_visible_params,
                    prepared.call_handler,
                    allow_retry=False,
                    authority_context=prepared.request_context.get("authority", {}),
                )
                if isinstance(retry_response, dict) and (
                    self._response_text(retry_response).strip() or _tool_use_blocks(retry_response)
                ):
                    metadata = dict(retry_response.get("metadata") or {})
                    metadata["recovered_from_empty_response"] = True
                    retry_response["metadata"] = metadata
                    response = retry_response
        return response

    def _complete_turn_with_compiler(self, prepared: PreparedChatRun, messages: list[dict[str, Any]]) -> dict[str, Any]:
        if prepared.call_handler is not None:
            self._record_provider_request_for_trace(
                messages=messages,
                tools=prepared.provider_tools,
                params=prepared.params,
                transport="complete",
                reason="call_handler",
            )
            return self._call_ai_complete_with_retry(
                prepared.model,
                messages,
                prepared.provider_tools,
                prepared.params,
                prepared.call_handler,
                allow_retry=True,
                authority_context=prepared.request_context.get("authority", {}),
            )
        provider, model_name = self._gateway.resolve_provider(prepared.model)
        caps = dict(prepared.provider_capabilities or {})
        caps.setdefault("provider_id", str(prepared.model).split("/", 1)[0] if "/" in str(prepared.model) else "")
        if provider.__class__.__name__ == "GoogleProvider":
            try:
                if provider._use_native_generative_api(model_name):
                    caps["api_family"] = "google_native"
            except Exception:
                pass
        api_family = str(caps.get("api_family") or "")
        if compiler_for_api_family(api_family) is None or not callable(getattr(provider, "_request_json", None)):
            self._record_provider_request_for_trace(
                messages=messages,
                tools=prepared.provider_tools,
                params=prepared.params,
                transport="complete",
                reason="compiler_unavailable",
            )
            return self._gateway.complete(
                {
                    "model": prepared.model,
                    "messages": messages,
                    "tools": prepared.provider_tools,
                    "params": prepared.params,
                    "authority_context": prepared.request_context.get("authority", {}),
                }
            )
        planned = PlannedProviderRequest(
            ir=legacy_standard_messages_to_ir(messages, prepared.conversation_id),
            model=model_name,
            provider_capabilities=caps,
            provider_tools=prepared.provider_tools,
            params=prepared.params,
            metadata=dict(prepared.provider_planning.get("metadata") or {}),
        )
        compiled = compile_complete(planned)
        self._record_provider_request_for_trace(
            messages=compiled.legacy_messages or messages,
            tools=prepared.provider_tools,
            params=prepared.params,
            transport="complete",
            compiled=compiled,
        )
        self._check_authority_for_compiled_provider(
            prepared,
            provider=provider,
            provider_id=str(caps.get("provider_id") or ""),
            model_name=model_name,
        )
        request_kwargs = _provider_request_timeout_kwargs(prepared.params)
        try:
            raw = provider._request_json(compiled.path, compiled.body, **request_kwargs)
        except TypeError:
            raw = provider._request_json(compiled.path, compiled.body)
        parser = compiler_for_api_family(compiled.api_family)
        response_ir = parser.parse_response(raw, compiled)
        response = response_ir.to_standard_response()
        metadata = dict(response.get("metadata") or {})
        metadata["provider_compiler"] = {
            "api_family": compiled.api_family,
            "path": compiled.path,
            "enabled": True,
        }
        response["metadata"] = metadata
        return response

    def _record_provider_request_for_trace(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None,
        params: dict[str, Any] | None,
        transport: str,
        reason: str | None = None,
        compiled: Any | None = None,
    ) -> None:
        payload: dict[str, Any] = {
            "transport": str(transport or "complete"),
            "legacy_messages": list(messages or []),
            "tools": list(tools or []),
            "params": dict(params or {}),
        }
        if reason:
            payload["reason"] = str(reason)
        if compiled is not None:
            payload["compiled"] = {
                "api_family": getattr(compiled, "api_family", ""),
                "provider_id": getattr(compiled, "provider_id", ""),
                "model": getattr(compiled, "model", ""),
                "path": getattr(compiled, "path", ""),
                "method": getattr(compiled, "method", ""),
                "body": dict(getattr(compiled, "body", {}) or {}),
                "warnings": list(getattr(compiled, "warnings", []) or []),
                "dropped_features": list(getattr(compiled, "dropped_features", []) or []),
                "metadata": dict(getattr(compiled, "metadata", {}) or {}),
            }
        self._provider_trace_requests.append(payload)
        if len(self._provider_trace_requests) > 16:
            self._provider_trace_requests = self._provider_trace_requests[-16:]

    @staticmethod
    def _check_authority_for_compiled_provider(
        prepared: PreparedChatRun,
        *,
        provider: Any,
        provider_id: str,
        model_name: str,
        consume_one_shots: bool = True,
    ) -> None:
        provider_id = str(provider_id or "").strip()
        if provider_id in {"", "stub", "rumi"}:
            return
        from domain.ai_client.authority_gate import provider_requires_authority

        if not provider_requires_authority(provider_id, provider=provider, api_id="legacy"):
            return
        from core_runtime.authority import get_authority_service

        authority_context = (
            prepared.request_context.get("authority") if isinstance(prepared.request_context, dict) else {}
        )
        context = dict(authority_context) if isinstance(authority_context, dict) else {}
        provider_call_key = f"{provider_id}:{model_name}"
        verified_provider_calls = context.get("_provider_one_shot_verified_for_run")
        if isinstance(verified_provider_calls, list) and provider_call_key in verified_provider_calls:
            return
        allow_consumed_one_shot_tokens_for_run = bool(
            context.get("allow_consumed_one_shot_tokens_for_run")
        )
        service = get_authority_service()

        def mark_provider_call_verified() -> None:
            if not isinstance(authority_context, dict):
                return
            current = authority_context.get("_provider_one_shot_verified_for_run")
            verified = list(current) if isinstance(current, list) else []
            if provider_call_key not in verified:
                verified.append(provider_call_key)
            authority_context["_provider_one_shot_verified_for_run"] = verified

        def one_shot_issued_for_resource(
            *,
            permission_id: str,
            request_id: str,
            approval_token: str,
            resource: dict[str, Any],
            include_consumed: bool = False,
        ) -> bool:
            issued = getattr(service, "one_shot_approval_issued", None)
            if not callable(issued):
                return False
            try:
                return bool(
                    issued(
                        request_id=request_id,
                        permission_id=permission_id,
                        token=approval_token,
                        conversation_id=context.get("conversation_id"),
                        principal_id=principal_id,
                        resource=resource,
                        include_consumed=include_consumed,
                    )
                )
            except TypeError:
                if include_consumed:
                    return False
                try:
                    return bool(
                        issued(
                            request_id=request_id,
                            permission_id=permission_id,
                            token=approval_token,
                            conversation_id=context.get("conversation_id"),
                            principal_id=principal_id,
                        )
                    )
                except Exception:
                    return False
            except Exception:
                return False

        checks = [
            ("model.invoke", "model"),
            ("api_key.use", "api_key"),
            ("network.egress", "network"),
        ]
        if _authority_context_token_for_permission(context, "model.invoke")[1]:
            missing_related = [
                item
                for item in checks
                if item[0] != "model.invoke" and not _authority_context_token_for_permission(context, item[0])[1]
            ]
            if missing_related:
                checks = missing_related + [item for item in checks if item not in missing_related]
        principal_id = str(context.get("principal_id") or "defaultspack")
        decisions: list[tuple[str, dict[str, Any], str, str, Any]] = []
        for permission_id, resource_kind in checks:
            request_id, approval_token = _authority_context_token_for_permission(context, permission_id)
            resource = build_provider_authority_resource(
                permission_id=permission_id,
                resource_kind=resource_kind,
                provider_id=provider_id,
                api_id="legacy",
                model_id=model_name,
                model_ref=prepared.model,
                provider=provider,
                stream=False,
            )
            effective_request_id = request_id or str(context.get("request_id") or "").strip()
            trusted_consumed_token = False
            if (
                allow_consumed_one_shot_tokens_for_run
                and effective_request_id
                and approval_token
            ):
                if not one_shot_issued_for_resource(
                    permission_id=permission_id,
                    request_id=effective_request_id,
                    approval_token=approval_token,
                    resource=resource,
                ) and one_shot_issued_for_resource(
                    permission_id=permission_id,
                    request_id=effective_request_id,
                    approval_token=approval_token,
                    resource=resource,
                    include_consumed=True,
                ):
                    trusted_consumed_token = True
            if trusted_consumed_token:
                decisions.append((permission_id, resource, request_id, approval_token, None))
                continue
            decision = service.check(
                principal_id=principal_id,
                permission_id=permission_id,
                resource=resource,
                reason=provider_authority_reason(permission_id, resource),
                conversation_id=context.get("conversation_id"),
                profile_id=context.get("profile_id"),
                node_id=context.get("node_id"),
                graph_id=context.get("graph_id"),
                request_id=request_id or context.get("request_id"),
                approval_token=approval_token,
                consume_approval_token=False,
            )
            if not decision.allowed:
                raise AuthorityApprovalRequired(decision)
            decisions.append((permission_id, resource, request_id, approval_token, decision))

        token_consumes = []
        rechecks: list[tuple[str, dict[str, Any], str, str]] = []
        trusted_consumed_provider_call = False
        for permission_id, resource, request_id, approval_token, decision in decisions:
            if decision is None:
                trusted_consumed_provider_call = True
                continue
            effective_request_id = request_id or str(context.get("request_id") or "").strip()
            if (
                decision.reason == "One-shot approval verified"
                and effective_request_id
                and approval_token
            ):
                token_consumes.append(
                    {
                        "request_id": effective_request_id,
                        "principal_id": principal_id,
                        "permission_id": permission_id,
                        "resource": resource,
                        "approval_token": approval_token,
                    }
                )
            else:
                rechecks.append((permission_id, resource, request_id, approval_token))

        for permission_id, resource, request_id, approval_token in rechecks:
            decision = service.check(
                principal_id=principal_id,
                permission_id=permission_id,
                resource=resource,
                reason=provider_authority_reason(permission_id, resource),
                conversation_id=context.get("conversation_id"),
                profile_id=context.get("profile_id"),
                node_id=context.get("node_id"),
                graph_id=context.get("graph_id"),
                request_id=request_id or context.get("request_id"),
                approval_token=approval_token,
                consume_approval_token=False,
            )
            if not decision.allowed:
                raise AuthorityApprovalRequired(decision)
        can_consume_one_shots = callable(getattr(service, "consume_one_shot_approvals_atomically", None))
        if token_consumes and consume_one_shots and can_consume_one_shots:
            decision = service.consume_one_shot_approvals_atomically(token_consumes)
            if not decision.allowed:
                raise AuthorityApprovalRequired(decision)
            mark_provider_call_verified()
        elif trusted_consumed_provider_call and consume_one_shots:
            mark_provider_call_verified()

    def _replay_approval_followup_if_present(
        self,
        prepared: PreparedChatRun,
        working_messages: list[dict[str, Any]],
        working_ir: Any,
        draft: _AssistantDraft | None,
    ) -> Iterator[dict[str, Any]]:
        """Deterministically replay an approved coding tool when the user-side
        approval-followup metadata resolves to an approved pending tool.

        Uses ``approval_token`` + ``tool_name`` + ``request_id`` from the
        ``approval_followup`` metadata block to look up the stored approved
        arguments, executes the pending tool once with those arguments and the
        token, appends the synthetic assistant tool_use + tool_result pair to
        the working chain, and clears ``provider_tools`` so the model can only
        summarize the result.

        Falls through (no-op) for non-coding flows, missing tokens,
        mismatched args_hash, tool_name mismatch, or any internal error. A
        consumed or invalid approval token returns a terminal followup response
        instead of entering another model turn, preventing stale hidden
        followups from rediscovering and re-requesting the same tool.

        When the replayed tool result itself reports ``approval_required`` or
        a ``tool_blocked`` recovery kind, this generator emits the same
        ``approval_requested`` / ``tool_blocked`` events the model-driven
        path would emit and *returns* a fully formed blocked response so the
        caller can short-circuit the model loop and surface the
        approval/blocking path directly. In all other cases the generator
        returns ``None`` and the caller continues into the summary turn.
        """
        metadata = prepared.metadata if isinstance(prepared.metadata, dict) else {}
        followup = metadata.get("approval_followup") if isinstance(metadata.get("approval_followup"), dict) else None
        if not followup:
            return None
        token = str(followup.get("approval_token") or followup.get("token") or "").strip()
        tool_name = str(followup.get("tool_name") or "").strip()
        request_id = str(followup.get("request_id") or followup.get("approval_request_id") or "").strip()
        if not (token and tool_name and request_id):
            return None

        try:
            from domain.safety import approval as _approval_mod
        except Exception:
            return None

        try:
            request = _approval_mod.get_approval_request(request_id)
        except Exception:
            request = None
        if not isinstance(request, dict):
            return None
        # Replay only when the request was approved by the user. ``consumed``
        # is excluded because the one-shot token has already burnt and would
        # not pass verify_execution_token below.
        request_status = str(request.get("status") or "").strip()
        if request_status != "approved":
            if request_status == "consumed":
                if isinstance(prepared.tool_context, dict):
                    prepared.tool_context["_approval_followup_block_legacy"] = True
                event = self._emit(
                    "status",
                    data={
                        "request_id": request_id,
                        "tool_name": tool_name,
                        "operation": str(request.get("operation") or "").strip(),
                        "status": "consumed",
                    },
                    message=_APPROVAL_FOLLOWUP_ALREADY_HANDLED_TEXT,
                    phase="approval_followup_consumed",
                    tool_name=tool_name,
                )
                self._sync_draft(draft, force=True)
                yield event
                return _approval_followup_terminal_response(
                    prepared.model,
                    prepared.params,
                    events=list(self._activity_events),
                    message=_APPROVAL_FOLLOWUP_ALREADY_HANDLED_TEXT,
                    request_id=request_id,
                    tool_name=tool_name,
                    operation=str(request.get("operation") or "").strip(),
                    status="consumed",
                    code="APPROVAL_TOKEN_USED",
                )
            return None

        details = request.get("details") if isinstance(request.get("details"), dict) else {}
        operation = str(request.get("operation") or "").strip()
        # Safety guard: if the original approval request stored the requesting
        # tool_name, the followup must target the same canonical tool identity.
        # Some first-party tool manifests store display names (for example
        # ``Job Resume``) in the approval details while the followup carries the
        # executable tool id (``job_resume``). Resolve both through the manifest
        # registry when exact string equality is not available, and treat
        # ambiguous or unknown aliases as a mismatch.
        request_tool_name = str(details.get("tool_name") or "").strip()
        if request_tool_name and not _approval_followup_tool_identity_matches(
            request_tool_name,
            tool_name,
            details=details,
            operation=operation,
        ):
            return None

        stored_args = details.get("arguments") if isinstance(details.get("arguments"), dict) else None
        if stored_args is None:
            return None
        if not operation:
            return None
        if not operation.startswith("tool."):
            if not (
                operation.startswith(("browser.", "computer."))
                and tool_name in {"browser_computer", "browser_use", "computer_use"}
            ):
                return None
        if isinstance(prepared.tool_context, dict):
            prepared.tool_context["_approval_followup_block_legacy"] = True

        try:
            args_hash = str(request.get("args_hash") or "").strip() or _approval_mod.hash_arguments(stored_args)
            verification = _approval_mod.verify_execution_token(
                token, operation, args_hash, consume=False,
            )
        except Exception:
            return None
        if not getattr(verification, "valid", False):
            code = str(getattr(verification, "code", "") or "").strip()
            message = (
                _APPROVAL_FOLLOWUP_ALREADY_HANDLED_TEXT
                if code == "APPROVAL_TOKEN_USED"
                else _APPROVAL_FOLLOWUP_INVALID_TEXT
            )
            event = self._emit(
                "status",
                data={
                    "request_id": request_id,
                    "tool_name": tool_name,
                    "operation": operation,
                    "status": "invalid_token",
                    "code": code,
                },
                message=message,
                phase="approval_followup_invalid",
                tool_name=tool_name,
            )
            self._sync_draft(draft, force=True)
            yield event
            return _approval_followup_terminal_response(
                prepared.model,
                prepared.params,
                events=list(self._activity_events),
                message=message,
                request_id=request_id,
                tool_name=tool_name,
                operation=operation,
                status="invalid_token",
                code=code,
            )

        tool_name, display_args = _approval_replay_executable_arguments(
            tool_name,
            stored_args,
            action=str(followup.get("action") or details.get("action") or "").strip(),
            operation=operation,
        )
        invoke_args = dict(display_args)
        invoke_args["approval_token"] = token
        if (
            tool_name in {"browser_computer", "browser_use", "computer_use"}
            and isinstance(invoke_args.get("payload"), dict)
        ):
            nested_payload = dict(invoke_args["payload"])
            nested_payload.setdefault("approval_token", token)
            invoke_args["payload"] = nested_payload
        # ``display_args`` is the version we expose to the model context
        # (synthetic tool_use message + IR), the SSE event stream, and any
        # nested-approval payload that surfaces from the replayed tool result.
        # Stripping ``approval_token`` here prevents the one-shot signed token
        # from leaking into a subsequent model prompt or a UI-visible
        # approval-required payload where a malicious component could attempt
        # to replay it. ``invoke_args`` (with token) is only handed to the
        # actual tool executor below.
        display_args = _strip_approval_tokens(invoke_args)
        tool_call_id = str(
            followup.get("tool_call_id")
            or details.get("tool_call_id")
            or request_id
            or gen_id()
        ).strip()

        # Mark we have started this synthetic tool call before emitting any event
        # so subsequent hooks treat it as a single deterministic execution.
        self._started_tool_call_ids.add(tool_call_id)

        display_started = _tool_display_payload(tool_name, display_args, status="running")
        yield self._emit(
            "tool_call_started",
            data={
                "tool_name": tool_name,
                "tool_call_id": tool_call_id,
                "arguments": display_args,
                "approval_replay": True,
                **display_started,
            },
            message=display_started["display_text"],
            phase="tool_call_started",
            tool_name=tool_name,
            tool_call_id=tool_call_id,
            arguments=display_args,
            approval_replay=True,
        )
        self._sync_draft(draft, force=True)

        try:
            result = self._execute_tool(prepared, tool_name, tool_call_id, invoke_args)
        except Exception as exc:  # pragma: no cover - defensive
            result = {
                "result": "approval-followup replay failed: {}".format(exc),
                "is_error": True,
                "widget": None,
            }

        summary = _tool_result_summary(tool_name, result)
        artifacts = _tool_result_artifacts(result)
        status = "failed" if _tool_result_is_error(result) else "completed"
        display_completed = _tool_display_payload(tool_name, display_args, status=status, summary=summary)
        yield self._emit(
            "tool_call_completed",
            data={
                "tool_name": tool_name,
                "tool_call_id": tool_call_id,
                "is_error": _tool_result_is_error(result),
                "recovery_kind": _tool_result_recovery_kind(result),
                "result_summary": summary,
                "summary": summary,
                "approval_replay": True,
                **display_completed,
                "result": _bounded_compact_tool_result(result, summary, artifacts),
                "artifacts": artifacts,
                "artifact_paths": [artifact.get("path") for artifact in artifacts if artifact.get("path")],
            },
            message=display_completed["display_text"],
            phase="tool_call_completed",
            tool_name=tool_name,
            tool_call_id=tool_call_id,
            is_error=_tool_result_is_error(result),
            approval_replay=True,
        )
        self._sync_draft(draft, force=True)

        # Safety guard: if the replayed tool itself still reports an approval
        # is required (e.g. a nested / chained approval flow) we must NOT
        # advance to the natural-language summary turn, otherwise the model
        # would speak as if the operation succeeded while the underlying tool
        # is actually still pending. Surface the approval path directly using
        # the same helpers as the model-driven branch in ``_execute``.
        # ``display_args`` is intentionally passed here instead of
        # ``invoke_args`` so the nested approval payload that bubbles up to
        # the UI never carries the one-shot signed token of the *outer*
        # approval - a leaked token there could be replayed by a downstream
        # component to invoke another tool.
        approval_request = _approval_request_from_tool_result(tool_name, tool_call_id, display_args, result)
        if approval_request is not None:
            # Defensive scrub: even when the engine passes ``display_args``
            # to ``_approval_request_from_tool_result`` (so the *fallback*
            # arguments are token-free), the function still prefers
            # ``result["payload"]`` when the tool result provides one. A
            # tool that builds its payload via ``payload=dict(arguments)``
            # would therefore echo the outer (spent) one-shot token back
            # into the nested approval payload that bubbles up to the UI
            # and is recorded into the assistant-side activity log. The
            # outer ``approval_token`` field is also forced to ``None`` if
            # the tool somehow surfaced it - a chained approval must mint
            # its own fresh token, never recycle ours.
            nested_payload = approval_request.get("payload")
            if isinstance(nested_payload, dict):
                approval_request["payload"] = _strip_approval_tokens(nested_payload)
            if approval_request.get("approval_token") == token:
                approval_request["approval_token"] = None
            approval_event = self._emit(
                "approval_requested",
                data=approval_request,
                message=_APPROVAL_WAITING_TEXT,
                phase="approval_requested",
                tool_name=tool_name,
                tool_call_id=tool_call_id,
                requires_approval=True,
            )
            self._sync_draft(draft, force=True)
            yield approval_event
            return _approval_waiting_response(
                prepared.model,
                approval_request,
                prepared.params,
                events=list(self._activity_events),
            )

        # ``display_args`` is also used for the synthetic assistant
        # ``tool_use`` block so the one-shot approval token never appears in
        # the model context (working_messages + IR) of any subsequent model
        # turn. The actual tool execution above already received the token.
        synth_tool_uses = [{"id": tool_call_id, "name": tool_name, "input": display_args}]
        _append_assistant_tool_use_message(working_messages, synth_tool_uses)
        try:
            append_assistant_tool_use_to_ir(working_ir, synth_tool_uses)
        except Exception:
            pass
        _append_tool_result_message(working_messages, tool_name, result, tool_call_id, model=prepared.model)
        try:
            append_tool_result_to_ir(working_ir, tool_name, result, tool_call_id, model=prepared.model)
        except Exception:
            pass

        # Safety guard: when the replayed tool reports a recovery kind that
        # blocks further automation (e.g. visible window required, focus
        # required) the model summary turn must not run, otherwise the user
        # would see a confident summary for an operation that never reached
        # the host. Surface the same ``tool_blocked`` status the model-driven
        # branch in ``_execute`` emits and short-circuit with the existing
        # ``_tool_blocked_response`` helper.
        recovery_kind = _tool_result_recovery_kind(result)
        if recovery_kind in {"visible_window_required", "focus_required"}:
            yield self._emit(
                "status",
                data={"tool_name": tool_name, "tool_call_id": tool_call_id, "recovery_kind": recovery_kind},
                message="可視画面外の tool 実行要求のため停止しました",
                phase="tool_blocked",
                tool_name=tool_name,
                tool_call_id=tool_call_id,
            )
            self._sync_draft(draft, force=True)
            return _tool_blocked_response(tool_name, result)

        # Strip provider tools so the upcoming model turn produces only a
        # natural-language summary; we have already replayed the pending tool
        # exactly once, and any further provider tool call from the same
        # followup turn would be a regression of the deterministic contract.
        #
        # Browser/computer control is the one exception: user-requested
        # computer-use tasks are naturally multi-step (open URL, then key/click
        # etc.). Keep the tool surface there so the model can continue with the
        # next approved action instead of emitting a plain-text ``call:...``.
        keep_provider_tools = (
            tool_name in {"browser_computer", "browser_use", "computer_use"}
            and isinstance(prepared.request_context, dict)
            and bool(prepared.request_context.get("user_requested_computer_use"))
        )
        if not keep_provider_tools:
            # The original list is snapshotted on ``tool_context`` so
            # ``_final_response`` can still surface the truthful set of
            # attached tools on the finalised assistant metadata (the
            # suppression here is scoped to the model summary turn only).
            if isinstance(prepared.tool_context, dict):
                prepared.tool_context.setdefault(
                    "_attached_provider_tools_snapshot",
                    list(prepared.provider_tools or []),
                )
            prepared.provider_tools = []
        if isinstance(prepared.tool_context, dict):
            prepared.tool_context["approval_replayed"] = {
                "tool_name": tool_name,
                "tool_call_id": tool_call_id,
                "request_id": request_id,
                "arguments": dict(display_args),
            }
        return None
    def _execute_tool(
        self,
        prepared: PreparedChatRun,
        tool_name: str,
        tool_call_id: str,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        invoke_context = build_tool_execution_context(prepared.tool_context or {}, tool_name, prepared.connected_tool_names)
        invoke_context = dict(invoke_context or {})
        invoke_context["run_event_sink"] = self._legacy_tool_event_sink
        invoke_context["run_id"] = self._run_id
        invoke_context["tool_call_id"] = tool_call_id
        invoke_context["is_cancelled"] = self._is_cancelled
        invoke_context["stream_event_callback"] = self._legacy_stream_event_callback
        if prepared.call_handler is not None:
            result = prepared.call_handler(
                "defaults.tool.invoke",
                {
                    "tool_name": tool_name,
                    "arguments": arguments,
                    "context": invoke_context,
                },
            )
        else:
            executed = ToolExecutor().execute(tool_name, arguments, invoke_context)
            result = {"status": "ok", "data": executed}

        log = {
            "tool_name": tool_name,
            "tool_call_id": tool_call_id,
            "arguments": _redact_sensitive_value(arguments),
            "result": _compact_tool_log_value(result),
            "timestamp": timestamp(),
        }
        self._tool_logs.append(log)
        return result

    def _final_response(self, prepared: PreparedChatRun, response: dict[str, Any]) -> dict[str, Any]:
        finalized = dict(response or _ai_error_response(
            prepared.model,
            "AI provider did not return a final response",
            prepared.params,
            events=list(self._activity_events),
        ))
        if not _tool_use_blocks(finalized) and not self._response_text(finalized).strip():
            finalized["content"] = [{"type": "text", "text": _empty_response_message(finalized.get("finish_reason"))}]
            metadata = dict(finalized.get("metadata") or {})
            metadata["empty_ai_response"] = True
            finalized["metadata"] = metadata
        metadata = dict(finalized.get("metadata") or {})
        requested_tools = list(prepared.tools_called or [])
        requested_tool_ids: list[str] = []
        unselected_requested_tools: list[dict[str, Any]] = []
        unknown_selected_tools: list[str] = []
        if isinstance(prepared.tool_context, dict):
            raw_requested_tool_ids = prepared.tool_context.get("requested_tool_ids")
            if isinstance(raw_requested_tool_ids, list):
                requested_tool_ids = [
                    str(item).strip()
                    for item in raw_requested_tool_ids
                    if str(item or "").strip()
                ]
            raw_unselected = prepared.tool_context.get("unselected_requested_tools")
            if isinstance(raw_unselected, list):
                unselected_requested_tools = [
                    dict(item)
                    for item in raw_unselected
                    if isinstance(item, dict)
                ]
            raw_unknown = prepared.tool_context.get("unknown_selected_tools")
            if isinstance(raw_unknown, list):
                unknown_selected_tools = [
                    str(item).strip()
                    for item in raw_unknown
                    if str(item or "").strip()
                ]
        if requested_tool_ids:
            requested_tools = list(dict.fromkeys([*requested_tool_ids, *requested_tools]))
        # When the approval-followup replay path transiently suppresses
        # ``provider_tools`` for the summary turn, ``tool_context`` holds a
        # snapshot of the originally attached tools so the finalised
        # assistant ``metadata`` can still report the truthful attached-tool
        # set. Falls back to the live ``provider_tools`` for non-replay
        # turns where no snapshot was taken.
        attached_provider_tools_source = prepared.provider_tools
        if isinstance(prepared.tool_context, dict):
            snapshot = prepared.tool_context.get("_attached_provider_tools_snapshot")
            if isinstance(snapshot, list):
                attached_provider_tools_source = snapshot
        attached_provider_tools = [
            name
            for name in (tool_name_from_definition(tool) for tool in attached_provider_tools_source)
            if name and not is_assistant_progress_tool_name(name)
        ]
        unattached_requested_tools = [
            name for name in requested_tools if name not in set(attached_provider_tools)
        ]
        attached_tool_count = len(attached_provider_tools)
        executed_tools: list[str] = []
        for log in self._tool_logs:
            tool_name = str(log.get("tool_name") or "").strip()
            if tool_name and tool_name not in executed_tools:
                executed_tools.append(tool_name)
        model_warnings: list[str] = []
        if isinstance(prepared.model_routing, dict) and isinstance(prepared.model_routing.get("warnings"), list):
            model_warnings = [str(item) for item in prepared.model_routing.get("warnings", [])]
        metadata.update(
            {
                "model": prepared.model,
                "attached_tool_count": attached_tool_count,
                "requested_tools": requested_tools,
                "attached_tools": attached_provider_tools,
                "attached_provider_tools": attached_provider_tools,
                "executed_tools": executed_tools,
                "unattached_requested_tools": unattached_requested_tools,
                "unknown_selected_tools": unknown_selected_tools,
                "thinking": {
                    "state": "completed" if finalized.get("finish_reason") != "error" else "failed",
                    **({"transcript": "".join(self._thinking_transcript_parts)} if self._thinking_transcript_parts else {}),
                },
                "thinking_level": prepared.params.get("thinking_level"),
                "deepthink_enabled": bool(prepared.params.get("deepthink_enabled")),
                "model_routing": dict(prepared.model_routing or {}),
                "chat_references": dict(prepared.chat_references or {}),
                "ir": {"schema_version": prepared.ir_schema_version},
                "provider_planning": compact_provider_planning(redact_sensitive_value(dict(prepared.provider_planning or {}))),
                "provider_capabilities": redact_sensitive_value(dict(prepared.provider_capabilities or {})),
            }
        )
        if self._progress_state:
            metadata["progress_state"] = dict(self._progress_state)
        if unattached_requested_tools or unselected_requested_tools or unknown_selected_tools:
            metadata["tool_attachment_diagnostics"] = {
                "requested_tools": requested_tools,
                "attached_tools": attached_provider_tools,
                "connected_tools": sorted(str(name) for name in prepared.connected_tool_names if name),
                "unattached_requested_tools": unattached_requested_tools,
                "unselected_requested_tools": unselected_requested_tools,
                "unknown_selected_tools": unknown_selected_tools,
            }
        if isinstance(prepared.request_context, dict) and isinstance(prepared.request_context.get("tool_selection"), dict):
            metadata["tool_selection"] = dict(prepared.request_context["tool_selection"])
        trace_metadata = self._write_provider_trace(prepared, finalized)
        if trace_metadata:
            metadata["provider_trace"] = trace_metadata
        if "selected_model_does_not_support_tool_calling" in model_warnings:
            metadata["tool_calling_unverified"] = True
            metadata["tool_calling_unavailable_reason"] = "selected_model_does_not_support_tool_calling"
        if prepared.matched_skills:
            metadata["matched_skill_instructions"] = list(prepared.matched_skills)
        prompt_usage = prepared.request_context.get("prompt_usage") if isinstance(prepared.request_context, dict) else None
        if isinstance(prompt_usage, dict):
            metadata["prompt_usage"] = prompt_usage
        finalized["metadata"] = metadata
        finalized["events"] = list(self._activity_events)
        finalized["tool_logs"] = list(self._tool_logs)
        return finalized

    @staticmethod
    def _use_provider_compiler(prepared: PreparedChatRun) -> bool:
        if str(os.environ.get("RUMI_DEFAULTSPACK_PROVIDER_LEGACY_MESSAGES", "") or "").strip().lower() in {"1", "true", "yes", "on"}:
            return False
        if str(os.environ.get("RUMI_DEFAULTSPACK_PROVIDER_COMPILER_V2", "") or "").strip().lower() in {"1", "true", "yes", "on"}:
            return True
        return False

    def _write_provider_trace(self, prepared: PreparedChatRun, response: dict[str, Any]) -> dict[str, Any] | None:
        try:
            capabilities = dict(prepared.provider_capabilities or {})
            provider_id = str(capabilities.get("provider_id") or (prepared.model.split("/", 1)[0] if "/" in prepared.model else "unknown"))
            planning = dict(prepared.provider_planning or {})
            if self._provider_trace_requests:
                compiled_payload = dict(self._provider_trace_requests[-1])
                compiled_payload["provider_request_count"] = len(self._provider_trace_requests)
                compiled_payload["provider_requests"] = list(self._provider_trace_requests)
            else:
                compiled_payload = {
                    "legacy_messages": list(prepared.standard_messages or []),
                    "tools": list(prepared.provider_tools or []),
                    "params": dict(prepared.params or {}),
                }
            return write_provider_trace(
                conversation_id=prepared.conversation_id,
                request_id=prepared.request_id,
                provider=provider_id,
                model=prepared.model,
                api_family=str(capabilities.get("api_family") or "legacy"),
                ir_schema_version=prepared.ir_schema_version,
                capability_summary=capabilities,
                planning_metadata=planning,
                dropped_features=list(planning.get("dropped_features") or []),
                bridge_actions=list(planning.get("bridge_actions") or []),
                warnings=list(planning.get("warnings") or []),
                compiled_payload=compiled_payload,
                response_summary={
                    "finish_reason": response.get("finish_reason"),
                    "usage": response.get("usage") if isinstance(response.get("usage"), dict) else {},
                    "content_blocks": len(response.get("content", [])) if isinstance(response.get("content"), list) else 0,
                },
                store=self._store,
            )
        except Exception:
            return None

    def _sync_draft(self, draft: _AssistantDraft | None, *, thinking_state: str = "running", force: bool = False) -> None:
        if draft is None:
            return
        draft.update(
            content_text="".join(self._text_parts),
            thinking_transcript="".join(self._thinking_transcript_parts),
            events=self._activity_events,
            tool_logs=self._tool_logs,
            finish_reason="streaming",
            thinking_state=thinking_state,
            force=force,
        )

    def _emit(
        self,
        event_type: str,
        *,
        data: dict[str, Any] | None = None,
        message: str = "",
        **extra: Any,
    ) -> dict[str, Any]:
        self._event_seq += 1
        event = run_event(
            event_type,
            run_id=self._run_id,
            conversation_id=self._conversation_id,
            seq=self._event_seq,
            data=data,
            timestamp=timestamp(),
            message=message,
            **extra,
        )
        legacy = to_legacy_chat_stream_event(event)
        if legacy is not None and self._is_activity_event(legacy):
            self._activity_events.append(legacy)
        return event

    @staticmethod
    def _is_activity_event(event: dict[str, Any]) -> bool:
        event_type = str(event.get("type") or "").strip()
        return event_type in {
            "status",
            "assistant_progress",
            "tool_call_started",
            "tool_call_delta",
            "tool_call_completed",
            "browser_state_invalidated",
            "browser_state_snapshot",
            "browser_dom_snapshot",
            "browser_screenshot",
            "approval_requested",
            "ai_retry_scheduled",
            "task_failed",
            "cancelled",
            "tool_selection_started",
            "tool_selection_completed",
            "tool_selection_fallback",
            "tool_selection_reviewed",
        }

    def _provider_supports_stream_tool_calls(self, model: str) -> bool:
        try:
            provider, _ = self._gateway.resolve_provider(model)
        except Exception:
            return False
        name = provider.__class__.__name__.lower()
        return name in {"openaiprovider", "googleprovider"}

    def _log_inspector(self, prepared: PreparedChatRun, response: dict[str, Any]) -> None:
        try:
            source = "domain.chat.stream_engine"
            if isinstance(prepared.request_context, dict):
                source = str(
                    prepared.request_context.get("run_source")
                    or prepared.request_context.get("source")
                    or source
                )
            enrich_info = prepared.enrich_info if isinstance(prepared.enrich_info, dict) else {}
            executed_tool_names = [
                str(log.get("tool_name") or "").strip()
                for log in self._tool_logs
                if isinstance(log, dict) and str(log.get("tool_name") or "").strip()
            ]
            unknown_selected_tools = []
            if isinstance(prepared.tool_context, dict):
                raw_unknown = prepared.tool_context.get("unknown_selected_tools")
                if isinstance(raw_unknown, list):
                    unknown_selected_tools = [str(item) for item in raw_unknown if str(item or "").strip()]
            metadata = response.get("metadata") if isinstance(response.get("metadata"), dict) else {}
            usage = response.get("usage") if isinstance(response.get("usage"), dict) else {}
            Inspector().log_request(
                request_id=prepared.request_id,
                conversation_id=prepared.conversation_id,
                model=prepared.model,
                prompt_used=str(enrich_info.get("enriched_prompt") or prepared.system_prompt or ""),
                tools_called=executed_tool_names or list(prepared.tools_called),
                context_info={
                    "source": source,
                    "run_id": self._run_id,
                    "stream_mode": self._stream_mode,
                    "message_count": len(prepared.standard_messages),
                    "params": dict(prepared.params or {}),
                    "attached_tools": list(prepared.tools_called),
                    "executed_tools": executed_tool_names,
                    "unknown_selected_tools": unknown_selected_tools,
                    "knowledge_results": enrich_info.get("knowledge_results", []),
                    "memory_results": enrich_info.get("memory_results", []),
                    "chat_references": dict(prepared.chat_references or {}),
                    "matched_skill_instructions": list(prepared.matched_skills or []),
                    "finish_reason": response.get("finish_reason"),
                    "usage": usage,
                    "metadata": metadata,
                },
            )
        except Exception:
            pass

    def _call_ai_complete_with_retry(
        self,
        model: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        params: dict[str, Any],
        call_handler: Any,
        *,
        allow_retry: bool,
        authority_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        attempts = _ai_retry_attempts(params) if allow_retry else 1
        last_error = "AI request failed"
        for attempt_index in range(attempts):
            try:
                if call_handler is not None:
                    response = call_handler(
                        "defaults.ai.complete",
                        {
                            "model": model,
                            "messages": messages,
                            "tools": tools,
                            "params": params,
                        },
                    )
                    if isinstance(response, dict) and response.get("status") == "error":
                        err = response.get("error", {})
                        raise RuntimeError(str(err.get("message") or "AI request failed"))
                    if isinstance(response, dict) and response.get("status") == "ok":
                        return response.get("data", {})
                    return response
                return self._gateway.complete(
                    {
                        "model": model,
                        "messages": messages,
                        "tools": tools or [],
                        "params": params or {},
                        "authority_context": authority_context or {},
                    }
                )
            except AuthorityApprovalRequired:
                raise
            except Exception as exc:
                last_error = str(exc)
                if attempt_index >= attempts - 1 or not _is_retryable_ai_error(last_error):
                    break
                delay = _ai_retry_delay(params, attempt_index)
                self._activity_events.append(
                    {
                        "type": "ai_retry_scheduled",
                        "message": "APIエラーのため少し待って再送信します",
                        "phase": "ai_retry_scheduled",
                        "attempt": attempt_index + 1,
                        "max_attempts": attempts,
                        "delay_seconds": delay,
                        "error": last_error,
                        "timestamp": timestamp(),
                    }
                )
                if delay > 0:
                    time.sleep(delay)
        raise RuntimeError(last_error)

    def _before_tool_call(
        self,
        prepared: PreparedChatRun,
        tool_name: str,
        tool_call_id: str,
        arguments: dict[str, Any],
    ) -> list[dict[str, Any]]:
        return []

    def _after_tool_call(
        self,
        prepared: PreparedChatRun,
        tool_name: str,
        tool_call_id: str,
        arguments: dict[str, Any],
        result: dict[str, Any],
    ) -> list[dict[str, Any]]:
        try:
            from domain.chat.browser_state import emit_browser_state_events
        except Exception:
            return []
        action = ""
        if isinstance(arguments, dict):
            action = str(arguments.get("action") or "").strip()
        emission = emit_browser_state_events(
            tool_name,
            result,
            tool_call_id=tool_call_id,
            action=action,
            timestamp=timestamp(),
            state_revision=self._browser_state_revision,
        )
        self._browser_state_revision = max(self._browser_state_revision, int(emission.state_revision or 0))
        normalized = []
        for item in emission.events or []:
            event = self._normalize_browser_state_event(item)
            if event is not None:
                normalized.append(event)
        return normalized

    def _normalize_browser_state_event(self, event: Any) -> dict[str, Any] | None:
        if not isinstance(event, dict):
            return None
        kind = str(event.get("event") or "").strip()
        mapping = {
            "invalidated": ("browser_state_invalidated", "invalidated"),
            "snapshot": ("browser_state_snapshot", "snapshot"),
            "dom_snapshot": ("browser_dom_snapshot", "dom_snapshot"),
            "screenshot": ("browser_screenshot", "screenshot"),
        }
        if kind not in mapping:
            return self._normalize_external_event(event)
        canonical_type, payload_key = mapping[kind]
        payload = event.get(payload_key) if isinstance(event.get(payload_key), dict) else {}
        data = {payload_key: payload, **payload}
        if event.get("timestamp") is not None and "timestamp" not in data:
            data["timestamp"] = event.get("timestamp")
        message_text = str(event.get("message") or payload.get("message") or canonical_type)
        extras = {
            key: value
            for key, value in event.items()
            if key
            not in {
                "type",
                "event",
                payload_key,
                "timestamp",
                "message",
                "data",
                "schema_version",
                "run_id",
                "conversation_id",
                "seq",
            }
        }
        normalized = self._emit(
            canonical_type,
            data=data,
            message=message_text,
            **extras,
        )
        return normalized

    def _normalize_external_event(self, event: Any) -> dict[str, Any] | None:
        if not isinstance(event, dict):
            return None
        event_type = str(event.get("type") or "").strip()
        if not event_type:
            return None
        if event.get("schema_version") == 1:
            legacy = to_legacy_chat_stream_event(event)
            if legacy is not None and self._is_activity_event(legacy):
                self._activity_events.append(legacy)
            return event
        payload = dict(event.get("data") or {})
        for key, value in event.items():
            if key == "type":
                continue
            payload.setdefault(key, value)
        normalized = self._emit(event_type, data=payload, message=str(payload.get("message") or event_type))
        return normalized

    def _legacy_tool_event_sink(self, event: dict[str, Any]) -> None:
        normalized = self._normalize_external_event(event)
        if normalized is not None:
            legacy = to_legacy_chat_stream_event(normalized)
            if legacy is not None and self._is_activity_event(legacy) and legacy not in self._activity_events:
                self._activity_events.append(legacy)

    def _legacy_stream_event_callback(self, event: dict[str, Any]) -> None:
        self._legacy_tool_event_sink(event)

    def _is_cancelled(self) -> bool:
        return self._cancel_event.is_set() or get_chat_cancellation_registry().is_cancelled(self._conversation_id)

    def _raise_if_cancelled(self) -> None:
        if self._is_cancelled():
            raise _ChatCancelled()

    @staticmethod
    def _tool_arguments(block: dict[str, Any]) -> dict[str, Any]:
        value = block.get("input", block.get("arguments", {}))
        if isinstance(value, str):
            try:
                parsed = __import__("json").loads(value)
            except Exception:
                return {"value": value}
            return parsed if isinstance(parsed, dict) else {"value": parsed}
        return value if isinstance(value, dict) else {}

    @staticmethod
    def _response_text(response: dict[str, Any]) -> str:
        blocks = response.get("content", []) if isinstance(response, dict) else []
        if isinstance(blocks, str):
            return blocks
        if not isinstance(blocks, list):
            return ""
        parts = []
        for block in blocks:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text") or ""))
        return "".join(parts)

    @staticmethod
    def _text_from_content_blocks(content: Any) -> str:
        if isinstance(content, str):
            return content
        if not isinstance(content, list):
            return ""
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(str(block.get("text") or ""))
            elif isinstance(block, str):
                parts.append(block)
        return "".join(parts).strip()

    def _fallback_complete_without_thinking(
        self,
        prepared: PreparedChatRun,
        messages: list[dict[str, Any]],
        *,
        transcript: str = "",
    ) -> dict[str, Any] | None:
        fallback_tool_sets: list[list[dict[str, Any]]] = []
        if prepared.provider_tools:
            fallback_tool_sets.append(prepared.provider_tools)
        fallback_tool_sets.append([])
        for tools in fallback_tool_sets:
            try:
                response = self._gateway.complete(
                    {
                        "model": prepared.model,
                        "messages": messages,
                        "tools": tools,
                        "params": _provider_visible_params(_params_without_thinking(prepared.params)),
                        "authority_context": prepared.request_context.get("authority", {}),
                    }
                )
            except AuthorityApprovalRequired:
                raise
            except Exception:
                continue
            if not isinstance(response, dict):
                continue
            if not self._text_from_content_blocks(response.get("content")) and not _tool_use_blocks(response):
                continue
            metadata = dict(response.get("metadata") or {})
            if transcript:
                metadata["thinking"] = {"state": "completed", "transcript": transcript}
            else:
                metadata.setdefault("thinking", {"state": "completed"})
            metadata["recovered_from_empty_stream"] = True
            metadata["fallback_kept_tools"] = bool(tools)
            metadata.setdefault("model", prepared.model)
            metadata.setdefault("attached_tool_count", len(_external_provider_tools(prepared.provider_tools)))
            metadata.setdefault("attached_tools", list(prepared.tools_called))
            metadata["thinking_level"] = prepared.params.get("thinking_level")
            metadata["deepthink_enabled"] = bool(prepared.params.get("deepthink_enabled"))
            response["metadata"] = metadata
            return response
        return None

    @staticmethod
    def _run_seal_policy(prepared: PreparedChatRun) -> RunSealPolicy:
        policy = build_run_seal_policy(
            params=prepared.params,
            profile_policy=prepared.request_context.get("profile_policy") if isinstance(prepared.request_context, dict) else None,
        )
        if not policy.enabled:
            return policy
        if response_has_structured_output(prepared.params) and not policy.allow_structured_output:
            return RunSealPolicy(
                enabled=False,
                max_retries=policy.max_retries,
                compact_on_failure=policy.compact_on_failure,
                allow_structured_output=policy.allow_structured_output,
                stream_tail_chars=policy.stream_tail_chars,
            )
        return policy

    def _should_compact_after_run_seal_failure(
        self,
        prepared: PreparedChatRun,
        messages: list[dict[str, Any]],
        *,
        finish_reason: str,
        attempts: int,
    ) -> bool:
        if finish_reason == "length":
            return True
        if attempts >= 1:
            return True
        context_window = int(
            (prepared.provider_capabilities or {}).get("max_context")
            or (prepared.provider_capabilities or {}).get("max_context_tokens")
            or 0
        )
        if context_window <= 0:
            return False
        return ContextCompressor().should_compact(
            messages,
            context_window=context_window,
            threshold=0.85,
            reserve_tokens=max(2048, int(context_window * 0.10)),
        )

    def _compact_messages_for_run_seal(
        self,
        prepared: PreparedChatRun,
        messages: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        result = ContextCompressor().compact(
            messages,
            metadata={
                "run_id": self._run_id or prepared.request_id,
                "conversation_id": prepared.conversation_id,
                "goal": prepared.user_text,
            },
        )
        replacement_history = result.get("replacement_history")
        return list(replacement_history) if isinstance(replacement_history, list) and replacement_history else list(messages)

    @staticmethod
    def _run_seal_success_response(
        response: dict[str, Any],
        *,
        seal: Any,
        attempts: int,
        compacted: bool,
        visible_text: str,
        had_interior_seal: bool,
        thinking_transcript: str,
    ) -> dict[str, Any]:
        updated = apply_visible_text_to_response(response, visible_text)
        metadata = dict(updated.get("metadata") or {})
        if thinking_transcript:
            existing_thinking = metadata.get("thinking") if isinstance(metadata.get("thinking"), dict) else {}
            existing_transcript = str(existing_thinking.get("transcript") or "").strip()
            combined_transcript = existing_transcript or thinking_transcript
            if existing_transcript and thinking_transcript not in existing_transcript:
                combined_transcript = existing_transcript + "\n\n" + thinking_transcript
            metadata["thinking"] = {
                **existing_thinking,
                "state": "completed",
                "transcript": combined_transcript,
                "source": str(existing_thinking.get("source") or "inline_reasoning_tag"),
            }
        metadata["run_seal"] = {
            "enabled": True,
            "ok": True,
            "attempts": attempts,
            "compacted": compacted,
            "system_hash": getattr(seal, "system_hash", ""),
            "finish_reason": updated.get("finish_reason"),
            "had_interior_seal": had_interior_seal,
            "had_inline_reasoning": bool(thinking_transcript),
        }
        updated["metadata"] = metadata
        return updated
