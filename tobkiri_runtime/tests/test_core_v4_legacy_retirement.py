"""Physical retirement checks for the pre-v4 execution authorities."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


RUNTIME = Path(__file__).resolve().parents[1]
RETIRED_MODULES = {
    "binding_handlers.py",
    "capability_binding_registration.py",
    "capability_executor.py",
    "capability_graph_compiler.py",
    "capability_graph_loader.py",
    "component_lifecycle.py",
    "ecosystem_nodes.py",
    "function_registry.py",
    "interface_registry.py",
    "kernel.py",
    "kernel_context_builder.py",
    "kernel_core.py",
    "kernel_handlers_system.py",
    "permission_manager.py",
    "profile_loader.py",
    "startup_capability_bridge.py",
}


def test_retired_execution_authority_modules_are_physically_absent() -> None:
    """Legacy executable authorities cannot be imported from production."""
    core = RUNTIME / "core_runtime"
    assert not {path.name for path in core.iterdir()} & RETIRED_MODULES


def test_manifest_authority_catalog_classifies_all_direct_pack_roots() -> None:
    """The finite catalog owns all 141 roots, including both v4-only Packs."""
    ecosystem = RUNTIME / "ecosystem"
    roots = {
        path.name
        for path in ecosystem.iterdir()
        if path.is_dir()
        and path.name != "setup_pack"
        and not path.name.startswith(".")
    }
    catalog = json.loads(
        (RUNTIME / "schemas" / "manifest_authority.v1.json").read_text(
            encoding="utf-8"
        )
    )["packs"]
    assert set(catalog) == roots
    assert len(catalog) == 141
    assert catalog["defaults"] == "modern-only"
    assert catalog["defaultspack"] == "modern-only"


def test_top_level_runtime_does_not_import_legacy_composition() -> None:
    """A clean process reaches no retired authority through ``tobkiri``."""
    code = """
import json
import sys
import tobkiri.runtime
blocked = {
    'app',
    'backend_core.ecosystem.registry',
    'core_runtime.capability_executor',
    'core_runtime.function_registry',
    'core_runtime.interface_registry',
}
print(json.dumps(sorted(blocked.intersection(sys.modules))))
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=RUNTIME,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.stdout.strip() == "[]"


def test_runtime_projection_module_is_metadata_only() -> None:
    """Only the offline script retains one-way projection implementation."""
    from core_runtime import manifest_projection

    assert manifest_projection.PROJECTION_RUNTIME_EXECUTABLE is False
    assert (
        manifest_projection.PROJECTION_OWNER
        == "scripts/offline_legacy_projection.py"
    )
    assert manifest_projection.PROJECTION_SOURCE == "rumi.pack.v3.json"
    assert not hasattr(
        manifest_projection, "generate_legacy_ecosystem_projection"
    )
    offline = (RUNTIME / "scripts" / "offline_legacy_projection.py").read_text(
        encoding="utf-8"
    )
    assert 'PROJECTION_SOURCE = "rumi.pack.v3.json"' in offline
    assert 'RUNTIME_EXECUTABLE = False' in offline
    assert "def generate_legacy_ecosystem_projection(" in offline
