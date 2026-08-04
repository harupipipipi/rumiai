from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path

import pytest

from core_runtime.capability_binding_registration import (
    register_pack_binding_handlers,
)
from core_runtime.global_contract_dispatch import (
    GlobalContractUnavailable,
    invoke_global_contract,
)
from core_runtime.interface_registry import InterfaceRegistry
from core_runtime.profile_graph_builder import build_startup_profile_graph_response
from core_runtime.resolved_profile import (
    ResolvedProfile,
    ResolutionInput,
    resolution_input_from_startup_profile,
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
CONVERSATION_PACK = "rumi_conversation_store_pack"
CONVERSATION_CONTRACT = "rumi.resource.conversation.v1"
FILE_INSPECT_CONTRACT = "rumi.service.file.inspect.v1"


class _ApprovedPacks:
    def get_approval(self, _pack_id: str) -> object:
        return object()

    def is_pack_approved_and_verified(self, _pack_id: str) -> tuple[bool, str]:
        return True, "verified fixture"

    def get_verified_pack_trust(
        self,
        pack_ids: tuple[str, ...],
    ) -> dict[str, str]:
        return {pack_id: "local" for pack_id in pack_ids}


def _resolved_file_inspect_profile() -> ResolvedProfile:
    effective = (
        "defaultspack",
        FILE_INSPECT_PACK,
        WORKSPACE_PACK,
        AUTHORITY_PACK,
        CONVERSATION_PACK,
    )
    return resolve_profile(
        ResolutionInput(
            profile_id="file-inspect-qa",
            profile_revision="gui-r1",
            platform="test",
            policy_revision="policy-r1",
            lockfile_revision=None,
            requested_pack_ids=("defaultspack", FILE_INSPECT_PACK),
            authorized_pack_ids=effective,
            healthy_pack_ids=effective,
            policy_capabilities=(
                "file.inspect",
                "conversation.read",
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
    default_profile = manager._default_startup_profile(reloaded["catalog"])
    assert default_profile is not None
    assert CONVERSATION_PACK in default_profile["packs"]
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

    provisional = resolve_profile(
        resolution_input_from_startup_profile(profile),
        ecosystem_dir=ECOSYSTEM,
    )
    assert CONVERSATION_PACK in provisional.selected_pack_ids
    approved = tuple(provisional.selected_pack_ids)
    resolution_input = resolution_input_from_startup_profile(
        profile,
        verified_pack_trust={pack_id: "local" for pack_id in approved},
    )
    plan = resolve_profile(
        replace(
            resolution_input,
            authorized_pack_ids=approved,
            healthy_pack_ids=approved,
        ),
        ecosystem_dir=ECOSYSTEM,
    )
    providers = [
        provider
        for provider in plan.providers
        if provider.contract_id == CONVERSATION_CONTRACT
    ]
    assert len(providers) == 1
    assert providers[0].source_pack_id == CONVERSATION_PACK


def test_resolved_profile_activates_and_invokes_read_only_file_inspect(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    plan = _resolved_file_inspect_profile()
    assert plan.effective_pack_set == (
        "defaultspack",
        CONVERSATION_PACK,
        FILE_INSPECT_PACK,
        AUTHORITY_PACK,
        WORKSPACE_PACK,
    )
    assert not plan.diagnostics

    token = activate_resolved_profile(plan)
    try:
        with pytest.raises(
            GlobalContractUnavailable,
            match="expected one active provider.*found 0",
        ):
            invoke_global_contract(
                InterfaceRegistry(),
                CONVERSATION_CONTRACT,
                "list",
                {"profile_id": "file-inspect-qa"},
            )
    finally:
        restore_resolved_profile(token)

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
    (tmp_path / "outside.txt").write_text("outside workspace\n", encoding="utf-8")
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
        conversation = invoke_global_contract(
            registry,
            CONVERSATION_CONTRACT,
            "list",
            {"profile_id": "file-inspect-qa"},
        )
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
        with pytest.raises(PermissionError):
            invoke_global_contract(
                registry,
                FILE_INSPECT_CONTRACT,
                "read",
                {
                    "profile_id": "file-inspect-qa",
                    "workspace_id": "qa-workspace",
                    "path": "../outside.txt",
                    "_workspace_binding": binding,
                },
            )
        with pytest.raises(PermissionError, match="Host workspace binding"):
            invoke_global_contract(
                registry,
                FILE_INSPECT_CONTRACT,
                "read",
                {
                    "profile_id": "file-inspect-qa",
                    "workspace_id": "qa-workspace",
                    "path": "hello.txt",
                    "_workspace_binding": {
                        **binding,
                        "workspace_id": "other-workspace",
                    },
                },
            )

        provider_key = f"global_contract.provider.{CONVERSATION_CONTRACT}"
        conversation_provider = registry.get(provider_key, strategy="all")[0]
        registry.register(provider_key, conversation_provider)
        with pytest.raises(
            GlobalContractUnavailable,
            match="expected one active provider.*found 2",
        ):
            invoke_global_contract(
                registry,
                CONVERSATION_CONTRACT,
                "list",
                {"profile_id": "file-inspect-qa"},
            )
    finally:
        restore_resolved_profile(token)

    assert conversation["profile_id"] == "file-inspect-qa"
    assert conversation["conversations"] == []
    assert result["content"] == "hello from profile\n"
    assert result["read_only"] is True
