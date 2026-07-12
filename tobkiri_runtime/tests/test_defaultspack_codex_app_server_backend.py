from __future__ import annotations

import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


def test_codex_app_server_is_coding_backend_not_provider():
    from domain.ai_client.providers import get_provider_catalog_map
    from domain.components.registry import DomainComponentRegistry, build_domain_component_roots

    registry = DomainComponentRegistry(build_domain_component_roots(DEFAULTSPACK_ROOT))
    backend = registry.get("coding_backends", "codex-app-server")

    assert backend is not None
    assert backend.kind == "coding_backend"
    assert backend.as_dict()["policy"]["do_not_treat_as_llm_provider"] is True
    assert "codex-app-server" not in get_provider_catalog_map()


def test_codex_app_server_workspace_boundary_and_server_approval(tmp_path):
    from blocks.coding.codex_app_server import (
        CodexAppServerBackend,
        ServerApprovalRequiredError,
        WorkspaceBoundaryError,
    )

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    inside = workspace / "notes.txt"
    inside.write_text("ok", encoding="utf-8")
    outside = tmp_path / "outside.txt"
    outside.write_text("no", encoding="utf-8")

    backend = CodexAppServerBackend()
    session = backend.create_session(str(workspace), profile={"name": "test"})

    with pytest.raises(ServerApprovalRequiredError):
        backend.validate_action(
            session,
            "file.write",
            target_path=inside,
            client_supplied_approved=True,
        )

    backend.validate_action(
        session,
        "file.write",
        target_path=inside,
        context={"server_approvals": {"file.write": True}},
        client_supplied_approved=False,
    )

    with pytest.raises(WorkspaceBoundaryError):
        backend.validate_action(
            session,
            "file.write",
            target_path=outside,
            context={"server_approvals": {"file.write": True}},
        )
