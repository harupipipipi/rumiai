from __future__ import annotations

import time
from typing import Any

from domain.external.chat_link import CHAT_LINK_PROMPT, linked_conversation_id
from domain.safety import approval


LINE_APPROVAL_COMMAND_IDS = {"approvals", "approve", "deny"}
_LATEST_TOKENS = {"", "latest", "last", "newest", "recent", "直近", "最新"}
_MAX_REPLY_CHARS = 4500
_CONTINUE_TEXT = "ユーザーがLINEから許可しました。承認済みの操作を続行してください。"


def handle_line_approval_command(command_id: str, arg_text: str, context: dict[str, Any]) -> dict[str, Any]:
    command_id = str(command_id or "").strip().lower()
    conversation_id = linked_conversation_id(context)
    if not conversation_id:
        return _result(CHAT_LINK_PROMPT, action="needs_chat_link")

    pending = pending_approval_requests(conversation_id)
    if command_id == "approvals":
        return _result(_format_pending_requests(pending), action="list", count=len(pending))

    if command_id == "deny":
        request, reason, message = _resolve_request_for_decision(arg_text, pending, allow_reason=True)
        if request is None:
            return _result(message, action="resolve_failed", count=len(pending))
        decision = approval.deny(str(request.get("request_id") or ""), reason)
        short_id = _short_request_id(str(request.get("request_id") or ""))
        if str(decision.get("status") or "") == "missing":
            return _result(f"拒否できませんでした: {decision.get('reason') or 'not found'}", action="deny_failed")
        return _result(f"拒否しました: {short_id}", action="denied", request_id=str(request.get("request_id") or ""))

    if command_id == "approve":
        request, _unused_reason, message = _resolve_request_for_decision(arg_text, pending, allow_reason=False)
        if request is None:
            return _result(message, action="resolve_failed", count=len(pending))
        request_id = str(request.get("request_id") or "")
        decision = approval.approve(request_id)
        if not decision.get("approved"):
            reason = str(decision.get("reason") or "approval failed")
            return _result(f"許可できませんでした: {reason}", action="approve_failed", request_id=request_id)
        continuation = _continue_approved_request(conversation_id, request, decision, context)
        short_id = _short_request_id(request_id)
        if not continuation.get("continued"):
            suffix = str(continuation.get("message") or "続きは画面で確認してください。").strip()
            return _result(f"許可しました: {short_id}\n{suffix}", action="approved", request_id=request_id)
        assistant_text = str(continuation.get("assistant_text") or "").strip()
        if assistant_text:
            return _result(_clip_text(f"許可しました: {short_id}\n{assistant_text}"), action="approved_continued", request_id=request_id)
        return _result(f"許可しました: {short_id}\n続行しました。", action="approved_continued", request_id=request_id)

    return _result("承認コマンドが見つかりません。/approvals を見てね。", action="unknown")


def pending_approval_count(context: dict[str, Any]) -> int:
    conversation_id = linked_conversation_id(context)
    if not conversation_id:
        return 0
    return len(pending_approval_requests(conversation_id, limit=100))


def pending_approval_requests(conversation_id: str, *, limit: int = 20) -> list[dict[str, Any]]:
    target = str(conversation_id or "").strip()
    if not target:
        return []
    try:
        requests = approval.list_approval_requests(status="pending", include_expired=False, limit=100)
    except Exception:
        return []
    scoped = [request for request in requests if _request_conversation_id(request) == target]
    return scoped[: max(1, int(limit or 20))]


def _continue_approved_request(
    conversation_id: str,
    request: dict[str, Any],
    decision: dict[str, Any],
    context: dict[str, Any],
) -> dict[str, Any]:
    details = request.get("details") if isinstance(request.get("details"), dict) else {}
    tool_name = str(details.get("tool_name") or "").strip()
    if not tool_name:
        return {"continued": False, "message": "許可しました。続きは画面で確認してください。"}

    payload = details.get("arguments") if isinstance(details.get("arguments"), dict) else {}
    action = str(details.get("action") or request.get("operation") or tool_name).strip()
    operation = str(request.get("operation") or details.get("operation") or action).strip()
    request_id = str(request.get("request_id") or "").strip()
    approval_token = str(decision.get("token") or "").strip()
    if not approval_token:
        return {"continued": False, "message": "許可トークンを作れませんでした。"}

    metadata = {
        "source": "external_integration",
        "external": {"provider": "line", "approval_request_id": request_id},
        "approval_followup": {
            "action": action,
            "operation": operation,
            "approval_token": approval_token,
            "payload": dict(payload),
            "arguments": dict(payload),
            "request_id": request_id,
            "tool_call_id": str(details.get("tool_call_id") or request_id),
            "tool_name": tool_name,
        },
        "runtime_content": _CONTINUE_TEXT,
        "selected_tools": [tool_name],
    }
    request_input = {
        "conversation_id": conversation_id,
        "message": {
            "role": "user",
            "content": _CONTINUE_TEXT,
            "metadata": metadata,
        },
        "params": {
            "tool_choice": "required",
            "tool_policy": {"selected_tools": [tool_name]},
        },
        "tools": [tool_name],
    }
    try:
        from blocks.chat import send as chat_send

        result = chat_send.run(request_input, dict(context or {}))
    except Exception:
        return {"continued": False, "message": "続行中にエラーが出ました。/logs も確認してね。"}

    if not isinstance(result, dict):
        return {"continued": False, "message": "続行結果を読めませんでした。"}
    if result.get("status") == "error":
        return {"continued": False, "message": "続行中にエラーが出ました。/logs も確認してね。", "result": result}
    assistant_text = _assistant_text_from_chat_result(result)
    return {"continued": True, "assistant_text": assistant_text, "result": result}


def _resolve_request_for_decision(
    arg_text: str,
    pending: list[dict[str, Any]],
    *,
    allow_reason: bool,
) -> tuple[dict[str, Any] | None, str, str]:
    if not pending:
        return None, "", "承認待ちはありません。"

    token, rest = _first_token(arg_text)
    normalized = token.strip().lower()
    if normalized in _LATEST_TOKENS:
        if len(pending) == 1:
            return pending[0], rest if allow_reason else "", ""
        return None, "", "複数あるのでIDを指定してください。\n" + _format_pending_requests(pending)

    matches = [request for request in pending if _request_id_matches(token, str(request.get("request_id") or ""))]
    if not matches and allow_reason and len(pending) == 1:
        return pending[0], str(arg_text or "").strip(), ""
    if not matches:
        return None, "", "その承認IDは見つかりません。\n" + _format_pending_requests(pending)
    if len(matches) > 1:
        return None, "", "候補が複数あります。もう少し長いIDで指定してください。"
    return matches[0], rest if allow_reason else "", ""


def _format_pending_requests(pending: list[dict[str, Any]]) -> str:
    if not pending:
        return "承認待ちはありません。"
    lines = ["承認待ち:"]
    for request in pending[:8]:
        request_id = str(request.get("request_id") or "")
        details = request.get("details") if isinstance(request.get("details"), dict) else {}
        tool_name = str(details.get("tool_name") or request.get("operation") or "tool").strip()
        action = str(details.get("action") or request.get("operation") or "").strip()
        risk = str(request.get("risk_level") or "").strip()
        ttl = _remaining_ttl_text(request)
        summary = " ".join(part for part in (tool_name, action) if part)
        suffix = " / ".join(part for part in (risk, ttl) if part)
        lines.append(f"{_short_request_id(request_id)}: {summary}" + (f" ({suffix})" if suffix else ""))
    command_hint = "許可: /approve"
    deny_hint = "拒否: /deny"
    if len(pending) > 1:
        command_hint += " <id>"
        deny_hint += " <id>"
    lines.append(f"{command_hint} / {deny_hint}")
    return _clip_text("\n".join(lines))


def _assistant_text_from_chat_result(result: dict[str, Any]) -> str:
    data = result.get("data") if isinstance(result.get("data"), dict) else result
    if not isinstance(data, dict):
        return ""
    content = data.get("content")
    if isinstance(content, str):
        return content.strip()
    if not isinstance(content, list):
        return str(data.get("raw_text") or data.get("text") or "").strip()
    parts: list[str] = []
    for item in content:
        if isinstance(item, str):
            parts.append(item)
        elif isinstance(item, dict) and isinstance(item.get("text"), str):
            parts.append(item["text"])
    return "\n".join(part.strip() for part in parts if part.strip())


def _request_conversation_id(request: dict[str, Any]) -> str:
    details = request.get("details") if isinstance(request.get("details"), dict) else {}
    return str(details.get("conversation_id") or "").strip()


def _request_id_matches(token: str, request_id: str) -> bool:
    needle = str(token or "").strip().lower()
    value = str(request_id or "").strip().lower()
    if not needle or not value:
        return False
    short = value[-8:]
    return needle == value or needle == short or value.endswith(needle)


def _first_token(arg_text: str) -> tuple[str, str]:
    text = str(arg_text or "").strip()
    if not text:
        return "", ""
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {"'", '"'}:
        return text[1:-1].strip(), ""
    token, sep, rest = text.partition(" ")
    return token.strip().strip("'\""), rest.strip() if sep else ""


def _remaining_ttl_text(request: dict[str, Any]) -> str:
    try:
        remaining = int(request.get("expires_at") or 0) - int(time.time())
    except Exception:
        return ""
    if remaining <= 0:
        return "期限切れ"
    if remaining >= 60:
        return f"残り{max(1, remaining // 60)}分"
    return f"残り{remaining}秒"


def _short_request_id(request_id: str) -> str:
    value = str(request_id or "").strip()
    if len(value) <= 12:
        return value or "(none)"
    return value[:4] + "..." + value[-8:]


def _clip_text(text: str, limit: int = _MAX_REPLY_CHARS) -> str:
    value = str(text or "")
    if len(value) <= limit:
        return value
    return value[: max(0, limit - 1)].rstrip() + "…"


def _result(text: str, *, action: str, **metadata: Any) -> dict[str, Any]:
    return {
        "status": "ok",
        "assistant_text": _clip_text(text),
        "line_approval": {"action": action, **metadata},
    }
