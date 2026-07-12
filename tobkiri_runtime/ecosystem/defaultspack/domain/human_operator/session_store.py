from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

from domain.chat.store import ChatStore

from .constants import HUMAN_OPERATOR_SESSION_DIRNAME


_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_.-]+$")


def _normalize_session_id(session_id: str) -> str:
    value = str(session_id or "").strip()
    if not value or _SAFE_ID_RE.fullmatch(value) is None:
        raise ValueError("invalid human-operator session id")
    return value


def session_dir(conversation_id: str) -> Path:
    root = ChatStore().conversation_workspace_dir(str(conversation_id or ""))
    path = root / HUMAN_OPERATOR_SESSION_DIRNAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def session_path(conversation_id: str, session_id: str) -> Path:
    return session_dir(conversation_id) / (_normalize_session_id(session_id) + ".json")


def save_session(conversation_id: str, session_id: str, payload: dict[str, Any]) -> Path:
    path = session_path(conversation_id, session_id)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_session(conversation_id: str, session_id: str) -> dict[str, Any] | None:
    path = session_path(conversation_id, session_id)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def session_route_path(
    conversation_id: str,
    session_id: str,
    *,
    view: str | None = None,
    prompt_view: str | None = None,
    flash: str | None = None,
) -> str:
    path = (
        "/api/human-operator/conversations/"
        + str(conversation_id or "")
        + "/sessions/"
        + _normalize_session_id(session_id)
    )
    query: dict[str, str] = {}
    if view:
        query["view"] = str(view)
    if prompt_view:
        query["prompt_view"] = str(prompt_view)
    if flash:
        query["flash"] = str(flash)
    return path + (("?" + urlencode(query)) if query else "")


def absolute_session_url(
    conversation_id: str,
    session_id: str,
    *,
    view: str | None = None,
    prompt_view: str | None = None,
    flash: str | None = None,
) -> str:
    host = str(os.environ.get("DEFAULTS_HTTP_HOST") or "127.0.0.1").strip() or "127.0.0.1"
    port = str(os.environ.get("DEFAULTS_HTTP_PORT") or "8766").strip() or "8766"
    if ":" in host and not host.startswith("["):
        host = "[" + host + "]"
    return "http://{}:{}{}".format(
        host,
        port,
        session_route_path(
            conversation_id,
            session_id,
            view=view,
            prompt_view=prompt_view,
            flash=flash,
        ),
    )
