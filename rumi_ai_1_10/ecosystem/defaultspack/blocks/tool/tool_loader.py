from __future__ import annotations

from pathlib import Path

from backend_core.ecosystem import compat


class ToolLoader:
    """Compatibility shim when the defaultspack blocks shadow the legacy tool package."""

    def __init__(self, tools_dir: str | Path | None = None) -> None:
        resolved = Path(tools_dir) if tools_dir is not None else compat.get_tools_dir()
        self.tools_dir = resolved
        self.tools_dir.mkdir(parents=True, exist_ok=True)
