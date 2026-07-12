from __future__ import annotations

from blocks._common import error
from domain.human_operator.page import render_session_page
from domain.human_operator.session_store import load_session


def run(input_data, context):
    del context
    conversation_id = str((input_data or {}).get("conversation_id") or "").strip()
    session_id = str((input_data or {}).get("session_id") or "").strip()
    if not conversation_id or not session_id:
        result = error("conversation_id and session_id are required", "INVALID_INPUT")
        result["_http_status"] = 400
        return result
    session = load_session(conversation_id, session_id)
    if session is None:
        result = error("Human Operator session not found", "NOT_FOUND")
        result["_http_status"] = 404
        return result
    view = str((input_data or {}).get("view") or "readable").strip().lower()
    if view not in {"readable", "json"}:
        view = "readable"
    prompt_view = str((input_data or {}).get("prompt_view") or "original").strip().lower()
    if prompt_view not in {"original", "rough_ja", "compact", "launch", "live"}:
        prompt_view = "original"
    flash = str((input_data or {}).get("flash") or "").strip().lower()
    return {
        "_static": True,
        "content_type": "text/html; charset=utf-8",
        "body": render_session_page(
            conversation_id,
            session_id,
            session,
            view=view,
            prompt_view=prompt_view,
            flash=flash,
        ),
    }
