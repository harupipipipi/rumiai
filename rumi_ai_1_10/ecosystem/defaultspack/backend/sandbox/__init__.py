"""sandbox module - Linux sandbox, GUI control."""
from __future__ import annotations
from typing import Any, Dict
class SandboxManager:
    def __init__(self): self._sandboxes = {}
    def create(self, name="default") -> Dict[str, Any]:
        self._sandboxes[name] = {"status": "running"}; return {"sandbox_id": name}
    def execute(self, sid: str, cmd: str) -> Dict[str, Any]:
        if sid not in self._sandboxes: return {"error": "Not found"}
        return {"output": f"[sandbox:{sid}] {cmd}", "exit_code": 0}
    def screenshot(self, sid: str) -> Dict[str, Any]: return {"status": "captured"}
    def click(self, sid: str, x: int, y: int) -> Dict[str, Any]: return {"status": "clicked", "x": x, "y": y}
    def type_text(self, sid: str, text: str) -> Dict[str, Any]: return {"status": "typed", "text": text}
    def destroy(self, sid: str) -> bool: return self._sandboxes.pop(sid, None) is not None
