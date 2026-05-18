"""Compatibility shim for the canonical defaultspack HTTP transport."""

from __future__ import annotations

import sys
from pathlib import Path

RUMI_ROOT = Path(__file__).resolve().parents[3]
DEFAULTSPACK_ROOT = RUMI_ROOT / "ecosystem" / "defaultspack"
for path in (str(RUMI_ROOT), str(DEFAULTSPACK_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)

from ecosystem.defaultspack.transport.http import (  # noqa: F401,E402
    DefaultsHttpServer,
    _RequestHandler,
    start_http_server,
)

__all__ = ["DefaultsHttpServer", "_RequestHandler", "start_http_server"]
