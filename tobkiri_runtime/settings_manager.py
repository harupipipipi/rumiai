from __future__ import annotations

from pathlib import Path

from backend_core.ecosystem import compat


class SettingsManager:
    """Legacy shim for user settings storage."""

    def __init__(self, user_data_dir: str | Path | None = None) -> None:
        resolved = Path(user_data_dir) if user_data_dir is not None else compat.get_user_data_dir()
        self.user_data_dir = resolved
        self.user_data_dir.mkdir(parents=True, exist_ok=True)
