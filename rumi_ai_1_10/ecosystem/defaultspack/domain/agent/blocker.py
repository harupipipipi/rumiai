from __future__ import annotations

from typing import Any
import json
import os
from pathlib import Path

from blocks._common import gen_id, timestamp


BLOCKER_MESSAGES = {
    "blocked_by_login": "Login required before the agent can continue.",
    "blocked_by_captcha": "Captcha required before the agent can continue.",
    "blocked_by_2fa": "Two-factor authentication required before the agent can continue.",
    "blocked_by_payment": "Payment confirmation required before the agent can continue.",
    "blocked_by_external_send": "External send confirmation required before the agent can continue.",
    "blocked_by_sensitive_confirmation": "Sensitive confirmation required before the agent can continue.",
}


def blocker_contract(agent_id: str, blocked_reason: str, *, profile_id: str = "", browser_profile_id: str = "") -> dict[str, Any]:
    return {
        "agent_id": agent_id,
        "status": "blocked",
        "blocked_reason": blocked_reason,
        "requires_user_action": True,
        "message": BLOCKER_MESSAGES.get(blocked_reason, "User action required before the agent can continue."),
        "resume_action": f"/api/agents/{agent_id}/resume",
        "profile_id": profile_id,
        "browser_profile_id": browser_profile_id,
    }


def _pack_root() -> Path:
    return Path(__file__).resolve().parents[2]


class BlockerStore:
    def __init__(self, root: Path | None = None) -> None:
        pack_root = Path(root or _pack_root())
        override = os.environ.get("RUMI_DEFAULTSPACK_AGENT_BLOCKERS_PATH", "").strip()
        self.path = Path(override) if override else pack_root / "user_data" / "shared" / "agents" / "blockers.json"

    def add(self, agent_id: str, message: str, *, severity: str = "medium", metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        data = self._read()
        blocker = {
            "blocker_id": "blocker_" + gen_id(),
            "agent_id": str(agent_id or ""),
            "message": str(message or ""),
            "severity": severity,
            "status": "active",
            "metadata": metadata if isinstance(metadata, dict) else {},
            "created_at": timestamp(),
            "updated_at": timestamp(),
        }
        data.setdefault("blockers", []).append(blocker)
        self._write(data)
        return blocker

    def resolve(self, blocker_id: str, *, resolution: str = "") -> dict[str, Any] | None:
        data = self._read()
        for blocker in data.setdefault("blockers", []):
            if isinstance(blocker, dict) and blocker.get("blocker_id") == blocker_id:
                blocker["status"] = "resolved"
                blocker["resolution"] = resolution
                blocker["resolved_at"] = timestamp()
                blocker["updated_at"] = timestamp()
                self._write(data)
                return dict(blocker)
        return None

    def list(self, agent_id: str = "", *, active_only: bool = False) -> list[dict[str, Any]]:
        blockers = [dict(item) for item in self._read().get("blockers", []) if isinstance(item, dict)]
        if agent_id:
            blockers = [item for item in blockers if item.get("agent_id") == agent_id]
        if active_only:
            blockers = [item for item in blockers if item.get("status") == "active"]
        blockers.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
        return blockers

    def _read(self) -> dict[str, Any]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {"blockers": []}
        except Exception:
            return {"blockers": []}

    def _write(self, data: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps({"schema_version": 1, **data}, ensure_ascii=False, indent=2), encoding="utf-8")
