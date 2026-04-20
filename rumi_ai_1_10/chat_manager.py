from __future__ import annotations

from pathlib import Path

from backend_core.ecosystem import compat


class ChatManager:
    """Legacy shim that resolves chats_dir through ecosystem compat."""

    def __init__(self, chats_dir: str | Path | None = None) -> None:
        resolved = Path(chats_dir) if chats_dir is not None else compat.get_chats_dir()
        self.chats_dir = resolved
        self.chats_dir.mkdir(parents=True, exist_ok=True)
