from __future__ import annotations

import json
import os
import re
import tempfile
import time
from pathlib import Path
from typing import Any


TRACE_TTL_SECONDS = 7 * 24 * 60 * 60
_TRACE_ID_RE = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")


class ToolSelectionTraceAccessError(Exception):
    def __init__(self, message: str, code: str) -> None:
        super().__init__(message)
        self.code = code


class ToolSelectionTraceStore:
    def __init__(self, *, pack_root: Path | None = None) -> None:
        self._pack_root = pack_root or Path(__file__).resolve().parents[2]
        root_override = os.environ.get("RUMI_DEFAULTSPACK_TOOL_SELECTION_TRACE_DIR")
        self._root = (
            Path(root_override).expanduser()
            if root_override
            else self._pack_root / "user_data" / "shared" / "tool_selection_traces"
        )

    def save(self, trace: dict[str, Any]) -> None:
        trace_id = str(trace.get("selection_id") or "").strip()
        if not _valid_trace_id(trace_id):
            return
        try:
            payload = dict(trace)
            now = time.time()
            payload.setdefault("created_at_epoch", now)
            payload.setdefault("expires_at_epoch", now + TRACE_TTL_SECONDS)
            self._root.mkdir(parents=True, exist_ok=True)
            self._atomic_write_json(self._root / f"{trace_id}.json", payload)
        except OSError:
            return

    def get(self, trace_id: str) -> dict[str, Any] | None:
        candidate = str(trace_id or "").strip()
        if not _valid_trace_id(candidate):
            return None
        path = self._root / f"{candidate}.json"
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        return payload if isinstance(payload, dict) else None

    def get_authorized(self, trace_id: str, context: dict[str, Any] | None) -> dict[str, Any]:
        trace = self.get(trace_id)
        if trace is None:
            raise ToolSelectionTraceAccessError("Tool selection trace not found", "NOT_FOUND")
        if _is_expired(trace):
            raise ToolSelectionTraceAccessError("Tool selection trace expired", "EXPIRED")
        if not _context_can_access_trace(trace, context or {}):
            raise ToolSelectionTraceAccessError("Tool selection trace is not available to this profile", "FORBIDDEN")
        return trace

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


def _valid_trace_id(value: str) -> bool:
    return bool(_TRACE_ID_RE.match(str(value or "").strip()))


def _is_expired(trace: dict[str, Any]) -> bool:
    expires_at = _float_or_none(trace.get("expires_at_epoch"))
    return expires_at is not None and expires_at <= time.time()


def _context_can_access_trace(trace: dict[str, Any], context: dict[str, Any]) -> bool:
    owner_profile_id = str(trace.get("owner_profile_id") or "").strip()
    context_profile_id = _context_profile_id(context)
    if owner_profile_id:
        if not context_profile_id or context_profile_id != owner_profile_id:
            return False
    conversation_id = str(trace.get("conversation_id") or "").strip()
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
