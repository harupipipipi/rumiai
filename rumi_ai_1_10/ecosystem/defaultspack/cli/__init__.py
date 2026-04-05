"""cli module - Command-line interface for defaultspack."""
from __future__ import annotations
from typing import Any, Dict, List, Optional
class CLIManager:
    def __init__(self): self._commands = {}; self._session_id: Optional[str] = None
    def register_command(self, name: str, handler: Any): self._commands[name] = handler
    def execute(self, command: str, args=None) -> Dict[str, Any]:
        h = self._commands.get(command)
        if not h: return {"error": f"Unknown command: {command}"}
        try: return {"result": h(args or {})}
        except Exception as e: return {"error": str(e)}
    def list_commands(self) -> List[str]: return list(self._commands.keys())
    def set_session(self, sid: str): self._session_id = sid
    def get_session(self) -> Optional[str]: return self._session_id
