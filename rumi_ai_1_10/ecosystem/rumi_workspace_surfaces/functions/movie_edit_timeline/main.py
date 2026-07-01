from __future__ import annotations

import sys
from pathlib import Path

PACK_ROOT = Path(__file__).resolve().parents[2]
if str(PACK_ROOT) not in sys.path:
    sys.path.insert(0, str(PACK_ROOT))

from surface_helpers import movie_edit_timeline


def run(context, args):
    return movie_edit_timeline(args if isinstance(args, dict) else {}, context if isinstance(context, dict) else {})
