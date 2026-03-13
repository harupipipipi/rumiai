"""
test_phase_b2a.py - Phase B-2a tests

Tests for _KERNEL_HANDLER_MANIFESTS dict and startup flow changes.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Set

import pytest
import yaml


# ---------------------------------------------------------------------------
# Helpers — import kernel module artefacts without booting the full Kernel
# ---------------------------------------------------------------------------

def _get_expected_handler_keys() -> frozenset:
    """Import _EXPECTED_HANDLER_KEYS from kernel.py."""
    from core_runtime.kernel import _EXPECTED_HANDLER_KEYS
    return _EXPECTED_HANDLER_KEYS


def _get_kernel_handler_manifests() -> Dict[str, Dict[str, Any]]:
    """Import _KERNEL_HANDLER_MANIFESTS from kernel.py."""
    from core_runtime.kernel import _KERNEL_HANDLER_MANIFESTS
    return _KERNEL_HANDLER_MANIFESTS


# Handler key sets — hard-coded because importing the mixin classes would
# pull in heavy dependencies.  These sets are cross-checked with the
# _EXPECTED_HANDLER_KEYS frozenset via test_kernel_handler_manifests_keys_match_expected.

_SYSTEM_HANDLER_KEYS: Set[str] = {
    "kernel:mounts.init",
    "kernel:registry.load",
    "kernel:active_ecosystem.load",
    "kernel:interfaces.publish",
    "kernel:ir.get",
    "kernel:ir.call",
    "kernel:ir.register",
    "kernel:exec_python",
    "kernel:ctx.set",
    "kernel:ctx.get",
    "kernel:ctx.copy",
    "kernel:execute_flow",
    "kernel:save_flow",
    "kernel:load_flows",
    "kernel:flow.compose",
    "kernel:security.init",
    "kernel:docker.check",
    "kernel:approval.init",
    "kernel:approval.scan",
    "kernel:container.init",
    "kernel:privilege.init",
    "kernel:api.init",
    "kernel:container.start_approved",
    "kernel:component.discover",
    "kernel:component.load",
    "kernel:emit",
    "kernel:startup.failed",
    "kernel:vocab.load",
    "kernel:noop",
}

_RUNTIME_HANDLER_KEYS: Set[str] = {
    "kernel:flow.load_all",
    "kernel:flow.execute_by_id",
    "kernel:python_file_call",
    "kernel:modifier.load_all",
    "kernel:modifier.apply",
    "kernel:network.grant",
    "kernel:network.revoke",
    "kernel:network.check",
    "kernel:network.list",
    "kernel:egress_proxy.start",
    "kernel:egress_proxy.stop",
    "kernel:egress_proxy.status",
    "kernel:lib.process_all",
    "kernel:lib.check",
    "kernel:lib.execute",
    "kernel:lib.clear_record",
    "kernel:lib.list_records",
    "kernel:audit.query",
    "kernel:audit.summary",
    "kernel:audit.flush",
    "kernel:vocab.list_groups",
    "kernel:vocab.list_converters",
    "kernel:vocab.summary",
    "kernel:vocab.convert",
    "kernel:shared_dict.resolve",
    "kernel:shared_dict.propose",
    "kernel:shared_dict.explain",
    "kernel:shared_dict.list",
    "kernel:shared_dict.remove",
    "kernel:uds_proxy.init",
    "kernel:uds_proxy.ensure_socket",
    "kernel:uds_proxy.stop",
    "kernel:uds_proxy.stop_all",
    "kernel:uds_proxy.status",
    "kernel:capability_proxy.init",
    "kernel:capability_proxy.status",
    "kernel:capability_proxy.stop_all",
    "kernel:capability.grant",
    "kernel:capability.revoke",
    "kernel:capability.list",
    "kernel:pending.export",
}


def _load_startup_flow() -> Dict[str, Any]:
    """Load 00_startup.flow.yaml and return parsed dict."""
    candidates = [
        Path(__file__).resolve().parent.parent.parent / "flows" / "00_startup.flow.yaml",
        Path("rumi_ai_1_10/flows/00_startup.flow.yaml"),
        Path("flows/00_startup.flow.yaml"),
    ]
    for candidate in candidates:
        if candidate.exists():
            with open(candidate, "r", encoding="utf-8") as f:
                return yaml.safe_load(f)
    pytest.skip("00_startup.flow.yaml not found")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestKernelHandlerManifests:
    """Phase B-2a: _KERNEL_HANDLER_MANIFESTS tests."""

    def test_kernel_handler_manifests_keys_match_expected(self) -> None:
        """_KERNEL_HANDLER_MANIFESTS のキーセットが _EXPECTED_HANDLER_KEYS と完全一致すること"""
        expected = _get_expected_handler_keys()
        manifests = _get_kernel_handler_manifests()
        manifest_keys = set(manifests.keys())

        missing_from_manifests = expected - manifest_keys
        extra_in_manifests = manifest_keys - expected

        assert not missing_from_manifests, (
            f"Keys in _EXPECTED_HANDLER_KEYS but missing from "
            f"_KERNEL_HANDLER_MANIFESTS: {sorted(missing_from_manifests)}"
        )
        assert not extra_in_manifests, (
            f"Keys in _KERNEL_HANDLER_MANIFESTS but not in "
            f"_EXPECTED_HANDLER_KEYS: {sorted(extra_in_manifests)}"
        )

    def test_kernel_handler_manifests_all_have_description(self) -> None:
        """全エントリに非空の description があること"""
        manifests = _get_kernel_handler_manifests()
        for key, manifest in manifests.items():
            assert "description" in manifest, (
                f"Manifest for '{key}' is missing 'description' field"
            )
            assert isinstance(manifest["description"], str), (
                f"Manifest for '{key}' has non-string description: "
                f"{type(manifest['description'])}"
            )
            assert manifest["description"].strip(), (
                f"Manifest for '{key}' has empty description"
            )

    def test_kernel_handler_manifests_all_have_tags(self) -> None:
        """全エントリに非空の tags リストがあること"""
        manifests = _get_kernel_handler_manifests()
        for key, manifest in manifests.items():
            assert "tags" in manifest, (
                f"Manifest for '{key}' is missing 'tags' field"
            )
            assert isinstance(manifest["tags"], list), (
                f"Manifest for '{key}' has non-list tags: "
                f"{type(manifest['tags'])}"
            )
            assert len(manifest["tags"]) > 0, (
                f"Manifest for '{key}' has empty tags list"
            )

    def test_kernel_handler_manifests_tags_include_kernel(self) -> None:
        """全エントリの tags に 'kernel' が含まれること"""
        manifests = _get_kernel_handler_manifests()
        for key, manifest in manifests.items():
            assert "kernel" in manifest["tags"], (
                f"Manifest for '{key}' does not have 'kernel' tag. "
                f"Tags: {manifest['tags']}"
            )

    def test_kernel_handler_manifests_count(self) -> None:
        """エントリ数が 70 であること (system 29 + runtime 41)"""
        manifests = _get_kernel_handler_manifests()
        assert len(manifests) == 70, (
            f"Expected 70 manifests, got {len(manifests)}"
        )

    def test_kernel_handler_manifests_system_tags(self) -> None:
        """system ハンドラの tags に 'system' が含まれること"""
        manifests = _get_kernel_handler_manifests()
        for key in _SYSTEM_HANDLER_KEYS:
            assert key in manifests, (
                f"System handler '{key}' not found in manifests"
            )
            assert "system" in manifests[key]["tags"], (
                f"System handler '{key}' does not have 'system' tag. "
                f"Tags: {manifests[key]['tags']}"
            )

    def test_kernel_handler_manifests_runtime_tags(self) -> None:
        """runtime ハンドラの tags に 'runtime' が含まれること"""
        manifests = _get_kernel_handler_manifests()
        for key in _RUNTIME_HANDLER_KEYS:
            assert key in manifests, (
                f"Runtime handler '{key}' not found in manifests"
            )
            assert "runtime" in manifests[key]["tags"], (
                f"Runtime handler '{key}' does not have 'runtime' tag. "
                f"Tags: {manifests[key]['tags']}"
            )


class TestStartupFlowFunctionRegistryStep:
    """Phase B-2a: 00_startup.flow.yaml function_registry_load step tests."""

    def test_startup_flow_has_function_registry_load_step(self) -> None:
        """00_startup.flow.yaml に function_registry_load step が存在すること"""
        flow = _load_startup_flow()
        steps = flow.get("steps", [])
        step_ids = [s.get("id") for s in steps]
        assert "function_registry_load" in step_ids, (
            f"Step 'function_registry_load' not found in startup flow. "
            f"Found steps: {step_ids}"
        )

    def test_startup_flow_function_registry_load_priority(self) -> None:
        """function_registry_load step の priority が 15 であること"""
        flow = _load_startup_flow()
        steps = flow.get("steps", [])
        target_step = None
        for step in steps:
            if step.get("id") == "function_registry_load":
                target_step = step
                break
        assert target_step is not None, (
            "Step 'function_registry_load' not found in startup flow"
        )
        assert target_step.get("priority") == 15, (
            f"Expected priority 15 for function_registry_load, "
            f"got {target_step.get('priority')}"
        )
        assert target_step.get("phase") == "ecosystem", (
            f"Expected phase 'ecosystem' for function_registry_load, "
            f"got {target_step.get('phase')}"
        )
