#!/usr/bin/env python3
"""Build a conservative core update zip."""

from __future__ import annotations

import argparse
import fnmatch
import zipfile
from pathlib import Path

INCLUDE = ("app.py", "backend_core", "core_runtime", "pyproject.toml", "requirements.txt")
PROTECTED_PATTERNS = (
    "user_data",
    "user_data/**",
    "packs",
    "packs/**",
    "pack_state",
    "pack_state/**",
    "logs",
    "logs/**",
    "settings",
    "settings/**",
    "update_state",
    "update_state/**",
    "ecosystem/defaultspack",
    "ecosystem/defaultspack/**",
    "pack_seeds",
    "pack_seeds/**",
    "secrets",
    "secrets/**",
    ".env",
    ".env.*",
    "*.local.*",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("runtime_dir", type=Path)
    parser.add_argument("output", type=Path)
    return parser.parse_args()


def _is_protected(rel: str) -> bool:
    parts = Path(rel).parts
    if any(part == "secrets" for part in parts):
        return True
    if parts and (parts[-1] == ".env" or parts[-1].startswith(".env.")):
        return True
    for pattern in PROTECTED_PATTERNS:
        if fnmatch.fnmatch(rel, pattern):
            return True
        if pattern.endswith("/**") and rel == pattern[:-3]:
            return True
    return False


def _should_include_file(path: Path, root: Path) -> bool:
    if path.is_symlink() or "__pycache__" in path.parts:
        return False
    rel = path.relative_to(root).as_posix()
    return not _is_protected(rel)


def build_core_bundle(runtime_dir: Path, output: Path) -> None:
    root = runtime_dir.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for rel in INCLUDE:
            path = root / rel
            if path.is_file():
                if _should_include_file(path, root):
                    zf.write(path, rel)
            elif path.is_dir():
                for item in sorted(path.rglob("*")):
                    if item.is_file() and _should_include_file(item, root):
                        zf.write(item, item.relative_to(root).as_posix())


def main() -> None:
    args = parse_args()
    build_core_bundle(args.runtime_dir, args.output)


if __name__ == "__main__":
    main()
