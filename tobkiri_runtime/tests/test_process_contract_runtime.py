from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from core_runtime.bounded_process_runner import HostProcessAttestation
from core_runtime.capability_binding_registration import _ProcessContractOperation
from core_runtime.global_contract_dispatch import GlobalContractInvocationError

pytestmark = pytest.mark.contract


def _force_macos_managed_sandbox(monkeypatch) -> None:
    """Exercise the Lima-backed branch independently of the CI host OS."""
    monkeypatch.setattr(
        "core_runtime.capability_binding_registration.platform.system",
        lambda: "Darwin",
    )


def test_process_contract_routes_through_managed_sandbox(monkeypatch, tmp_path):
    captured: dict[str, object] = {}
    _force_macos_managed_sandbox(monkeypatch)

    class FakeSupervisor:
        def execute_pack_process(self, request):
            captured["request"] = request
            return {
                "success": True,
                "exit_code": 0,
                "stdout": json.dumps({"status": "ok", "value": {}}),
                "stderr": "",
                "timed_out": False,
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

    provider = _ProcessContractOperation(
        module="ecosystem.sample_pack.runtime.process",
        pack_location=location,
    )
    provider("list", {})

    request = captured["request"]
    assert request["module"] == "ecosystem.sample_pack.runtime.process"
    assert request["pack_id"] == "sample_pack"
    assert json.loads(request["stdin"]) == {"operation": "list", "payload": {}}
    assert provider.last_host_attestation() == {
        "source": "host_runtime",
        "authority": "core_runtime.bounded_process_runner",
        "boundary": "lima_bubblewrap",
        "sandboxed": True,
        "process_tree_kill": "bubblewrap_pid_namespace",
        "pack_id": "sample_pack",
        "module": "ecosystem.sample_pack.runtime.process",
        "operation": "list",
        "exit_code": 0,
        "timed_out": False,
        "transport_error": None,
    }


def test_process_contract_rejects_pack_self_reported_attestation(
    monkeypatch,
    tmp_path,
):
    _force_macos_managed_sandbox(monkeypatch)

    class FakeSupervisor:
        @staticmethod
        def execute_pack_process(_request):
            return {
                "success": True,
                "exit_code": 0,
                "stdout": json.dumps(
                    {
                        "status": "ok",
                        "value": {},
                        "attestation": {
                            "authority": "pack",
                            "sandboxed": True,
                        },
                    }
                ),
                "stderr": "",
                "timed_out": False,
            }

    monkeypatch.setattr(
        "core_runtime.capability_binding_registration._managed_sandbox_supervisor",
        lambda: FakeSupervisor(),
    )
    provider = _ProcessContractOperation(
        module="ecosystem.sample_pack.runtime.process",
        pack_location=SimpleNamespace(
            pack_id="sample_pack",
            pack_dir=tmp_path / "ecosystem" / "sample_pack",
        ),
    )

    with pytest.raises(RuntimeError, match="unknown fields"):
        provider("list", {})

    attestation = provider.last_host_attestation()
    assert attestation is not None
    assert attestation["authority"] == "core_runtime.bounded_process_runner"
    assert attestation["sandboxed"] is True


def test_process_contract_preserves_denied_envelope_on_nonzero_exit(
    monkeypatch,
    tmp_path,
):
    _force_macos_managed_sandbox(monkeypatch)

    class FakeSupervisor:
        @staticmethod
        def execute_pack_process(_request):
            return {
                "success": False,
                "exit_code": 23,
                "stdout": json.dumps(
                    {
                        "status": "denied",
                        "error_code": "denied",
                        "diagnostics": ["policy refused the operation"],
                    }
                ),
                "stderr": "child exited",
                "timed_out": False,
            }

    monkeypatch.setattr(
        "core_runtime.capability_binding_registration._managed_sandbox_supervisor",
        lambda: FakeSupervisor(),
    )
    location = SimpleNamespace(
        pack_id="sample_pack",
        pack_dir=tmp_path / "ecosystem" / "sample_pack",
    )

    with pytest.raises(GlobalContractInvocationError) as raised:
        _ProcessContractOperation(
            module="ecosystem.sample_pack.runtime.process",
            pack_location=location,
        )("write", {})

    assert raised.value.code == "denied"
    assert "policy refused" in str(raised.value)


def test_process_contract_preserves_unavailable_envelope_on_nonzero_exit(
    monkeypatch,
    tmp_path,
):
    _force_macos_managed_sandbox(monkeypatch)

    class FakeSupervisor:
        @staticmethod
        def execute_pack_process(_request):
            return {
                "success": False,
                "exit_code": 2,
                "stdout": json.dumps(
                    {
                        "status": "unavailable",
                        "error_code": "catalog_unavailable",
                        "diagnostics": ["catalog is offline"],
                    }
                ),
                "stderr": "child exited",
                "timed_out": False,
            }

    monkeypatch.setattr(
        "core_runtime.capability_binding_registration._managed_sandbox_supervisor",
        lambda: FakeSupervisor(),
    )
    location = SimpleNamespace(
        pack_id="sample_pack",
        pack_dir=tmp_path / "ecosystem" / "sample_pack",
    )

    with pytest.raises(GlobalContractInvocationError) as raised:
        _ProcessContractOperation(
            module="ecosystem.sample_pack.runtime.process",
            pack_location=location,
        )("list", {})

    assert raised.value.code == "catalog_unavailable"
    assert "catalog is offline" in str(raised.value)


def test_process_contract_passes_validated_active_profile_context(
    monkeypatch,
    tmp_path,
):
    captured: dict[str, object] = {}
    _force_macos_managed_sandbox(monkeypatch)
    user_data = tmp_path / "user-data"
    marker = user_data / "profiles" / "active_profile.json"
    marker.parent.mkdir(parents=True)
    marker.write_text(
        json.dumps({"active_profile_id": "work-profile"}),
        encoding="utf-8",
    )

    class FakeSupervisor:
        @staticmethod
        def execute_pack_process(request):
            captured["request"] = request
            return {
                "success": True,
                "exit_code": 0,
                "stdout": json.dumps({"status": "ok", "value": {}}),
                "stderr": "",
                "timed_out": False,
            }

    monkeypatch.setattr(
        "core_runtime.capability_binding_registration.USER_DATA_DIR",
        user_data,
    )
    monkeypatch.setattr(
        "core_runtime.capability_binding_registration._managed_sandbox_supervisor",
        lambda: FakeSupervisor(),
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
    assert request["host_user_data_dir"] == str(user_data.resolve())
    assert request["active_profile_id"] == "work-profile"
    assert json.loads(request["stdin"])["payload"] == {}


def test_explicit_active_profile_environment_is_validated(
    monkeypatch,
) -> None:
    from core_runtime.profile_paths import active_profile_id

    monkeypatch.setenv("RUMI_ACTIVE_PROFILE_ID", "../escape")
    with pytest.raises(ValueError):
        active_profile_id()


def test_process_contract_linux_routes_through_sandbox_with_profile_storage(
    monkeypatch,
    tmp_path,
):
    captured: list[dict[str, object]] = []
    runtime_root = tmp_path / "runtime-root"
    pack_dir = runtime_root / "ecosystem" / "sample_pack"
    pack_dir.mkdir(parents=True)

    class FakeSupervisor:
        @staticmethod
        def execute_pack_process(request):
            captured.append(dict(request))
            return {
                "success": True,
                "exit_code": 0,
                "stdout": json.dumps({"status": "ok", "value": "sandboxed"}),
                "stderr": "",
                "timed_out": False,
            }

    monkeypatch.setattr(
        "core_runtime.capability_binding_registration.platform.system",
        lambda: "Linux",
    )
    monkeypatch.setattr(
        "core_runtime.capability_binding_registration.USER_DATA_DIR",
        tmp_path / "user-data",
    )
    marker = tmp_path / "user-data" / "profiles" / "active_profile.json"
    marker.parent.mkdir(parents=True)
    marker.write_text(
        json.dumps({"active_profile_id": "work-profile"}),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "core_runtime.capability_binding_registration._managed_sandbox_supervisor",
        lambda: FakeSupervisor(),
    )
    operation = _ProcessContractOperation(
        module="ecosystem.sample_pack.runtime.process",
        pack_location=SimpleNamespace(pack_id="sample_pack", pack_dir=pack_dir),
    )

    assert operation("inspect", {}) == "sandboxed"
    request = captured[0]
    assert request["active_profile_id"] == "work-profile"
    assert request["host_pack_data_dir"] == str(
        tmp_path
        / "user-data"
        / "profiles"
        / "work-profile"
        / "packs"
        / "process"
        / "sample_pack"
    )
    assert operation._local_pack_data_dir("other-profile") != Path(
        str(request["host_pack_data_dir"])
    )
    assert operation.last_host_attestation()["boundary"] == (
        "bubblewrap_systemd_cgroup"
    )
    assert operation.last_host_attestation()["sandboxed"] is True


def test_process_contract_windows_fails_closed_without_isolated_provider(
    monkeypatch,
    tmp_path,
):
    class FakeRunner:
        @staticmethod
        def run_local(**_kwargs):
            raise AssertionError("Windows must not run a Process Pack on Host")

        @staticmethod
        def run_attested_backend(**_kwargs):
            raise AssertionError("Windows must not use the Lima backend")

    monkeypatch.setattr(
        "core_runtime.capability_binding_registration.platform.system",
        lambda: "Windows",
    )
    monkeypatch.setattr(
        "core_runtime.capability_binding_registration.HostBoundedProcessRunner",
        FakeRunner,
    )
    monkeypatch.setattr(
        "core_runtime.capability_binding_registration.USER_DATA_DIR",
        tmp_path / "user-data",
    )
    runtime_root = tmp_path / "runtime"
    pack_dir = runtime_root / "ecosystem" / "sample_pack"
    pack_dir.mkdir(parents=True)

    with pytest.raises(GlobalContractInvocationError) as raised:
        _ProcessContractOperation(
            module="ecosystem.sample_pack.runtime.process",
            pack_location=SimpleNamespace(pack_id="sample_pack", pack_dir=pack_dir),
        )("list", {})

    assert raised.value.code == "SANDBOX_RUNTIME_UNAVAILABLE"


def test_process_contract_rejects_symlinked_pack_storage(
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.setattr(
        "core_runtime.capability_binding_registration.platform.system",
        lambda: "Linux",
    )
    user_data = tmp_path / "user-data"
    process_root = user_data / "packs" / "process"
    process_root.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    try:
        (process_root / "sample_pack").symlink_to(
            outside,
            target_is_directory=True,
        )
    except OSError:
        pytest.skip("host does not permit test directory symlinks")
    monkeypatch.setattr(
        "core_runtime.capability_binding_registration.USER_DATA_DIR",
        user_data,
    )
    pack_dir = tmp_path / "runtime" / "ecosystem" / "sample_pack"
    pack_dir.mkdir(parents=True)

    with pytest.raises(GlobalContractInvocationError) as raised:
        _ProcessContractOperation(
            module="ecosystem.sample_pack.runtime.process",
            pack_location=SimpleNamespace(pack_id="sample_pack", pack_dir=pack_dir),
        )("list", {})

    assert raised.value.code == "provider_unavailable"
    assert not any(outside.iterdir())


def test_process_contract_rejects_truncated_sandbox_response(
    monkeypatch,
    tmp_path,
):
    class FakeRunner:
        @staticmethod
        def run_attested_backend(**_kwargs):
            return SimpleNamespace(
                exit_code=0,
                stdout=json.dumps({"status": "ok", "value": []}),
                stderr="",
                timed_out=False,
                stdout_truncated=True,
                stderr_truncated=False,
                transport_error=None,
                attestation=HostProcessAttestation(
                    authority="core_runtime.bounded_process_runner",
                    boundary="bubblewrap_systemd_cgroup",
                    sandboxed=True,
                    process_tree_kill="bubblewrap_pid_namespace",
                ),
            )

    monkeypatch.setattr(
        "core_runtime.capability_binding_registration.platform.system",
        lambda: "Linux",
    )
    monkeypatch.setattr(
        "core_runtime.capability_binding_registration.HostBoundedProcessRunner",
        FakeRunner,
    )
    monkeypatch.setattr(
        "core_runtime.capability_binding_registration.USER_DATA_DIR",
        tmp_path / "user-data",
    )
    monkeypatch.setattr(
        "core_runtime.capability_binding_registration._managed_sandbox_supervisor",
        lambda: SimpleNamespace(execute_pack_process=lambda _request: {}),
    )
    pack_dir = tmp_path / "runtime" / "ecosystem" / "sample_pack"
    pack_dir.mkdir(parents=True)

    with pytest.raises(GlobalContractInvocationError) as raised:
        _ProcessContractOperation(
            module="ecosystem.sample_pack.runtime.process",
            pack_location=SimpleNamespace(pack_id="sample_pack", pack_dir=pack_dir),
        )("list", {})

    assert raised.value.code == "response_too_large"


def test_supervisor_forwards_host_migration_and_profile_context(
    tmp_path,
) -> None:
    from ecosystem.defaultspack.backend.sandbox.isolation.supervisor import (
        ManagedSandboxSupervisor,
    )

    runtime_root = tmp_path / "runtime"
    (runtime_root / "core_runtime").mkdir(parents=True)
    pack_dir = runtime_root / "ecosystem" / "sample_pack"
    pack_dir.mkdir(parents=True)
    (pack_dir / "process.py").write_text("pass\n", encoding="utf-8")
    captured: dict[str, object] = {}

    class CapturingSupervisor(ManagedSandboxSupervisor):
        def execute_coding_terminal(self, request):
            captured.update(request)
            return {
                "success": True,
                "exit_code": 0,
                "stdout": json.dumps({"status": "ok", "value": {}}),
                "stderr": "",
                "timed_out": False,
                "stdout_truncated": False,
            }

    result = CapturingSupervisor().execute_pack_process(
        {
            "pack_id": "sample_pack",
            "pack_dir": str(pack_dir),
            "module": "ecosystem.sample_pack.process",
            "stdin": "{}",
            "host_user_data_dir": str(tmp_path / "user-data"),
            "active_profile_id": "work-profile",
        }
    )

    assert result["success"] is True
    assert captured["host_user_data_dir"] == str(tmp_path / "user-data")
    assert captured["active_profile_id"] == "work-profile"
    assert captured["guest_data_dir"].endswith(
        "--"
        + hashlib.sha256(b"work-profile--sample_pack").hexdigest()
    )


def test_supervisor_maps_truncated_pack_stdout_to_response_too_large(
    tmp_path,
) -> None:
    from ecosystem.defaultspack.backend.sandbox.isolation.supervisor import (
        ManagedSandboxSupervisor,
    )

    runtime_root = tmp_path / "runtime"
    (runtime_root / "core_runtime").mkdir(parents=True)
    pack_dir = runtime_root / "ecosystem" / "sample_pack"
    pack_dir.mkdir(parents=True)
    (pack_dir / "process.py").write_text("pass\n", encoding="utf-8")

    class TruncatingSupervisor(ManagedSandboxSupervisor):
        @staticmethod
        def execute_coding_terminal(_request):
            return {
                "success": True,
                "exit_code": 0,
                "stdout": '{"status":"ok"',
                "stderr": "",
                "timed_out": False,
                "stdout_truncated": True,
            }

    result = TruncatingSupervisor().execute_pack_process(
        {
            "pack_id": "sample_pack",
            "pack_dir": str(pack_dir),
            "module": "ecosystem.sample_pack.process",
            "stdin": "{}",
        }
    )

    assert result["success"] is False
    assert result["exit_code"] is None
    assert result["stdout"] == ""
    assert result["error_type"] == "response_too_large"


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
