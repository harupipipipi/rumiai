from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .peer_store import PEER_APPROVED, PEER_BLOCKED, PeerRecord, PeerStore


TOOL_CLAIM_KEYS = {
    "tool",
    "tools",
    "tool_id",
    "tool_name",
    "selected_tools",
    "requested_tool",
    "function",
    "function_id",
    "block",
    "block_id",
    "endpoint",
    "capability",
    "capabilities_request",
    "action",
}
DANGEROUS_TOOL_TERMS = {
    "terminal",
    "terminal_exec",
    "terminal_stream",
    "shell",
    "exec",
    "subprocess",
    "file",
    "file_write",
    "file_patch",
    "file_delete",
    "file_restore",
    "git",
    "git_push",
    "git_commit",
    "browser",
    "browser_computer",
    "computer_use",
}
APPROVAL_BYPASS_KEYS = {
    "approval_granted",
    "approved",
    "is_approved",
    "server_approved",
    "approval_token",
    "bypass_approval",
    "approval_bypass",
    "grant_approval",
}
DANGEROUS_TRUE_FLAGS = {
    "allow_shell",
    "allow_terminal",
    "allow_file_write",
    "allow_git",
    "allow_browser",
    "allow_direct_tool",
    "yolo_mode",
}


@dataclass
class P2PPolicyDecision:
    allowed: bool
    reason: str = ""
    code: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "allowed": bool(self.allowed),
            "reason": self.reason,
            "code": self.code,
            "metadata": dict(self.metadata),
        }


class P2PPolicy:
    def __init__(self, peer_store: PeerStore | None = None) -> None:
        self.peer_store = peer_store or PeerStore()

    def evaluate(self, envelope: dict[str, Any], *, peer: PeerRecord | None = None) -> P2PPolicyDecision:
        sender_id = str(envelope.get("sender_id") or "").strip()
        peer = peer or self.peer_store.get_peer(sender_id)
        if peer is None:
            return _deny("unknown peer", "PEER_UNKNOWN")
        if peer.status == PEER_BLOCKED:
            return _deny("peer is blocked", "PEER_BLOCKED")
        if peer.status != PEER_APPROVED:
            return _deny("peer is not approved", "PEER_UNAPPROVED")

        denied_claim = _find_denied_claim({"body": envelope.get("body"), "metadata": envelope.get("metadata"), "type": envelope.get("type")})
        if denied_claim:
            return _deny(denied_claim["reason"], "PRIVILEGED_CLAIM_DENIED", denied_claim)

        required = required_capability(envelope)
        if required and not _has_capability(peer.capabilities, required):
            return _deny("peer lacks required capability", "CAPABILITY_DENIED", {"required_capability": required})

        company_id = _company_id_from(envelope)
        if company_id and not _company_allowed(peer.allowed_company_ids, company_id):
            return _deny("peer is not allowed for company", "COMPANY_DENIED", {"company_id": company_id})

        return P2PPolicyDecision(True, code="OK", metadata={"required_capability": required, "company_id": company_id})


def required_capability(envelope: dict[str, Any]) -> str:
    message_type = str(envelope.get("type") or "message").strip().lower()
    if message_type in {"message", "p2p.message", "chat.message"}:
        return "message"
    if message_type in {"event", "external_event", "p2p.event"}:
        return "external_event"
    if "company" in message_type:
        return "company_message"
    return message_type


def _has_capability(capabilities: list[str], required: str) -> bool:
    normalized = {str(item).strip().lower() for item in capabilities if str(item).strip()}
    return "*" in normalized or required in normalized or f"p2p.{required}" in normalized


def _company_allowed(allowed_company_ids: list[str], company_id: str) -> bool:
    normalized = {str(item).strip() for item in allowed_company_ids if str(item).strip()}
    return "*" in normalized or str(company_id or "").strip() in normalized


def _company_id_from(envelope: dict[str, Any]) -> str:
    body = envelope.get("body") if isinstance(envelope.get("body"), dict) else {}
    metadata = envelope.get("metadata") if isinstance(envelope.get("metadata"), dict) else {}
    for source in (body, metadata):
        company_id = str(source.get("company_id") or source.get("allowed_company_id") or "").strip()
        if company_id:
            return company_id
    return ""


def _find_denied_claim(value: Any, path: tuple[str, ...] = ()) -> dict[str, Any] | None:
    if isinstance(value, dict):
        for key, item in value.items():
            key_text = str(key or "").strip()
            lower_key = key_text.lower()
            next_path = (*path, key_text)
            if lower_key in APPROVAL_BYPASS_KEYS and _truthy(item):
                return {"path": ".".join(next_path), "reason": "remote approval claims are not accepted"}
            if lower_key in DANGEROUS_TRUE_FLAGS and _truthy(item):
                return {"path": ".".join(next_path), "reason": "remote privileged execution flags are not accepted"}
            if lower_key == "write_actions_require_approval" and item is False:
                return {"path": ".".join(next_path), "reason": "remote approval policy override is not accepted"}
            if lower_key in TOOL_CLAIM_KEYS and _contains_dangerous_tool_term(item):
                return {"path": ".".join(next_path), "reason": "remote privileged tool execution is not accepted"}
            nested = _find_denied_claim(item, next_path)
            if nested:
                return nested
    elif isinstance(value, list):
        for index, item in enumerate(value):
            nested = _find_denied_claim(item, (*path, str(index)))
            if nested:
                return nested
    return None


def _contains_dangerous_tool_term(value: Any) -> bool:
    if isinstance(value, dict):
        return any(_contains_dangerous_tool_term(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_dangerous_tool_term(item) for item in value)
    text = str(value or "").strip().lower()
    if not text:
        return False
    parts = {text, *text.replace(".", "_").replace("-", "_").split("_")}
    return any(term in text or term in parts for term in DANGEROUS_TOOL_TERMS)


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if value is None:
        return False
    text = str(value).strip().lower()
    return text not in {"", "0", "false", "no", "off", "none", "null"}


def _deny(reason: str, code: str, metadata: dict[str, Any] | None = None) -> P2PPolicyDecision:
    return P2PPolicyDecision(False, reason=reason, code=code, metadata=dict(metadata or {}))
