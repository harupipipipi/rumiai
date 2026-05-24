#!/usr/bin/env python3
"""Collect target-specific Tauri updater payloads for GitHub Releases."""

from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle-dir", type=Path, required=True)
    parser.add_argument("--target", required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.bundle_dir.is_dir():
        raise SystemExit(f"bundle dir not found: {args.bundle_dir}")
    candidates = _signed_payloads(args.bundle_dir)
    if not candidates:
        raise SystemExit(f"no signed updater payloads found under {args.bundle_dir}")
    payload, signature = _select_payload(args.target, candidates)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    asset_name = f"viewer-updater-{args.target}-{_safe_asset_name(payload.name)}"
    asset_path = args.out_dir / asset_name
    sig_path = args.out_dir / f"{asset_name}.sig"
    shutil.copy2(payload, asset_path)
    shutil.copy2(signature, sig_path)
    fragment = {
        "target": args.target,
        "platform": _platform_key(args.target),
        "asset": asset_name,
        "signature_asset": sig_path.name,
        "signature": sig_path.read_text(encoding="utf-8").strip(),
        "source_payload": str(payload),
    }
    (args.out_dir / f"viewer-updater-{args.target}.json").write_text(
        json.dumps(fragment, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _signed_payloads(bundle_dir: Path) -> list[tuple[Path, Path]]:
    payloads: list[tuple[Path, Path]] = []
    for sig in sorted(bundle_dir.rglob("*.sig")):
        payload = Path(str(sig)[:-4])
        if payload.is_file():
            payloads.append((payload, sig))
    return payloads


def _select_payload(target: str, candidates: list[tuple[Path, Path]]) -> tuple[Path, Path]:
    def score(item: tuple[Path, Path]) -> int:
        payload, _sig = item
        name = payload.name
        if "apple-darwin" in target:
            return 100 if name.endswith(".app.tar.gz") else 10 if name.endswith(".tar.gz") else 0
        if "windows" in target:
            return 100 if name.endswith(".zip") else 10 if name.endswith(".msi") else 0
        if "linux" in target:
            return 100 if name.endswith(".AppImage.tar.gz") else 90 if name.endswith(".tar.gz") else 0
        return 1

    selected = max(candidates, key=score)
    if score(selected) <= 0:
        raise SystemExit(f"no updater payload matched target {target}")
    return selected


def _platform_key(target: str) -> str:
    mapping = {
        "aarch64-apple-darwin": "darwin-aarch64",
        "x86_64-apple-darwin": "darwin-x86_64",
        "x86_64-pc-windows-msvc": "windows-x86_64",
        "x86_64-unknown-linux-gnu": "linux-x86_64",
    }
    try:
        return mapping[target]
    except KeyError as exc:
        raise SystemExit(f"unsupported updater target: {target}") from exc


def _safe_asset_name(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", name)


if __name__ == "__main__":
    main()
