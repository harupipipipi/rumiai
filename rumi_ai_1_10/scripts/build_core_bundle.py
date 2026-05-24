#!/usr/bin/env python3
"""Build a conservative core update zip."""

from __future__ import annotations

import argparse
import zipfile
from pathlib import Path

INCLUDE = ("app.py", "core_runtime", "pyproject.toml", "requirements.txt")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("runtime_dir", type=Path)
    parser.add_argument("output", type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    root = args.runtime_dir.resolve()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(args.output, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for rel in INCLUDE:
            path = root / rel
            if path.is_file():
                zf.write(path, rel)
            elif path.is_dir():
                for item in sorted(path.rglob("*")):
                    if item.is_file() and not item.is_symlink() and "__pycache__" not in item.parts:
                        zf.write(item, item.relative_to(root).as_posix())


if __name__ == "__main__":
    main()
