#!/usr/bin/env python3
"""Generate pack-index.stable.json for .rumi-pack artifacts."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core_runtime.update.download import sha256_file
from core_runtime.update.trust import sign_hmac


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact", action="append", type=Path, required=True)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--channel", default="stable")
    parser.add_argument("--allow-unsigned", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    key_id = os.environ.get("RUMI_PACK_HMAC_KEY_ID", "")
    secret = os.environ.get("RUMI_PACK_HMAC_SECRET", "")
    if args.channel == "stable" and not args.allow_unsigned and not (key_id and secret):
        raise SystemExit("RUMI_PACK_HMAC_KEY_ID and RUMI_PACK_HMAC_SECRET are required for stable pack indexes")
    packs: dict[str, dict] = {}
    for artifact in args.artifact:
        name = artifact.name.removesuffix(".rumi-pack")
        pack_id, _, version = name.rpartition("-")
        if not pack_id or not version:
            raise SystemExit(f"artifact name must be <pack_id>-<version>.rumi-pack: {artifact}")
        entry = packs.setdefault(pack_id, {"latest": version, "versions": {}})
        digest = sha256_file(artifact)
        entry["latest"] = version
        entry["versions"][version] = {
            "url": f"{args.base_url.rstrip('/')}/{artifact.name}",
            "sha256": digest,
            "signature": sign_hmac(digest, key_id, secret) if key_id and secret else "",
            "min_core_version": "1.10.0",
            "max_core_version": "<2.0.0",
        }
    payload = {
        "schema": "rumi.pack_index.v1",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "channel": args.channel,
        "packs": packs,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
