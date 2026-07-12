from __future__ import annotations

import sys
from pathlib import Path


PACK_ROOT = Path(__file__).resolve().parents[1]
ECOSYSTEM_DIR = PACK_ROOT.parent
DEFAULTSPACK_ROOT = ECOSYSTEM_DIR / "defaultspack"
RUMI_ROOT = ECOSYSTEM_DIR.parent

for path in (RUMI_ROOT, PACK_ROOT, DEFAULTSPACK_ROOT):
    text = str(path)
    if text not in sys.path:
        sys.path.insert(0, text)


def tool_result(result="", *, widget=None, is_error=False):
    return {"result": result, "is_error": bool(is_error), "widget": widget}
