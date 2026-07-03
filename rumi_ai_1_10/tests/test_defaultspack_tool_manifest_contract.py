from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parent.parent
TOOL_ROOT = ROOT / "ecosystem" / "defaultspack" / "tools"

pytestmark = pytest.mark.contract


def _parameters(tool_id: str) -> dict:
    manifest = json.loads((TOOL_ROOT / tool_id / "manifest.json").read_text(encoding="utf-8"))
    return manifest["config"]["schema"]["parameters"]


def _validate(schema: dict, payload: dict) -> list[str] | None:
    try:
        import jsonschema
    except ImportError:
        return None
    validator = jsonschema.Draft7Validator(schema)
    return [error.message for error in validator.iter_errors(payload)]


def _requires_any_of(schema: dict, *keys: str) -> bool:
    required_sets = [
        set(item.get("required", []))
        for item in schema.get("anyOf", [])
        if isinstance(item, dict)
    ]
    return all({key} in required_sets for key in keys)


def test_execute_tool_manifests_require_runtime_inputs():
    sandbox = _parameters("sandbox_exec")
    python = _parameters("python_exec")
    node = _parameters("node_exec")

    assert sandbox["additionalProperties"] is False
    assert python["additionalProperties"] is False
    assert node["additionalProperties"] is False
    assert _requires_any_of(sandbox, "argv", "command")
    assert _requires_any_of(python, "code", "script_path")
    assert _requires_any_of(node, "code", "script_path")
    assert sandbox["properties"]["command"]["oneOf"][0]["type"] == "string"
    assert sandbox["properties"]["command"]["oneOf"][1]["type"] == "array"

    validation_cases: list[tuple[dict[str, Any], dict[str, Any], bool]] = [
        (sandbox, {}, False),
        (python, {}, False),
        (node, {}, False),
        (sandbox, {"argv": ["pwd"]}, True),
        (sandbox, {"command": "pwd"}, True),
        (python, {"code": "print('ok')"}, True),
        (python, {"script_path": "scripts/ok.py"}, True),
        (node, {"code": "console.log('ok')"}, True),
        (node, {"script_path": "scripts/ok.js"}, True),
        (sandbox, {"argv": ["pwd"], "approved": True}, False),
        (python, {"code": "print('ok')", "approved": True}, False),
    ]
    for schema, payload, should_pass in validation_cases:
        errors = _validate(schema, payload)
        if errors is None:
            continue
        assert (errors == []) is should_pass
