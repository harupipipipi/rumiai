from __future__ import annotations

import json
import os
import re
import tempfile
import time
from pathlib import Path
from typing import Any


PREVIEW_TTL_SECONDS = 5 * 60
_PREVIEW_ID_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")


class ToolSelectionPreviewAccessError(Exception):
    def __init__(self, message: str, code: str) -> None:
        super().__init__(message)
        self.code = code


class ToolSelectionPreviewStore:
    def __init__(self, *, pack_root: Path | None = None) -> None:
        self._pack_root = pack_root or Path(__file__).resolve().parents[2]
        root_override = os.environ.get("RUMI_DEFAULTSPACK_TOOL_SELECTION_PREVIEW_DIR")
        self._root = (
            Path(root_override).expanduser()
            if root_override
            else self._pack_root / "user_data" / "shared" / "tool_selection_previews"
        )

    def save(self, snapshot: dict[str, Any]) -> None:
        preview_id = str(snapshot.get("preview_id") or "").strip()
        if not _valid_preview_id(preview_id):
            return
        try:
            payload = dict(snapshot)
            now = time.time()
            payload.setdefault("created_at_epoch", now)
            payload.setdefault("expires_at_epoch", now + PREVIEW_TTL_SECONDS)
            self._root.mkdir(parents=True, exist_ok=True)
            self._atomic_write_json(self._root / f"{preview_id}.json", payload)
        except OSError:
            return

    def get(self, preview_id: str) -> dict[str, Any] | None:
        candidate = str(preview_id or "").strip()
        if not _valid_preview_id(candidate):
            return None
        try:
            payload = json.loads((self._root / f"{candidate}.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return payload if isinstance(payload, dict) else None

    def get_authorized(self, preview_id: str, context: dict[str, Any] | None) -> dict[str, Any]:
        snapshot = self.get(preview_id)
        if snapshot is None:
            raise ToolSelectionPreviewAccessError("Tool selection preview not found", "NOT_FOUND")
        if _is_expired(snapshot):
            raise ToolSelectionPreviewAccessError("Tool selection preview expired", "EXPIRED")
        if not _context_can_access_preview(snapshot, context or {}):
            raise ToolSelectionPreviewAccessError(
                "Tool selection preview is not available to this profile",
                "FORBIDDEN",
            )
        return snapshot

    def _atomic_write_json(self, path: Path, payload: dict[str, Any]) -> None:
        fd, tmp_name = tempfile.mkstemp(
            dir=str(path.parent),
            prefix=f".{path.name}.",
            suffix=".tmp",
        )
        tmp_path = Path(tmp_name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=True)
                handle.flush()
                os.fsync(handle.fileno())
            try:
                os.chmod(tmp_path, 0o600)
            except OSError:
                pass
            os.replace(tmp_path, path)
            try:
                os.chmod(path, 0o600)
            except OSError:
                pass
        except BaseException:
            try:
                tmp_path.unlink()
            except OSError:
                pass
            raise


def preview_context_metadata(context: dict[str, Any] | None, *, conversation_id: str = "") -> dict[str, str]:
    safe_context = context if isinstance(context, dict) else {}
    return {
        "owner_profile_id": _context_profile_id(safe_context),
        "conversation_id": str(conversation_id or safe_context.get("conversation_id") or "").strip(),
    }


def _valid_preview_id(value: str) -> bool:
    return bool(_PREVIEW_ID_RE.match(str(value or "").strip()))


def _is_expired(snapshot: dict[str, Any]) -> bool:
    expires_at = _float_or_none(snapshot.get("expires_at_epoch"))
    return expires_at is not None and expires_at <= time.time()


def _context_can_access_preview(snapshot: dict[str, Any], context: dict[str, Any]) -> bool:
    owner_profile_id = str(snapshot.get("owner_profile_id") or "").strip()
    context_profile_id = _context_profile_id(context)
    if owner_profile_id and (not context_profile_id or owner_profile_id != context_profile_id):
        return False
    conversation_id = str(snapshot.get("conversation_id") or "").strip()
    context_conversation_id = str(context.get("conversation_id") or context.get("chat_id") or "").strip()
    if conversation_id and context_conversation_id and conversation_id != context_conversation_id:
        return False
    return True


def _context_profile_id(context: dict[str, Any]) -> str:
    principal = context.get("_authenticated_principal") if isinstance(context, dict) else None
    if isinstance(principal, dict):
        candidate = str(principal.get("profile_id") or "").strip()
        if candidate:
            return candidate
    subject = context.get("_authority_subject") if isinstance(context, dict) else None
    if isinstance(subject, dict):
        candidate = str(subject.get("profile_id") or "").strip()
        if candidate:
            return candidate
    for key in ("profile_id", "input_profile_id", "active_profile_id"):
        candidate = str(context.get(key) or "").strip() if isinstance(context, dict) else ""
        if candidate:
            return candidate
    return ""


def _float_or_none(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
