from __future__ import annotations

import sys
from pathlib import Path

PACK_ROOT = Path(__file__).resolve().parents[2]
if str(PACK_ROOT) not in sys.path:
    sys.path.insert(0, str(PACK_ROOT))

from surface_helpers import image_export


def run(context: object, args: object) -> dict[str, object]:
    return image_export(
        args if isinstance(args, dict) else {},
        context if isinstance(context, dict) else {},
    )
