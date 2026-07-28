from __future__ import annotations

import json
import os
from types import SimpleNamespace

import pytest

from core_runtime.capability_binding_registration import _ProcessContractOperation

pytestmark = pytest.mark.contract


def test_process_contract_routes_through_managed_sandbox(monkeypatch, tmp_path):
    captured: dict[str, object] = {}

    class FakeSupervisor:
        def execute_pack_process(self, request):
            captured["request"] = request
            return {
                "success": True,
                "stdout": json.dumps({"status": "ok", "value": {}}),
            }

    def fake_supervisor():
        return FakeSupervisor()

    monkeypatch.setattr(
        "core_runtime.capability_binding_registration._managed_sandbox_supervisor",
        fake_supervisor,
    )
    location = SimpleNamespace(
        pack_id="sample_pack",
        pack_dir=tmp_path / "ecosystem" / "sample_pack",
    )

    _ProcessContractOperation(
        module="ecosystem.sample_pack.runtime.process",
        pack_location=location,
    )("list", {})

    request = captured["request"]
    assert request["module"] == "ecosystem.sample_pack.runtime.process"
    assert request["pack_id"] == "sample_pack"
    assert json.loads(request["stdin"]) == {"operation": "list", "payload": {}}


@pytest.mark.skipif(
    os.environ.get("RUMI_RUN_LIMA_INTEGRATION") != "1",
    reason="real Lima sandbox integration is opt-in",
)
def test_process_contract_real_child_keeps_bundle_tree_bytecode_free(
    monkeypatch,
    tmp_path,
):
    runtime_root = tmp_path / "runtime-root"
    core_runtime = runtime_root / "core_runtime"
    core_runtime.mkdir(parents=True)
    (core_runtime / "__init__.py").write_text("", encoding="utf-8")
    pack_dir = runtime_root / "ecosystem" / "sample_pack"
    module_dir = pack_dir / "runtime"
    module_dir.mkdir(parents=True)
    for package_dir in (runtime_root / "ecosystem", pack_dir, module_dir):
        (package_dir / "__init__.py").write_text("", encoding="utf-8")
    (module_dir / "sibling.py").write_text("VALUE = 'loaded'\n", encoding="utf-8")
    (module_dir / "process.py").write_text(
        "import json, os, sys\n"
        "from .sibling import VALUE\n"
        "request = json.loads(sys.stdin.read())\n"
        "print(json.dumps({'status': 'ok', 'value': {\n"
        "    'value': VALUE,\n"
        "    'dont_write_bytecode': sys.dont_write_bytecode,\n"
        "    'ignore_environment': sys.flags.ignore_environment,\n"
        "    'no_user_site': sys.flags.no_user_site,\n"
        "    'user_data': os.environ.get('RUMI_USER_DATA'),\n"
        "    'secret_visible': 'PROCESS_CONTRACT_TEST_SECRET' in os.environ,\n"
        "}}))\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("PROCESS_CONTRACT_TEST_SECRET", "must-not-leak")

    result = _ProcessContractOperation(
        module="ecosystem.sample_pack.runtime.process",
        pack_location=SimpleNamespace(pack_id="sample_pack", pack_dir=pack_dir),
    )("inspect", {})

    assert result == {
        "value": "loaded",
        "dont_write_bytecode": True,
        "ignore_environment": 1,
        "no_user_site": 1,
        "user_data": "/data",
        "secret_visible": False,
    }
    assert not list(runtime_root.rglob("__pycache__"))
    assert not list(runtime_root.rglob("*.pyc"))


@pytest.mark.skipif(
    os.environ.get("RUMI_RUN_LIMA_INTEGRATION") != "1",
    reason="real Lima sandbox integration is opt-in",
)
def test_real_shipped_process_pack_runs_with_curated_kernel_code() -> None:
    from core_runtime.paths import discover_pack_locations

    location = next(
        item
        for item in discover_pack_locations()
        if item.pack_id == "rumi_model_registry_pack"
    )
    result = _ProcessContractOperation(
        module="ecosystem.rumi_model_registry_pack.runtime.process",
        pack_location=location,
    )("list", {"profile_id": "sandbox-integration-read"})

    assert result == {
        "version": "rumi.model-registry.store.v1",
        "profile_id": "sandbox-integration-read",
        "revision": 0,
        "profiles": [],
        "aliases": {},
    }
