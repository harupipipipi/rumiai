from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(DEFAULTSPACK_ROOT) not in sys.path:
    sys.path.insert(0, str(DEFAULTSPACK_ROOT))

pytestmark = pytest.mark.contract


def _authorize(monkeypatch: pytest.MonkeyPatch, events: list[str], mutation_guard):
    from domain.coding import contract_adapter
    from domain.safety.approval import TokenVerification

    def verify(*_args: Any, consume: bool, **_kwargs: Any) -> TokenVerification:
        events.append(f"approval:{consume}")
        return TokenVerification(True, request_id="approval-1")

    def invoke(contract_id: str, operation: str, payload: dict[str, Any]):
        assert contract_id == contract_adapter.HOST_AUTHORITY
        assert operation == "authorize"
        events.append("host-receipt")
        return {"authorized": True, "receipt": "receipt-1"}

    monkeypatch.setattr(contract_adapter.approval, "verify_execution_token", verify)
    monkeypatch.setattr(contract_adapter, "invoke_coding_contract", invoke)
    monkeypatch.setattr(contract_adapter, "_profile_id", lambda: "profile-1")
    return contract_adapter.authorize_legacy_coding_operation(
        legacy_operation="file.write",
        service_pack_id="rumi_file_mutation_pack",
        service_operation="file.write",
        authority="file.write",
        arguments={"path": "src/App.tsx", "content": "new"},
        input_data={
            "workspace_id": "workspace-1",
            "path": "src/App.tsx",
            "content": "new",
            "approval_token": "token",
        },
        context={"principal_id": "agent-1"},
        selected_workspace_id="workspace-1",
        mutation_guard=mutation_guard,
    )


def test_mutation_authority_order_is_precheck_guard_consume_then_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []

    def guard(*_args: Any) -> None:
        events.append("mutation-guard")

    result = _authorize(monkeypatch, events, guard)

    assert result["authorized"] is True
    assert result["approval_request_id"] == "approval-1"
    assert events == [
        "approval:False",
        "mutation-guard",
        "approval:True",
        "host-receipt",
    ]


def test_mutation_guard_denial_does_not_consume_token_or_mint_host_receipt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[str] = []

    def guard(*_args: Any) -> dict[str, Any]:
        events.append("mutation-guard")
        return {
            "reason": "adaptive_lease_held",
            "code": "ADAPTIVE_LEASE_HELD",
            "message": "lease is held",
        }

    result = _authorize(monkeypatch, events, guard)

    assert result == {
        "authorized": False,
        "reason": "adaptive_lease_held",
        "code": "ADAPTIVE_LEASE_HELD",
        "message": "lease is held",
    }
    assert events == ["approval:False", "mutation-guard"]


def test_every_legacy_mutation_entrypoint_uses_canonical_guard() -> None:
    block_root = DEFAULTSPACK_ROOT / "blocks" / "coding"
    callers = {
        "file_create.py": 1,
        "file_delete.py": 1,
        "file_patch.py": 1,
        "file_write.py": 1,
        "git_branch.py": 1,
        "git_commit.py": 1,
        "git_push.py": 1,
        "terminal_exec.py": 1,
        "terminal_stream.py": 1,
        "sandbox_common.py": 2,
        "workspace/_contract.py": 1,
    }

    for relative_path, expected_calls in callers.items():
        source = (block_root / relative_path).read_text(encoding="utf-8")
        assert source.count("authorize_legacy_coding_operation(") == expected_calls
        assert source.count("mutation_guard=canonical_mutation_guard") == expected_calls
