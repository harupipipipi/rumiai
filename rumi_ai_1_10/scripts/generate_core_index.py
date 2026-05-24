#!/usr/bin/env python3
"""Generate core-index.stable.json for a core bundle."""

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
    core_bundle_signature_payload,
    index_signature_payload,
    sign_ed25519,
    signature_entry,
)
from core_runtime.update.versioning import read_pyproject_version


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--runtime-dir", type=Path, required=True)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--allow-unsigned", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    version = read_pyproject_version(args.runtime_dir / "pyproject.toml") or "0.0.0"
    key_id = os.environ.get("RUMI_CORE_ED25519_KEY_ID") or os.environ.get("RUMI_UPDATE_ED25519_KEY_ID", "")
    private_key = os.environ.get("RUMI_CORE_ED25519_PRIVATE_KEY_B64") or os.environ.get(
        "RUMI_UPDATE_ED25519_PRIVATE_KEY_B64", ""
    )
    if not args.allow_unsigned and not (key_id and private_key):
        raise SystemExit(
            "RUMI_UPDATE_ED25519_KEY_ID and RUMI_UPDATE_ED25519_PRIVATE_KEY_B64 "
            "are required for core indexes"
        )
    digest = sha256_file(args.bundle)
    bundle_signature = sign_ed25519(
        core_bundle_signature_payload(version, digest),
        key_id,
        private_key,
    ) if key_id and private_key else ""
    payload = {
        "schema": "rumi.core_index.v1",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "latest": version,
        "versions": {
            version: {
                "url": f"{args.base_url.rstrip('/')}/{args.bundle.name}",
                "sha256": digest,
                "signature_scheme": "ed25519" if bundle_signature else "",
                "key_id": key_id if bundle_signature else "",
                "signature": bundle_signature,
            }
        },
    }
    if key_id and private_key:
        payload["signatures"] = [
            signature_entry(sign_ed25519(index_signature_payload(payload), key_id, private_key))
        ]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
