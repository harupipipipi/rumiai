"""Compatibility shim for the canonical defaultspack CLI transport."""

from __future__ import annotations

import sys
from pathlib import Path

RUMI_ROOT = Path(__file__).resolve().parents[3]
DEFAULTSPACK_ROOT = RUMI_ROOT / "ecosystem" / "defaultspack"
for path in (str(RUMI_ROOT), str(DEFAULTSPACK_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)

from ecosystem.defaultspack.transport.cli import *  # noqa: F401,F403,E402
