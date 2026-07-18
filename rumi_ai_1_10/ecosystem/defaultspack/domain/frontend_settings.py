"""Canonical location for Defaultspack frontend settings.

The debug harness can isolate a Defaultspack run by setting
``RUMI_DEFAULTSPACK_FRONTEND_SETTINGS_PATH``.  Runtime consumers must use the
same location so a selected model is not read from the shared production
settings while the rest of the run is isolated.
"""

from __future__ import annotations

import os
from pathlib import Path


FRONTEND_SETTINGS_PATH_ENV = "RUMI_DEFAULTSPACK_FRONTEND_SETTINGS_PATH"


def frontend_settings_path(pack_root: Path | None = None) -> Path:
    """Return the environment override or the production-default path.

    ``pack_root`` is deliberately only used for the fallback.  Callers which
    receive the canonical pack root (for example frontend registries) must
    still honour the per-run override.
    """

    override = os.environ.get(FRONTEND_SETTINGS_PATH_ENV, "").strip()
    if override:
        return Path(override).expanduser().resolve(strict=False)
    root = pack_root or Path(__file__).resolve().parents[1]
    return root / "user_data" / "shared" / "frontend_settings.json"
