from __future__ import annotations

import base64
import mimetypes
from pathlib import Path
from typing import Any

from ._utils import default_browser_root, now_iso, safe_int, sanitize_id, write_json


READ_ONLY_ACTIONS = {
    "browser.profile.list",
    "browser.profile.get",
    "browser.session.health",
    "browser.session.list",
    "browser.tab.list",
    "browser.tab.snapshot",
    "browser.tab.screenshot",
    "browser.ref.resolve",
    "browser.ref.recover",
}

MUTATING_ACTIONS = {
    "browser.profile.create",
    "browser.profile.update",
    "browser.profile.delete",
    "browser.profile.set_active",
    "browser.session.start",
    "browser.session.stop",
    "browser.session.restart",
    "browser.tab.open",
    "browser.tab.focus",
    "browser.tab.close",
    "browser.tab.navigate",
    "browser.ref.click",
    "browser.ref.type",
    "browser.ref.key",
    "browser.ref.scroll",
}


class BrowserArtifactStore:
    def __init__(self, root: str | Path | None = None) -> None:
        self.root = Path(root) if root is not None else default_browser_root() / "artifacts"

    def write_base64(self, data: str, *, suffix: str = ".png", mime_type: str | None = None, name: str | None = None) -> dict[str, Any]:
        artifact_id = sanitize_id(name or "browser-artifact-{}".format(now_iso()), default="browser-artifact")
        path = self.root / "{}{}".format(artifact_id, suffix if suffix.startswith(".") else "." + suffix)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(base64.b64decode(data))
        return self._artifact_record(path, mime_type=mime_type)

    def write_json(self, value: Any, *, name: str) -> dict[str, Any]:
        artifact_id = sanitize_id(name, default="browser-json")
        path = self.root / "{}.json".format(artifact_id)
        write_json(path, value)
        return self._artifact_record(path, mime_type="application/json")

    @staticmethod
    def _artifact_record(path: Path, *, mime_type: str | None = None) -> dict[str, Any]:
        return {
            "id": path.stem,
            "path": str(path),
            "mime_type": mime_type or mimetypes.guess_type(str(path))[0] or "application/octet-stream",
            "size_bytes": path.stat().st_size if path.exists() else 0,
            "created_at": now_iso(),
        }


class BrowserPolicy:
    def __init__(self, *, read_only: bool = False) -> None:
        self.read_only = bool(read_only)

    def evaluate(self, action: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = payload or {}
        if self.read_only and action in MUTATING_ACTIONS:
            return {
                "allowed": False,
                "requires_approval": False,
                "reason": "browser policy is read-only",
                "action": action,
            }
        return {
            "allowed": True,
            "requires_approval": self.requires_approval(action, payload),
            "action": action,
        }

    @staticmethod
    def requires_approval(action: str, payload: dict[str, Any] | None = None) -> bool:
        if action in READ_ONLY_ACTIONS:
            return False
        if payload and payload.get("dry_run"):
            return False
        return action in MUTATING_ACTIONS or action.startswith("computer.")


def computer_use_fallback_contract(
    *,
    browser_action: str,
    reason: str,
    ref: dict[str, Any] | None = None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = dict(payload or {})
    action = browser_action.rsplit(".", 1)[-1]
    if action.startswith("ref_"):
        action = action.removeprefix("ref_")
    fallback_payload: dict[str, Any] = {"action": action}
    bounds = (ref or {}).get("bounds") if isinstance(ref, dict) else None
    if action in {"click", "move"} and isinstance(bounds, dict):
        fallback_payload["x"] = safe_int(bounds.get("x")) + max(safe_int(bounds.get("width")) // 2, 0)
        fallback_payload["y"] = safe_int(bounds.get("y")) + max(safe_int(bounds.get("height")) // 2, 0)
    for key in ("text", "key", "amount", "x", "y"):
        if key in payload:
            fallback_payload[key] = payload[key]
    return {
        "ok": False,
        "requires_fallback": True,
        "fallback_tool": "computer_use",
        "fallback_action": action,
        "fallback_payload": fallback_payload,
        "reason": reason,
        "ref": ref,
    }
