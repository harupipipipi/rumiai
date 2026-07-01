from __future__ import annotations

import sys
from pathlib import Path

PACK_ROOT = Path(__file__).resolve().parents[2]
RUMI_ROOT = PACK_ROOT.parents[1]
for path in (str(PACK_ROOT), str(RUMI_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)

from domain.local_hook import delete_local_hook


def run(context, args):
    del context
    return delete_local_hook(args if isinstance(args, dict) else {})
