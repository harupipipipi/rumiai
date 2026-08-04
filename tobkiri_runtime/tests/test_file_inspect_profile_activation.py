from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from core_runtime.capability_binding_registration import (
    register_pack_binding_handlers,
)
from core_runtime.global_contract_dispatch import invoke_global_contract
from core_runtime.interface_registry import InterfaceRegistry
from core_runtime.profile_graph_builder import build_startup_profile_graph_response
from core_runtime.resolved_profile import (
    ResolvedProfile,
    ResolutionInput,
    resolve_profile,
)
from core_runtime.resolved_profile_scope import (
    activate_resolved_profile,
    restore_resolved_profile,
)
from core_runtime.startup_profiles import StartupProfileManager
from ecosystem.rumi_workspace_mount_pack.runtime.mounts import (
    WorkspaceMountStore,
)


ECOSYSTEM = Path(__file__).resolve().parents[1] / "ecosystem"
FILE_INSPECT_PACK = "rumi_file_inspect_pack"
WORKSPACE_PACK = "rumi_workspace_mount_pack"
AUTHORITY_PACK = "rumi_host_authority_bridge_pack"
FILE_INSPECT_CONTRACT = "rumi.service.file.inspect.v1"


class _ApprovedPacks:
    def get_approval(self, _pack_id: str) -> object:
        return object()

    def is_pack_approved_and_verified(self, _pack_id: str) -> tuple[bool, str]:
        return True, "verified fixture"


def _resolved_file_inspect_profile() -> ResolvedProfile:
    effective = (FILE_INSPECT_PACK, WORKSPACE_PACK, AUTHORITY_PACK)
    return resolve_profile(
        ResolutionInput(
            profile_id="file-inspect-qa",
            profile_revision="gui-r1",
            platform="test",
            policy_revision="policy-r1",
            lockfile_revision=None,
            requested_pack_ids=(FILE_INSPECT_PACK,),
            authorized_pack_ids=effective,
            healthy_pack_ids=effective,
            policy_capabilities=(
                "file.inspect",
                "workspace.metadata.read",
                "workspace.mount.manage",
                "host.authority.consume",
            ),
            verified_pack_trust=tuple((pack_id, "local") for pack_id in effective),
        ),
        ecosystem_dir=ECOSYSTEM,
    )


def test_gui_profile_add_activate_and_reload_keeps_pack(tmp_path: Path) -> None:
    storage_path = tmp_path / "settings" / "startup_profiles.json"
    manager = StartupProfileManager(
        storage_path=storage_path,
        ecosystem_dir=str(ECOSYSTEM),
        approval_manager=_ApprovedPacks(),
        seed_default_profile=False,
    )
    created = manager.create_profile(
        {
            "profile_id": "file-inspect-qa",
            "name": "File Inspect QA",
            "base_pack": "defaultspack",
            "graph_id": "defaultspack.startup",
        }
    )
    assert created.get("created") is True

    added = manager.add_pack_to_profile("file-inspect-qa", FILE_INSPECT_PACK)
    activated = manager.activate_profile("file-inspect-qa")
    assert added["profile"]["packs"] == ["defaultspack", FILE_INSPECT_PACK]
    assert activated["activated"] is True

    reloaded = StartupProfileManager(
        storage_path=storage_path,
        ecosystem_dir=str(ECOSYSTEM),
        approval_manager=_ApprovedPacks(),
        seed_default_profile=False,
    ).list_profiles_payload()
    profile = next(
        item
        for item in reloaded["profiles"]
        if item["profile_id"] == "file-inspect-qa"
    )
    assert reloaded["active_profile_id"] == "file-inspect-qa"
    assert profile["packs"] == ["defaultspack", FILE_INSPECT_PACK]
    candidate = next(
        node
        for pack in reloaded["catalog"]["packs"]
        if pack["pack_id"] == FILE_INSPECT_PACK
        for node in pack["nodes"]
        if node.get("metadata", {}).get("contract_id") == FILE_INSPECT_CONTRACT
    )
    assert candidate["metadata"]["data_only_projection"] is True

    graph = build_startup_profile_graph_response(
        profile,
        startup_catalog=reloaded["catalog"],
        profile_workspace_manager=manager.profile_workspace_manager,
        ecosystem_dir=str(ECOSYSTEM),
    )
    assert any(
        item["id"]
        == "rumi_file_inspect_pack.contract.file-inspect.service"
        for item in graph["available"]["capability_nodes"]
    )


def test_resolved_profile_activates_and_invokes_read_only_file_inspect(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    plan = _resolved_file_inspect_profile()
    assert plan.effective_pack_set == (
        FILE_INSPECT_PACK,
        AUTHORITY_PACK,
        WORKSPACE_PACK,
    )
    assert not plan.diagnostics

    monkeypatch.setenv("RUMI_ALLOW_HOST_EXECUTION", "true")
    import ecosystem.rumi_workspace_mount_pack.runtime.mounts as mounts

    monkeypatch.setattr(mounts, "USER_DATA_DIR", tmp_path / "user_data")
    registry = InterfaceRegistry()
    registration = register_pack_binding_handlers(
        interface_registry=registry,
        approval_manager=_ApprovedPacks(),
        ecosystem_dir=str(ECOSYSTEM),
        effective_pack_ids=plan.effective_pack_set,
    )
    assert registration.ok is True
    assert registration.skipped == []
    assert set(registration.registered) == set(plan.effective_pack_set)

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "hello.txt").write_text("hello from profile\n", encoding="utf-8")
    store = WorkspaceMountStore("file-inspect-qa")
    store.mount("qa-workspace", str(workspace), expected_revision=0)
    mount = store.get("qa-workspace")
    assert mount is not None
    root_stat = workspace.stat()
    binding = {
        "workspace_id": "qa-workspace",
        "access": "read_only",
        "mount_revision": str(mount["updated_at"]),
        "canonical_root": str(workspace.resolve()),
        "root_st_dev": int(root_stat.st_dev),
        "root_st_ino": int(root_stat.st_ino),
    }
    binding["root_identity"] = hashlib.sha256(
        json.dumps(
            binding,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()

    token = activate_resolved_profile(plan)
    try:
        result = invoke_global_contract(
            registry,
            FILE_INSPECT_CONTRACT,
            "read",
            {
                "profile_id": "file-inspect-qa",
                "workspace_id": "qa-workspace",
                "path": "hello.txt",
                "_workspace_binding": binding,
            },
        )
    finally:
        restore_resolved_profile(token)

    assert result["content"] == "hello from profile\n"
    assert result["read_only"] is True
