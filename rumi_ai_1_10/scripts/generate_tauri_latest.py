#!/usr/bin/env python3
"""Generate the Tauri updater latest.json from collected target fragments."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fragments-dir", type=Path, required=True)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--notes", default="")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    platforms = {}
    base_url = args.base_url.rstrip("/")
    for fragment_path in sorted(args.fragments_dir.glob("viewer-updater-*.json")):
        fragment = json.loads(fragment_path.read_text(encoding="utf-8"))
        platform = str(fragment.get("platform") or "")
        asset = str(fragment.get("asset") or "")
        signature = str(fragment.get("signature") or "")
        if not platform or not asset or not signature:
            raise SystemExit(f"invalid updater fragment: {fragment_path}")
        asset_path = args.fragments_dir / asset
        sig_path = args.fragments_dir / str(fragment.get("signature_asset") or "")
        if not asset_path.is_file() or not sig_path.is_file():
            raise SystemExit(f"fragment references missing updater artifact: {fragment_path}")
        platforms[platform] = {
            "signature": signature,
            "url": f"{base_url}/{asset}",
        }
    if not platforms:
        raise SystemExit(f"no updater fragments found in {args.fragments_dir}")
    payload = {
        "version": args.version,
        "notes": args.notes,
        "pub_date": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "platforms": platforms,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
