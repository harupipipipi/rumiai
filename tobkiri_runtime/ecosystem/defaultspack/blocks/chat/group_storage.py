from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from _common import ok, error


def _normalize_root_path(value) -> Path:
    text = str(value or "").strip()
    if not text:
        raise ValueError("root_path is required")
    resolved = Path(text).expanduser().resolve(strict=True)
    if not resolved.is_dir():
        raise ValueError("root_path is not a directory")
    return resolved


def run(input_data, context=None):
    del context
    try:
        root_path = _normalize_root_path((input_data or {}).get("root_path") or (input_data or {}).get("workspace_root"))
    except (OSError, ValueError) as exc:
        return error(str(exc), code="INVALID_INPUT")

    rumi_data_path = root_path / ".rumiDP"
    chat_path = rumi_data_path / "chat"
    try:
        (chat_path / "conversations").mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return error(str(exc), code="GROUP_STORAGE_CREATE_FAILED")

    return ok(
        {
            "root_path": str(root_path),
            "rumi_data_path": str(rumi_data_path),
            "chat_store_path": str(chat_path / "conversations.json"),
        }
    )
