#!/usr/bin/env python3
"""Build a .rumi-pack zip with checksums."""

from __future__ import annotations

import argparse
import json
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core_runtime.update.download import sha256_file


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pack_dir", type=Path)
    parser.add_argument("output", type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    pack_dir = args.pack_dir.resolve()
    output = args.output.resolve()
    manifest = {}
    files = [
        path for path in sorted(pack_dir.rglob("*"))
        if path.is_file() and not path.is_symlink() and "node_modules" not in path.parts
    ]
    for path in files:
        rel = path.relative_to(pack_dir).as_posix()
        if rel in {"manifest.json", "manifest.sha256", "signature", "signature.sig"}:
            continue
        manifest[rel] = sha256_file(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in files:
            rel = path.relative_to(pack_dir).as_posix()
            if rel in {"manifest.json", "manifest.sha256", "signature", "signature.sig"}:
                continue
            zf.write(path, rel)
        zf.writestr(
            "manifest.json",
            json.dumps({"schema": "rumi.pack_manifest.v1", "files": manifest}, indent=2, sort_keys=True) + "\n",
        )


if __name__ == "__main__":
    main()
