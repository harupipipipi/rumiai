#!/usr/bin/env python3
"""Generate core-index.stable.json for a core bundle."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core_runtime.update.download import sha256_file
from core_runtime.update.versioning import read_pyproject_version


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--runtime-dir", type=Path, required=True)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    version = read_pyproject_version(args.runtime_dir / "pyproject.toml") or "0.0.0"
    payload = {
        "schema": "rumi.core_index.v1",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "latest": version,
        "versions": {
            version: {
                "url": f"{args.base_url.rstrip('/')}/{args.bundle.name}",
                "sha256": sha256_file(args.bundle),
            }
        },
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
