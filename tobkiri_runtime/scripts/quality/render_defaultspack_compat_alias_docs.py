#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
for path in (str(ROOT), str(DEFAULTSPACK_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)

from domain.function_runtime.compat_aliases import render_compat_alias_reference  # noqa: E402


def main() -> int:
    output_path = ROOT / "docs" / "defaultspack-compat-alias-reference.md"
    output_path.write_text(render_compat_alias_reference(), encoding="utf-8")
    print(f"wrote {output_path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
