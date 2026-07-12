"""Compatibility shim for the canonical defaultspack UDS transport."""

from __future__ import annotations

import sys
from pathlib import Path

RUMI_ROOT = Path(__file__).resolve().parents[3]
DEFAULTSPACK_ROOT = RUMI_ROOT / "ecosystem" / "defaultspack"
for path in (str(RUMI_ROOT), str(DEFAULTSPACK_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)

from ecosystem.defaultspack.transport.uds import (  # noqa: F401,E402
    DefaultsUdsTransport,
    _ID_INJECT_MAP,
    _ROUTE_MAP,
    _match_route,
)

__all__ = ["DefaultsUdsTransport", "_ID_INJECT_MAP", "_ROUTE_MAP", "_match_route"]
