from __future__ import annotations

from pathlib import Path

from backend_core.ecosystem import compat

# DEPRECATED: legacy import compatibility only.
# New code must use defaultspack functions, agents, memory, or extensions.


class SupporterLoader:
    """Legacy shim for supporter directory loading."""

    def __init__(self, supporter_dir: str | Path | None = None) -> None:
        resolved = Path(supporter_dir) if supporter_dir is not None else compat.get_supporters_dir()
        self.supporter_dir = resolved
        self.supporter_dir.mkdir(parents=True, exist_ok=True)
