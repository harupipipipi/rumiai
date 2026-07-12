#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from copy import deepcopy
from pathlib import Path

OLD_TO_NEW = {
    "model": "models_api",
    "api": "models_api",
    "provider": "models_api",
    "tools": "tools_mcp",
    "tool": "tools_mcp",
    "mcp": "tools_mcp",
    "computer_use": "computer_automation",
    "computer": "computer_automation",
    "browser": "computer_automation",
    "theme": "workspace_ui",
    "layout": "workspace_ui",
    "ui": "workspace_ui",
    "pack": "packs_extensions",
    "extension": "packs_extensions",
    "debug": "diagnostics",
}

DISPLAY_NAME_FIXES = {
    "mimo": "Mimo model preset",
    "computer_use_gradient": "Automation visual indicator",
    "openrouter_auto": "OpenRouter auto routing",
}

VISUAL_SETTING_KEYS = {"computer_use_gradient", "automation_gradient", "indicator_gradient"}


def migrate(raw: dict) -> dict:
    migrated = deepcopy(raw)
    settings = migrated.get("settings", migrated)
    migrated.setdefault("migration", {})["settings_control_center"] = {"version": 1, "applied": True}

    for key, value in list(settings.items()):
        if not isinstance(value, dict):
            continue
        old_category = value.get("category") or value.get("section")
        if old_category in OLD_TO_NEW:
            value["section"] = OLD_TO_NEW[old_category]
            value.pop("category", None)

        label = value.get("label") or value.get("title") or value.get("display_name")
        if isinstance(label, str) and label in DISPLAY_NAME_FIXES:
            value["display_name"] = DISPLAY_NAME_FIXES[label]
            value["legacy_label"] = label
            value.pop("label", None)

        if key in VISUAL_SETTING_KEYS:
            value["section"] = "workspace_ui"
            value.setdefault("display_name", DISPLAY_NAME_FIXES.get(key, "Automation visual indicator"))

        if key in {"computer_use", "computer_control"}:
            value["section"] = "computer_automation"
            value.setdefault("display_name", "Computer Control")

    migrated["settings"] = settings
    return migrated


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    raw = json.loads(args.input.read_text(encoding="utf-8"))
    migrated = migrate(raw)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(migrated, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote migrated settings to {args.output}")


if __name__ == "__main__":
    main()
