from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULTSPACK = ROOT / "ecosystem" / "defaultspack"


def _read(relative_path: str) -> str:
    return (DEFAULTSPACK / relative_path).read_text(encoding="utf-8")


def test_company_routes_use_neutral_team_workspace_copy() -> None:
    routes = json.loads((DEFAULTSPACK / "routes.json").read_text(encoding="utf-8"))
    company_routes = [
        route
        for route in routes["routes"]
        if route.get("flow_id") == "company_workspace"
    ]

    assert company_routes
    descriptions = [str(route.get("description") or "").lower() for route in company_routes]
    assert all("company" not in description for description in descriptions)
    assert all("mimo" not in description for description in descriptions)
    assert any("team workspace" in description for description in descriptions)


def test_team_workspace_docs_define_model_and_profile_ownership() -> None:
    docs = "\n".join(
        _read(path)
        for path in (
            "docs/company_workspace.md",
            "docs/multi-agent.md",
            "docs/remote_task_gateway.md",
        )
    )

    assert "model-independent" in docs
    assert "rumi_operations_company_pack" in docs
    assert "MiMo Coding Company" in docs
    assert "OpenCode Zen" in docs
    assert "MiMo-only company" in docs


def test_shared_runtime_copy_does_not_brand_company_workspace_as_mimo() -> None:
    shared_runtime_files = (
        "blocks/agent/multi_execute.py",
        "blocks/agent/multi_message.py",
        "blocks/company/__init__.py",
        "domain/company/__init__.py",
        "domain/company/message_router.py",
        "domain/company/models.py",
        "domain/company/runtime_store.py",
        "domain/company/store.py",
        "domain/company/supervisor.py",
        "domain/remote/task_gateway.py",
    )

    shared_copy = "\n".join(_read(path) for path in shared_runtime_files).lower()
    assert "mimo" not in shared_copy
    assert "company workspace" not in shared_copy
    assert "company runtime" not in shared_copy


def test_shared_scheduled_approval_copy_does_not_imply_a_mimo_only_runtime() -> None:
    scheduled_approval = _read("domain/tool/scheduled_approval.py")
    approval = _read("domain/safety/approval.py")

    assert "MiMo scheduled approvals" not in scheduled_approval
    assert "MiMo scheduled auto-approval" not in approval
