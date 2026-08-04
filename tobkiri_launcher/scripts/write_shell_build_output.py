#!/usr/bin/env python3
"""Write the exact, post-build Shell v4 output contract consumed by packaging."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    """Validate explicit build facts and write a deterministic manifest."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-id", required=True)
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument(
        "--platform", required=True, choices=("macos", "linux", "windows")
    )
    parser.add_argument("--architecture", required=True, choices=("arm64", "x86_64"))
    parser.add_argument("--source-identity", required=True)
    parser.add_argument("--source-revision", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    artifact = args.artifact.expanduser().resolve()
    if args.artifact.is_symlink() or not artifact.exists():
        raise SystemExit(f"build artifact is missing or symlinked: {args.artifact}")
    for name in ("artifact_id", "source_identity", "source_revision"):
        if not getattr(args, name).strip():
            raise SystemExit(f"{name} must not be empty")
    value = {
        "schema": "io.tobkiri.shell.build-output.v4",
        "artifact_id": args.artifact_id,
        "artifact_path": str(artifact),
        "platform": args.platform,
        "architecture": args.architecture,
        "build_profile": "release",
        "source_identity": args.source_identity,
        "source_revision": args.source_revision,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
