"""Runtime port resolution helpers."""

from __future__ import annotations

import os
from typing import Any


DEFAULT_RUNTIME_PORT = 8765


def resolve_runtime_port(default: int = DEFAULT_RUNTIME_PORT, fallback: Any = None) -> int:
    """Resolve the Rumi runtime API port with safe fallback parsing."""
    for candidate in (os.environ.get("RUMI_PORT"), fallback, default):
        if candidate is None or candidate == "":
            continue
        try:
            port = int(candidate)
        except (TypeError, ValueError):
            continue
        if 0 < port <= 65535:
            return port
    return default
