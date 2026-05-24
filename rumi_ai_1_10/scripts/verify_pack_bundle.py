#!/usr/bin/env python3
"""Verify a .rumi-pack bundle."""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core_runtime.update.download import safe_extract_zip, sha256_file
from core_runtime.update.manifest import validate_extracted_pack


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path)
    parser.add_argument("--pack-id", required=True)
    parser.add_argument("--core-version", default="1.10.0")
    parser.add_argument("--viewer-version", default="0.1.0")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    with tempfile.TemporaryDirectory(prefix="rumi-pack-verify-") as tmp:
        extracted = Path(tmp) / "extracted"
        safe_extract_zip(args.bundle, extracted)
        validate_extracted_pack(
            extracted,
            target_pack_id=args.pack_id,
            core_version=args.core_version,
            viewer_version=args.viewer_version,
        )
    print(f"OK {args.bundle} sha256={sha256_file(args.bundle)}")


if __name__ == "__main__":
    main()
