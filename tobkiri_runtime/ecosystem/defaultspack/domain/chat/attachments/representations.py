from __future__ import annotations

import base64
from typing import Any


MAX_INLINE_DATA_URL_CHARS = 120_000


def build_representations(attachment: dict[str, Any], workspace_path: str = "") -> dict[str, Any]:
    reps: dict[str, Any] = {}
    content = attachment.get("content")
    if isinstance(content, str) and content:
        reps["text"] = {"chars": len(content), "truncated": bool(attachment.get("truncated")), "text": content}
    data_url = attachment.get("dataUrl") or attachment.get("data_url")
    mime = str(attachment.get("type") or attachment.get("mime_type") or "").lower()
    if isinstance(data_url, str) and data_url.startswith("data:"):
        byte_length = _data_url_byte_length(data_url)
        if mime.startswith("image/") and len(data_url) <= MAX_INLINE_DATA_URL_CHARS:
            reps["inline_data_url"] = {"mime_type": mime or _data_url_mime(data_url), "data_url": data_url, "bytes": byte_length}
        elif mime.startswith("image/"):
            reps["inline_data_url"] = {"mime_type": mime or _data_url_mime(data_url), "workspace_path": workspace_path, "bytes": byte_length}
            reps["image_pages"] = [{"workspace_path": workspace_path, "mime_type": mime or _data_url_mime(data_url)}]
        elif mime == "application/pdf":
            reps["pdf_text"] = {"workspace_path": workspace_path}
    if attachment.get("provider_refs"):
        reps["provider_file_ids"] = dict(attachment.get("provider_refs") or {})
    return reps


def _data_url_mime(data_url: str) -> str:
    header = data_url.split(",", 1)[0]
    return header.replace("data:", "", 1).split(";", 1)[0] or "application/octet-stream"


def _data_url_byte_length(data_url: str) -> int | None:
    if "," not in data_url:
        return None
    try:
        return len(base64.b64decode(data_url.split(",", 1)[1], validate=True))
    except Exception:
        return None
