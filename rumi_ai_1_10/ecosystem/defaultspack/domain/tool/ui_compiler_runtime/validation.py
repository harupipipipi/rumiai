from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

REQUIRED_COMPONENT_FILES = {
    "design-intent.json",
    "component.manifest.json",
    "source/Component.tsx",
    "source/Component.module.css",
    "source/Component.test.tsx",
    "source/Component.stories.tsx",
}
REQUIRED_FIXTURES = {"default", "long", "empty", "loading", "error"}
HEX_COLOR_RE = re.compile(r"#[0-9a-fA-F]{3,8}\\b")


def validate_candidate_bundle(root: Path, contract: dict[str, Any]) -> dict[str, Any]:
    missing = [rel for rel in sorted(REQUIRED_COMPONENT_FILES) if not (root / rel).is_file()]
    fixtures = root / "fixtures"
    missing_fixtures = [state for state in sorted(REQUIRED_FIXTURES) if not (fixtures / f"{state}.json").is_file()]
    manifest = _read_json(root / "component.manifest.json")
    design_intent = _read_json(root / "design-intent.json")
    issues: list[dict[str, Any]] = []
    if missing:
        issues.append({"code": "MISSING_COMPONENT_FILES", "severity": "blocker", "evidence": {"missing": missing}})
    if missing_fixtures:
        issues.append({"code": "MISSING_FIXTURES", "severity": "blocker", "evidence": {"missing": missing_fixtures}})
    if not design_intent:
        issues.append({"code": "MISSING_DESIGN_INTENT", "severity": "blocker", "evidence": {}})
    if _uses_non_token_color(root):
        issues.append({"code": "NON_TOKEN_COLOR", "severity": "blocker", "evidence": {"root": str(root)}})
    required_states = set(_list(contract.get("requiredStates")))
    manifest_states = set(_list(manifest.get("requiredStates")))
    missing_states = sorted(required_states - manifest_states)
    if missing_states:
        issues.append({"code": "REQUIRED_STATE_MISSING", "severity": "blocker", "evidence": {"missing": missing_states}})
    return {
        "status": "fail" if any(issue["severity"] == "blocker" for issue in issues) else "pass",
        "issues": issues,
        "manifest": manifest,
        "designIntent": design_intent,
    }


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _uses_non_token_color(root: Path) -> bool:
    for path in (root / "source").rglob("*"):
        if path.is_file() and path.suffix in {".css", ".tsx", ".ts", ".jsx", ".js"}:
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                continue
            if HEX_COLOR_RE.search(text):
                return True
    return False


def _list(value: Any) -> list[str]:
    return [str(item) for item in value] if isinstance(value, list) else []
