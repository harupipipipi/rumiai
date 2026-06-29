#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

VALID_SECTIONS = {
    "quick_setup",
    "models_api",
    "accounts_connections",
    "tools_mcp",
    "computer_automation",
    "workspace_ui",
    "profiles",
    "privacy_security",
    "packs_extensions",
    "advanced",
    "diagnostics",
}

BLOCKED_RAW_LABELS = {"mimo", "computer_use_gradient", "openrouter_auto"}


def label_text(value) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return value.get("en") or value.get("ja") or next(iter(value.values()), "")
    return ""


def validate_settings_manifest(path: Path) -> list[str]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    errors: list[str] = []
    if raw.get("schema") != "rumi.settings.v1":
        errors.append(f"{path}: expected schema rumi.settings.v1")

    for contribution in raw.get("contributions", []):
        cid = contribution.get("id", "<missing id>")
        title = label_text(contribution.get("title"))
        if not contribution.get("owner"):
            errors.append(f"{path}:{cid}: missing owner")
        if not title:
            errors.append(f"{path}:{cid}: missing title")
        if title.lower() in BLOCKED_RAW_LABELS:
            errors.append(f"{path}:{cid}: raw/internal label '{title}' is blocked")
        if contribution.get("section") not in VALID_SECTIONS:
            errors.append(f"{path}:{cid}: unknown section {contribution.get('section')}")
        if "priority" not in contribution:
            errors.append(f"{path}:{cid}: missing priority")
        if contribution.get("frequency") == "debug" and contribution.get("section") != "diagnostics":
            errors.append(f"{path}:{cid}: debug setting outside Diagnostics")
        if contribution.get("audience") == "developer" and contribution.get("section") not in {"advanced", "diagnostics"}:
            errors.append(f"{path}:{cid}: developer setting outside Advanced/Diagnostics")
    return errors


def validate_provider_manifest(path: Path) -> list[str]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    errors: list[str] = []
    if raw.get("schema") != "rumi.connection.provider.v1":
        errors.append(f"{path}: expected schema rumi.connection.provider.v1")
    if not raw.get("provider_id"):
        errors.append(f"{path}: missing provider_id")
    if not label_text(raw.get("display_name")):
        errors.append(f"{path}: missing display_name")
    settings = raw.get("settings", {})
    if settings.get("section") and settings["section"] not in VALID_SECTIONS:
        errors.append(f"{path}: provider references unknown settings section")
    if "priority" not in settings and "priority" not in raw:
        errors.append(f"{path}: provider missing priority")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    args = parser.parse_args()

    errors: list[str] = []
    for path in args.root.rglob("*.settings.json"):
        errors.extend(validate_settings_manifest(path))
    for path in args.root.rglob("*.connection.json"):
        errors.extend(validate_provider_manifest(path))

    if errors:
        print("Manifest validation failed:", file=sys.stderr)
        print("\n".join(errors), file=sys.stderr)
        return 1
    print("Manifest validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
