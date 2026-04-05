"""coding module - File operations, git operations, terminal."""
from __future__ import annotations
from typing import Any, Dict
class CodingManager:
    def __init__(self): self._terminals = {}
    def file_read(self, path: str) -> Dict[str, Any]:
        try:
            with open(path, "r") as f: return {"content": f.read(), "path": path}
        except Exception as e: return {"error": str(e)}
    def file_write(self, path: str, content: str) -> Dict[str, Any]:
        try:
            with open(path, "w") as f: f.write(content)
            return {"success": True, "path": path}
        except Exception as e: return {"error": str(e)}
    def file_list(self, directory: str) -> Dict[str, Any]:
        import os
        try: return {"entries": os.listdir(directory), "directory": directory}
        except Exception as e: return {"error": str(e)}
