from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))

from domain.tool_policy.internal_context import mark_tool_server_approval_context  # noqa: E402


def fixture_tree(name: str = "inbox_contract") -> dict[str, Any]:
    path = ROOT / "tests" / "fixtures" / "ui_compiler" / f"{name}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def write_pass_package(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    (path / "package.json").write_text(
        json.dumps(
            {
                "scripts": {
                    "lint": "echo lint-passed",
                    "test": "echo test-passed",
                    "build": "echo build-passed"
                }
            }
        ),
        encoding="utf-8",
    )
    return path


def fake_context(workspace: Path) -> dict[str, Any]:
    return mark_tool_server_approval_context(
        {"conversation_workspace_dir": str(workspace), "_ui_compiler_backend": "fake"}
    )


def build_args(run_id: str, *, project_path: str = "project", tree_name: str = "inbox_contract") -> dict[str, Any]:
    return {
        "ui_tree": fixture_tree(tree_name),
        "run_id": run_id,
        "target": {"projectPath": project_path},
        "options": {"viewports": [390], "scenarios": ["default"], "textScales": [1]},
    }
