from __future__ import annotations

from pathlib import Path
import sys


_DEFAULTSPACK_ROOT = Path(__file__).resolve().parents[3] / "defaultspack"
if str(_DEFAULTSPACK_ROOT) not in sys.path:
    sys.path.insert(0, str(_DEFAULTSPACK_ROOT))

from domain.chat.message_converter import convert_to_standard  # noqa: E402,F401


__all__ = ["convert_to_standard"]
