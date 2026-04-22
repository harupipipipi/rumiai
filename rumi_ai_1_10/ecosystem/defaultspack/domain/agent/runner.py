from __future__ import annotations

from typing import Any, Dict, Optional

from ..extensions.loading import import_entrypoint
from ..extensions.runtime import get_extension_registry


class AgentRunner:
    """Mode-driven agent runner scaffold for extension migration."""

    def __init__(self) -> None:
        self._registry = get_extension_registry().agent_modes()

    def get_mode(self, mode_id: str) -> Optional[Dict[str, Any]]:
        return self._registry.get(mode_id)

    def run(self, mode_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        mode = self.get_mode(mode_id)
        if mode is None:
            return {"ok": False, "error": f"agent mode not found: {mode_id}"}
        entrypoint = str(mode.get("entrypoint", "")).strip()
        if not entrypoint:
            return {"ok": True, "mode": mode_id, "payload": payload}
        runner = import_entrypoint(entrypoint)
        return runner(payload, {"mode_id": mode_id})
