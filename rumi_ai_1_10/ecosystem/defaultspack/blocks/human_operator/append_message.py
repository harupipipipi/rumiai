from __future__ import annotations

from blocks._common import error
from domain.human_operator.page import append_manual_message
from domain.human_operator.session_store import load_session, session_route_path


def run(input_data, context):
    del context
    conversation_id = str((input_data or {}).get("conversation_id") or "").strip()
    session_id = str((input_data or {}).get("session_id") or "").strip()
    if not conversation_id or not session_id:
        result = error("conversation_id and session_id are required", "INVALID_INPUT")
        result["_http_status"] = 400
        return result
    if load_session(conversation_id, session_id) is None:
        result = error("Human Operator session not found", "NOT_FOUND")
        result["_http_status"] = 404
        return result
    role = str((input_data or {}).get("role") or "user").strip().lower()
    text = str((input_data or {}).get("text") or "")
    content_format = str((input_data or {}).get("content_format") or "text").strip().lower()
    view = str((input_data or {}).get("view") or "readable").strip().lower()
    prompt_view = str((input_data or {}).get("prompt_view") or "original").strip().lower()
    try:
        append_manual_message(
            conversation_id,
            session_id,
            role=role,
            raw_text=text,
            content_format=content_format,
        )
    except ValueError as exc:
        result = error(str(exc), "INVALID_INPUT")
        result["_http_status"] = 400
        return result
    except RuntimeError as exc:
        result = error(str(exc), "INTERNAL_ERROR")
        result["_http_status"] = 500
        return result
    flash = "assistant_added" if role == "assistant" else "user_added"
    return {
        "_redirect": True,
        "status_code": 303,
        "location": session_route_path(
            conversation_id,
            session_id,
            view=view if view in {"readable", "json"} else "readable",
            prompt_view=prompt_view,
            flash=flash,
        ),
    }
