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
from core_runtime.update.trust import (
    index_signature_payload,
    pack_bundle_signature_payload,
    sign_ed25519,
    signature_entry,
)


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
    key_id = os.environ.get("RUMI_PACK_ED25519_KEY_ID") or os.environ.get("RUMI_UPDATE_ED25519_KEY_ID", "")
    private_key = os.environ.get("RUMI_PACK_ED25519_PRIVATE_KEY_B64") or os.environ.get(
        "RUMI_UPDATE_ED25519_PRIVATE_KEY_B64", ""
    )
    if args.channel == "stable" and not args.allow_unsigned and not (key_id and private_key):
        raise SystemExit(
            "RUMI_UPDATE_ED25519_KEY_ID and RUMI_UPDATE_ED25519_PRIVATE_KEY_B64 "
            "are required for stable pack indexes"
        )
    packs: dict[str, dict] = {}
    for artifact in args.artifact:
        name = artifact.name.removesuffix(".rumi-pack")
        pack_id, _, version = name.rpartition("-")
        if not pack_id or not version:
            raise SystemExit(f"artifact name must be <pack_id>-<version>.rumi-pack: {artifact}")
        entry = packs.setdefault(pack_id, {"latest": version, "versions": {}})
        digest = sha256_file(artifact)
        entry["latest"] = version
        bundle_signature = sign_ed25519(
            pack_bundle_signature_payload(digest),
            key_id,
            private_key,
        ) if key_id and private_key else ""
        entry["versions"][version] = {
            "url": f"{args.base_url.rstrip('/')}/{artifact.name}",
            "sha256": digest,
            "signature_scheme": "ed25519" if bundle_signature else "",
            "key_id": key_id if bundle_signature else "",
            "signature": bundle_signature,
            "min_core_version": "1.10.0",
            "max_core_version": "<2.0.0",
        }
    payload = {
        "schema": "rumi.pack_index.v1",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "channel": args.channel,
        "packs": packs,
    }
    if key_id and private_key:
        payload["signatures"] = [
            signature_entry(sign_ed25519(index_signature_payload(payload), key_id, private_key))
        ]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
