#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))

from domain.templates.contracts import run_template_contracts  # noqa: E402
from domain.templates.projectors import build_template_catalog  # noqa: E402


def main() -> int:
    catalog = build_template_catalog(defaultspack_root=DEFAULTSPACK_ROOT)
    result = run_template_contracts(catalog, defaultspack_root=DEFAULTSPACK_ROOT)
    summary = result.to_dict()
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
