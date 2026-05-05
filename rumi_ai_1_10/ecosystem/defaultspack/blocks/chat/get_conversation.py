import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from blocks._common import ok, error, gen_id, timestamp

from domain.chat.store import ChatStore
from domain.approval.store import ApprovalStore


def _sync_tool_approval_statuses(conv):
    store = ApprovalStore()
    for message in conv.get("messages", []) if isinstance(conv.get("messages"), list) else []:
        logs = message.get("tool_logs")
        if not isinstance(logs, list):
            continue
        for log in logs:
            if not isinstance(log, dict):
                continue
            result = log.get("result")
            if not isinstance(result, dict):
                continue
            data = result.get("data") if isinstance(result.get("data"), dict) else result
            widget = data.get("widget") if isinstance(data.get("widget"), dict) else data
            if not isinstance(widget, dict):
                continue
            approval_id = str(widget.get("approval_id") or "")
            if not approval_id:
                continue
            approval = store.get(approval_id)
            if not approval:
                continue
            widget["approval_status"] = approval.get("status")
            widget["approval_expired"] = approval.get("expired")
            if "approval_token" not in widget and approval.get("has_token"):
                widget["approval_token"] = "[redacted]"
    return conv


def run(input_data, context):
    store = ChatStore()
    conversation_id = input_data.get("conversation_id")
    if not conversation_id:
        return error("conversation_id is required", "INVALID_INPUT")
    conv = store.get_conversation(conversation_id)
    if conv is None:
        return error("Conversation not found", "NOT_FOUND")
    return ok(_sync_tool_approval_statuses(conv))
