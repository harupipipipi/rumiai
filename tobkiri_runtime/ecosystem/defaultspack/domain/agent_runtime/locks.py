from __future__ import annotations

import os
from pathlib import Path

from core_runtime.runtime_locks import NamedLock

from .run_store import default_runtime_dir


def session_lock(session_key: str, *, timeout_ms: int = 60000, stale_after_seconds: float = 600) -> NamedLock:
    root = Path(os.environ.get("RUMI_DEFAULTSPACK_AGENT_LOCK_DIR") or default_runtime_dir() / "locks")
    return NamedLock(
        root,
        session_key,
        owner=f"defaultspack:{os.getpid()}",
        timeout_ms=timeout_ms,
        stale_after_seconds=stale_after_seconds,
        reentrant=True,
    )
