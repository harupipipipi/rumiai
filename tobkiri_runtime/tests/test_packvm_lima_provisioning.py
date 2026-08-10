from __future__ import annotations

import json
import hashlib
import hmac
import multiprocessing
import os
import platform
import shutil
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from ecosystem.defaultspack.backend.sandbox.isolation.lima_runtime import (
    PACKVM_ARTIFACT_STORAGE_BUDGET_BYTES,
    PACKVM_BACKEND_ID,
    PACKVM_DISK_SIZE_BYTES,
    PACKVM_GUEST_FREE_RESERVE_BYTES,
    PACKVM_HOST_STORAGE_RESERVE_BYTES,
    PACKVM_LIMA_INSTANCE,
    PACKVM_PINNED_IMAGE_VIRTUAL_SIZE_BYTES,
    PackVMLimaProvisioner,
    PackVMForeignInstanceError,
    PackVMMutationConflict,
    PackVMProcessError,
    PackVMProvisioningRequest,
    PackVMResponseReconciliationRequired,
)
from ecosystem.defaultspack.backend.sandbox.isolation.resources import (
    packvm_guest_runner,
)
from core_runtime.packvm_lifecycle_v4 import PackVMLifecycleV4


MACHINE_ID = "0123456789abcdef0123456789abcdef"


class FakeLima:
    def __init__(self, command_path: Path, instance_dir: Path) -> None:
        self.command_path = command_path
        self.instance_dir = instance_dir
        self.exists = False
        self.running = False
        self.runner_digest = ""
        self.machine_id = MACHINE_ID
        self.config_marker = "original"
        self.commands: list[tuple[str, ...]] = []
        self.fail_install = False
        self.fail_start_after_create = False
        self.fail_delete = False
        self.timeout_start = False
        self.block_delete = False
        self.delete_started = threading.Event()
        self.delete_release = threading.Event()
        self.response_identity_missing = False
        self.challenge_digest_mismatch = False
        self.challenge_calls = 0

    def __call__(self, command, input_text, _timeout):
        argv = tuple(str(item) for item in command)
        self.commands.append(argv)
        args = argv[1:]
        if args == ("list", "--format", "{{.Name}}"):
            stdout = f"{PACKVM_LIMA_INSTANCE}\n" if self.exists else ""
            return SimpleNamespace(returncode=0, stdout=stdout, stderr="")
        if len(args) >= 4 and args[:2] == ("start", "--name"):
            self.exists = True
            self.running = not self.fail_start_after_create
            if self.timeout_start:
                return SimpleNamespace(
                    returncode=1,
                    stdout="",
                    stderr="download stalled at /private/secret/image.img",
                    timed_out=True,
                )
            if self.fail_start_after_create:
                return SimpleNamespace(
                    returncode=23,
                    stdout="",
                    stderr="start failed at /private/secret/instance",
                )
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        if args[:3] == ("stop", "--force", PACKVM_LIMA_INSTANCE):
            self.running = False
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        if args[:3] == ("delete", "--force", PACKVM_LIMA_INSTANCE):
            if self.block_delete:
                self.delete_started.set()
                self.delete_release.wait(timeout=5)
            if self.fail_delete:
                return SimpleNamespace(returncode=31, stdout="", stderr="delete blocked")
            self.exists = False
            self.running = False
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        if args[:3] == ("list", PACKVM_LIMA_INSTANCE, "--format"):
            payload = {
                "name": PACKVM_LIMA_INSTANCE,
                "status": "Running" if self.running else "Stopped",
                "arch": "aarch64",
                "vmType": "vz",
                "dir": str(self.instance_dir),
                "config": {
                    "identityMarker": self.config_marker,
                    "vmType": "vz",
                    "mounts": [],
                    "networks": [],
                    "containerd": {"system": False, "user": False},
                    "ssh": {
                        "forwardAgent": False,
                        "forwardX11": False,
                        "forwardX11Trusted": False,
                    },
                    "propagateProxyEnv": False,
                    "hostResolver": {"enabled": False},
                    "portForwards": [
                        {
                            "guestIP": "0.0.0.0",
                            "guestPortRange": [1, 65535],
                            "ignore": True,
                        }
                    ],
                },
            }
            return SimpleNamespace(returncode=0, stdout=json.dumps(payload), stderr="")
        if "install" in args:
            if self.fail_install:
                return SimpleNamespace(returncode=1, stdout="", stderr="install failed")
            from ecosystem.defaultspack.backend.sandbox.isolation import lima_runtime

            self.runner_digest = lima_runtime._file_digest(lima_runtime._PACKVM_RUNNER)
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        if args[-2:] == ("cat", "/etc/machine-id"):
            return SimpleNamespace(returncode=0, stdout=self.machine_id + "\n", stderr="")
        if "sha256sum" in args:
            return SimpleNamespace(
                returncode=0,
                stdout=self.runner_digest.removeprefix("sha256:") + "  runner\n",
                stderr="",
            )
        if args[-1] == "/usr/local/libexec/tobkiri-packvm-supervisor":
            request = json.loads(input_text)
            if (
                request["operation"] == "invoke"
                and request.get("operation_id") == "challenge"
            ):
                import hashlib

                challenge = request["payload"]["challenge"]
                self.challenge_calls += 1
                payload = {
                    "challenge_digest": "sha256:" + hashlib.sha256(challenge.encode()).hexdigest()
                }
                if self.challenge_digest_mismatch and self.challenge_calls == 3:
                    payload["challenge_digest"] = "sha256:" + "f" * 64
                identities = {}
            elif request["operation"] == "invoke":
                payload = {"result": "ok"}
                identities = {
                    "guest_artifact_identity": request["guest_artifact_identity"]
                }
            elif request["operation"] == "materialize":
                payload = None
                identities = {
                    "artifact_digest": request["artifact_digest"],
                    "materialization_digest": request["materialization_digest"],
                    "guest_artifact_identity": "sha256:" + "a" * 64,
                }
            else:
                payload = None
                identities = {}
            if self.response_identity_missing:
                identities = {}
            return SimpleNamespace(
                returncode=0,
                stdout=json.dumps(
                    {
                        "ok": True,
                        "protocol": "io.tobkiri.packvm-supervisor.v1",
                        "build_id": "tobkiri-packvm-runner-1",
                        **identities,
                        **({"payload": payload} if payload is not None else {}),
                    }
                ),
                stderr="",
            )
        raise AssertionError(argv)


@pytest.fixture(autouse=True)
def _isolate_packvm_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep host Lima image-cache discovery inside each test's temp home."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))


@pytest.fixture
def provisioner(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    test_home = tmp_path / "home"
    test_lima_home = tmp_path / "lima-home"
    test_home.mkdir(exist_ok=True)
    test_lima_home.mkdir()
    monkeypatch.setenv("HOME", str(test_home))
    monkeypatch.setenv("LIMA_HOME", str(test_lima_home))
    command = tmp_path / "limactl"
    command.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    command.chmod(0o755)
    instance_dir = test_lima_home / PACKVM_LIMA_INSTANCE
    instance_dir.mkdir()
    fake = FakeLima(command, instance_dir)
    manager = PackVMLimaProvisioner(
        command_path=str(command),
        runner=fake,
        state_dir=tmp_path / "state",
        machine="arm64",
        disk_usage=lambda _path: SimpleNamespace(free=64 * 1024**3),
    )
    return manager, fake, command


def _request(plan, *, approve: bool = True) -> PackVMProvisioningRequest:
    return PackVMProvisioningRequest(
        plan_digest=plan.plan_digest,
        ceremony_nonce=plan.ceremony_nonce,
        confirmation=plan.confirmation,
        approve_image_download=approve,
    )


def _hold_packvm_process_claim(
    command_path: str,
    state_dir: str,
    lima_home: str,
    entered: object,
    release: object,
) -> None:
    """Hold the fixed-instance claim from an independent process."""

    manager = PackVMLimaProvisioner(
        command_path=command_path,
        runner=lambda *_args: None,
        state_dir=Path(state_dir),
        machine="arm64",
        lima_home=Path(lima_home),
    )
    binding = {
        "session_digest": "sha256:" + "1" * 64,
        "plan_digest": "sha256:" + "2" * 64,
        "ceremony_nonce_digest": "sha256:" + "3" * 64,
    }
    with manager.operation_gate("provision", binding):
        entered.set()  # type: ignore[attr-defined]
        release.wait(5)  # type: ignore[attr-defined]


def _wait_operation(
    lifecycle: PackVMLifecycleV4,
    operation_id: str,
    *,
    session_id: str = "panel-session-a",
) -> dict[str, object]:
    for _ in range(200):
        result = dict(lifecycle.progress(operation_id, session_id=session_id))
        if result["state"] not in {"queued", "running"}:
            return result
        time.sleep(0.01)
    raise AssertionError("PackVM operation did not settle")


def _write_environment_probe(path: Path) -> None:
    path.write_text(
        "#!/bin/sh\n"
        "printf 'HOME=%s\\n' \"${HOME-}\"\n"
        "printf 'LIMA_HOME=%s\\n' \"${LIMA_HOME-}\"\n"
        "printf 'PATH=%s\\n' \"${PATH-}\"\n"
        "printf 'UNTRUSTED=%s\\n' \"${PACKVM_UNTRUSTED-}\"\n",
        encoding="utf-8",
    )
    path.chmod(0o700)


def test_fixed_instance_claim_is_single_flight_across_processes(provisioner) -> None:
    manager, _fake, command = provisioner
    context = multiprocessing.get_context("fork")
    entered = context.Event()
    release = context.Event()
    process = context.Process(
        target=_hold_packvm_process_claim,
        args=(
            str(command),
            str(manager.state_path.parent),
            str(manager.lima_home),
            entered,
            release,
        ),
    )
    process.start()
    assert entered.wait(5)
    try:
        with pytest.raises(PackVMMutationConflict, match="in progress"):
            with manager.operation_gate("prepare", {"session_digest": "sha256:" + "4" * 64}):
                raise AssertionError("conflicting operation unexpectedly acquired the claim")
    finally:
        release.set()
        process.join(5)
    assert process.exitcode == 0


def test_failed_competitor_never_reconciles_the_owner_instance(provisioner) -> None:
    manager, fake, _command = provisioner
    fake.exists = True
    fake.running = True
    owner = {
        "session_digest": "sha256:" + "1" * 64,
        "plan_digest": "sha256:" + "2" * 64,
        "ceremony_nonce_digest": "sha256:" + "3" * 64,
    }
    competitor = {**owner, "ceremony_nonce_digest": "sha256:" + "4" * 64}
    with manager.operation_gate("provision", owner):
        before = tuple(fake.commands)
        with pytest.raises(PackVMMutationConflict):
            manager.cleanup_failed_provision(
                f"DELETE {PACKVM_LIMA_INSTANCE}",
                competitor,
            )
        assert tuple(fake.commands) == before
        assert fake.exists is True
        assert fake.running is True


def test_restart_recovery_adopts_only_the_exact_dead_owner_claim(provisioner) -> None:
    manager, _fake, _command = provisioner
    binding = {
        "session_digest": "sha256:" + "1" * 64,
        "plan_digest": "sha256:" + "2" * 64,
        "ceremony_nonce_digest": "sha256:" + "3" * 64,
    }
    manager.state_path.parent.mkdir(parents=True, exist_ok=True)
    manager.mutation_claim_path.write_text(
        json.dumps(
            {
                "version": 1,
                "operation": "provision",
                "instance": PACKVM_LIMA_INSTANCE,
                "owner_pid": 99_999_999,
                "binding": binding,
            }
        ),
        encoding="utf-8",
    )
    manager.mutation_claim_path.chmod(0o600)

    with manager.operation_gate("provision", binding, recover_claim=True):
        claim = json.loads(manager.mutation_claim_path.read_text(encoding="utf-8"))
        assert claim["owner_pid"] == os.getpid()
    assert not manager.mutation_claim_path.exists()


def test_sensitive_shell_rebinds_identity_after_response(
    provisioner,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager, fake, _command = provisioner
    assert manager.provision(_request(manager.prepare())).ready
    original = manager._verify_exact_current_instance
    calls = 0

    def swap_after_sensitive_shell(state, *, require_guest):
        nonlocal calls
        calls += 1
        if calls == 2:
            fake.machine_id = "f" * 32
        return original(state, require_guest=require_guest)

    monkeypatch.setattr(manager, "_verify_exact_current_instance", swap_after_sensitive_shell)
    request = {
        "operation": "invoke",
        "guest_artifact_identity": "sha256:" + "b" * 64,
    }
    with pytest.raises(PackVMForeignInstanceError, match="reconciliation"):
        manager.invoke_guest(request)


def test_sensitive_response_requires_exact_artifact_identity(provisioner) -> None:
    manager, fake, _command = provisioner
    assert manager.provision(_request(manager.prepare())).ready
    fake.response_identity_missing = True

    with pytest.raises(PackVMResponseReconciliationRequired, match="identity is missing"):
        manager.materialize_artifact(
            {
                "operation": "materialize",
                "artifact_digest": "sha256:" + "a" * 64,
                "materialization_digest": "sha256:" + "b" * 64,
            }
        )


def test_sensitive_response_transcript_rejects_digest_or_nonce_replay(provisioner) -> None:
    manager, fake, _command = provisioner
    assert manager.provision(_request(manager.prepare())).ready
    fake.challenge_digest_mismatch = True
    fake.challenge_calls = 0

    with pytest.raises(PackVMResponseReconciliationRequired, match="transcript mismatch"):
        manager.invoke_guest(
            {
                "operation": "invoke",
                "guest_artifact_identity": "sha256:" + "c" * 64,
            }
        )


def test_transcript_binding_is_forward_compatible_with_new_guest_operations(
    provisioner,
) -> None:
    manager, _fake, _command = provisioner
    assert manager.provision(_request(manager.prepare())).ready

    response = manager.invoke_guest({"operation": "cancel", "request_id": "request-1"})
    assert response["ok"] is True
    assert response["protocol"] == "io.tobkiri.packvm-supervisor.v1"


def _resign_operations(manager: PackVMLimaProvisioner, payload: dict[str, object]) -> None:
    """Write an intentionally modified but authentically signed operation state."""

    operations_path = manager.state_path.parent / "packvm-operations.json"
    unsigned = {key: value for key, value in payload.items() if key != "authentication"}
    key = (manager.state_path.parent / "packvm-operations.key").read_bytes()
    authentication = hmac.new(
        key,
        json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode(),
        hashlib.sha256,
    ).hexdigest()
    operations_path.write_text(
        json.dumps(
            {**unsigned, "authentication": authentication},
            sort_keys=True,
            separators=(",", ":"),
        )
        + "\n",
        encoding="utf-8",
    )
    operations_path.chmod(0o600)


def test_call_passes_only_validated_lima_environment_to_real_subprocess(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    lima_home = tmp_path / "lima-home"
    home.mkdir(exist_ok=True)
    lima_home.mkdir()
    probe = tmp_path / "environment-probe"
    _write_environment_probe(probe)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("LIMA_HOME", str(lima_home))
    monkeypatch.setenv("PACKVM_UNTRUSTED", "must-not-cross-process-boundary")

    manager = PackVMLimaProvisioner(
        command_path=str(probe),
        state_dir=tmp_path / "state",
        machine="arm64",
    )
    result = manager._call((str(probe),), timeout=10)

    assert result.returncode == 0
    assert result.stdout.splitlines() == [
        f"HOME={home}",
        f"LIMA_HOME={lima_home}",
        "PATH=/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin:/usr/local/bin",
        "UNTRUSTED=",
    ]


@pytest.mark.parametrize("variable", ["HOME", "LIMA_HOME"])
@pytest.mark.parametrize(
    "invalid_kind",
    ["empty", "relative", "parent", "symlink", "file", "unsafe_permissions"],
)
def test_lima_environment_rejects_unsafe_directory_paths(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    variable: str,
    invalid_kind: str,
) -> None:
    safe_home = tmp_path / "safe-home"
    safe_lima_home = tmp_path / "safe-lima-home"
    safe_home.mkdir()
    safe_lima_home.mkdir()
    invalid_root = tmp_path / "invalid"
    invalid_root.mkdir()
    if invalid_kind == "empty":
        invalid = ""
    elif invalid_kind == "relative":
        invalid = "relative-lima-home"
    elif invalid_kind == "parent":
        parent_target = tmp_path / "parent-target"
        parent_target.mkdir()
        invalid = str(tmp_path / "invalid" / ".." / "parent-target")
    elif invalid_kind == "symlink":
        target = invalid_root / "target"
        target.mkdir()
        link = invalid_root / "link"
        link.symlink_to(target)
        invalid = str(link)
    elif invalid_kind == "file":
        file_path = invalid_root / "not-a-directory"
        file_path.write_text("not a directory", encoding="utf-8")
        invalid = str(file_path)
    else:
        unsafe = invalid_root / "world-writable"
        unsafe.mkdir()
        os.chmod(unsafe, 0o777)
        invalid = str(unsafe)

    monkeypatch.setenv("HOME", str(safe_home))
    monkeypatch.setenv("LIMA_HOME", str(safe_lima_home))
    monkeypatch.setenv(variable, invalid)
    probe = tmp_path / "environment-probe"
    _write_environment_probe(probe)
    manager = PackVMLimaProvisioner(
        command_path=str(probe),
        state_dir=tmp_path / "state",
        machine="arm64",
    )

    with pytest.raises(ValueError, match=variable):
        manager._call((str(probe),), timeout=10)


def test_packvm_rejects_user_default_lima_home_and_foreign_instance(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    default_lima_home = home / ".lima"
    default_lima_home.mkdir()
    command = tmp_path / "limactl"
    command.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    command.chmod(0o700)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("LIMA_HOME", str(default_lima_home))
    manager = PackVMLimaProvisioner(
        command_path=str(command), state_dir=tmp_path / "state", machine="arm64"
    )
    with pytest.raises(ValueError, match=r"~/.lima"):
        manager._call((str(command), "list"), timeout=10)

    monkeypatch.setenv("LIMA_HOME", str(tmp_path / "dedicated"))
    foreign = PackVMLimaProvisioner(
        command_path=str(command),
        state_dir=tmp_path / "foreign-state",
        machine="arm64",
        instance="default",
    )
    with pytest.raises(ValueError, match="fixed managed identity"):
        foreign.prepare()


def test_lifecycle_rejects_environment_injection_payload(provisioner) -> None:
    manager, _fake, _command = provisioner
    lifecycle = PackVMLifecycleV4(manager)
    plan = lifecycle.prepare()
    consent_payload = {
        "plan_digest": plan["plan_digest"],
        "ceremony_nonce": plan["ceremony_nonce"],
        "confirmation": plan["confirmation"],
        "approve_image_download": True,
        "env": {"LIMA_HOME": "/tmp/attacker-controlled-lima-home"},
    }

    with pytest.raises(ValueError, match="typed contract"):
        lifecycle.consent(consent_payload)

    consent_payload.pop("env")
    consent = lifecycle.consent(consent_payload)
    with pytest.raises(ValueError, match="typed contract"):
        lifecycle.provision(
            {
                "consent_id": consent["consent_id"],
                "operation_id": str(uuid.uuid4()),
                "env": {"LIMA_HOME": "/tmp/attacker-controlled-lima-home"},
            }
        )


@pytest.mark.skipif(
    platform.system() != "Darwin" or shutil.which("limactl") is None,
    reason="requires the installed macOS limactl for a non-mutating isolation check",
)
def test_real_limactl_list_isolated_from_user_lima_home(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    isolated_home = tmp_path / "isolated-home"
    isolated_lima_home = tmp_path / "isolated-lima-home"
    isolated_home.mkdir()
    isolated_lima_home.mkdir()
    monkeypatch.setenv("HOME", str(isolated_home))
    monkeypatch.setenv("LIMA_HOME", str(isolated_lima_home))
    monkeypatch.delenv("PACKVM_UNTRUSTED", raising=False)

    command = shutil.which("limactl")
    assert command is not None
    manager = PackVMLimaProvisioner(
        command_path=command,
        state_dir=tmp_path / "state",
        machine="arm64",
    )
    result = manager._call(
        (manager._require_command(), "list", "--format", "{{.Name}}"),
        timeout=10,
    )

    assert result.returncode == 0
    assert PACKVM_LIMA_INSTANCE not in result.stdout
    assert not (isolated_lima_home / PACKVM_LIMA_INSTANCE).exists()


def test_fresh_provision_requires_download_approval_and_consumes_ceremony(
    provisioner,
) -> None:
    manager, fake, _command = provisioner
    plan = manager.prepare()
    assert plan.backend_id == PACKVM_BACKEND_ID
    assert plan.image_download_required is True
    assert plan.image_source.startswith("https://cloud-images.ubuntu.com/jammy/20260807/")
    assert plan.image_size_bytes > 600_000_000
    assert plan.disk_size_bytes == 4 * 1024**3
    assert plan.host_free_space_required_bytes == (
        PACKVM_DISK_SIZE_BYTES
        + PACKVM_HOST_STORAGE_RESERVE_BYTES
        + PACKVM_PINNED_IMAGE_VIRTUAL_SIZE_BYTES
        + plan.image_size_bytes
    )
    assert plan.host_free_space_available_bytes == 64 * 1024**3
    assert plan.host_free_space_reason is None
    assert plan.image_cache_status == "absent"
    assert plan.image_cache_reason is None
    assert plan.architecture == "arm64"
    assert plan.config_digest.startswith("sha256:")
    assert plan.guest_runner_digest.startswith("sha256:")
    assert plan.host_build_digest.startswith("sha256:")

    with pytest.raises(ValueError, match="explicit approval"):
        manager.provision(_request(plan, approve=False))
    assert all(command[1] == "list" for command in fake.commands)
    with pytest.raises(ValueError, match="already consumed"):
        manager.provision(_request(plan))


def test_checked_in_policy_has_no_network_mount_or_guest_download(provisioner) -> None:
    manager, _fake, _command = provisioner
    config = yaml.safe_load(manager._rendered_config())

    assert config["cpus"] == 2
    assert config["memory"] == "4GiB"
    assert config["disk"] == "4GiB"
    assert config["mounts"] == []
    assert config["networks"] == []
    assert config["propagateProxyEnv"] is False
    assert config["images"][0]["digest"].startswith("sha256:")
    assert "provision" not in config
    assert PACKVM_ARTIFACT_STORAGE_BUDGET_BYTES == packvm_guest_runner.MAX_ARTIFACT_STORAGE_BYTES
    assert PACKVM_GUEST_FREE_RESERVE_BYTES == packvm_guest_runner.MIN_GUEST_FREE_RESERVE_BYTES


def test_provision_fails_before_lima_mutation_when_host_space_is_insufficient(
    tmp_path: Path,
) -> None:
    command = tmp_path / "limactl"
    command.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    command.chmod(0o755)
    instance_dir = tmp_path / PACKVM_LIMA_INSTANCE
    instance_dir.mkdir()
    fake = FakeLima(command, instance_dir)
    available = 2 * 1024**3
    manager = PackVMLimaProvisioner(
        command_path=str(command),
        runner=fake,
        state_dir=tmp_path / "state",
        machine="arm64",
        disk_usage=lambda _path: SimpleNamespace(free=available),
    )

    plan = manager.prepare()
    assert plan.host_free_space_available_bytes == available
    assert "requires at least" in str(plan.host_free_space_reason)
    assert "only 2.00 GiB" in str(plan.host_free_space_reason)
    with pytest.raises(ValueError, match="only 2.00 GiB"):
        manager.provision(_request(plan))
    assert fake.exists is False
    assert all(command[1] == "list" for command in fake.commands)


def test_exact_lima_cache_hit_is_digest_verified_and_reduces_preflight(
    provisioner,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ecosystem.defaultspack.backend.sandbox.isolation import lima_runtime

    manager, fake, _command = provisioner
    content = b"pinned-test-image"
    source = "https://example.invalid/pinned-packvm.img"
    image = dict(lima_runtime._PACKVM_IMAGES["arm64"])
    image.update(
        {
            "url": source,
            "digest": "sha256:" + hashlib.sha256(content).hexdigest(),
            "size_bytes": len(content),
        }
    )
    monkeypatch.setitem(lima_runtime._PACKVM_IMAGES, "arm64", image)
    monkeypatch.setenv("HOME", str(tmp_path))
    entry = (
        tmp_path
        / "Library"
        / "Caches"
        / "lima"
        / "download"
        / "by-url-sha256"
        / hashlib.sha256(source.encode()).hexdigest()
    )
    entry.mkdir(parents=True)
    (entry / "url").write_text(source, encoding="utf-8")
    (entry / "data").write_bytes(content)

    plan = manager.prepare()
    assert plan.image_download_required is False
    assert plan.image_cache_status == "verified_source"
    assert plan.host_free_space_required_bytes == (
        PACKVM_DISK_SIZE_BYTES
        + PACKVM_HOST_STORAGE_RESERVE_BYTES
        + PACKVM_PINNED_IMAGE_VIRTUAL_SIZE_BYTES
    )
    (entry / "data").write_bytes(b"tampered-test-image")
    with pytest.raises(ValueError, match="plan changed"):
        manager.provision(_request(plan, approve=False))
    assert fake.exists is False


def test_lima_cache_source_match_without_digest_match_fails_closed(
    provisioner,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ecosystem.defaultspack.backend.sandbox.isolation import lima_runtime

    manager, _fake, _command = provisioner
    content = b"expected"
    source = "https://example.invalid/pinned-packvm.img"
    image = dict(lima_runtime._PACKVM_IMAGES["arm64"])
    image.update(
        {
            "url": source,
            "digest": "sha256:" + hashlib.sha256(content).hexdigest(),
            "size_bytes": len(content),
        }
    )
    monkeypatch.setitem(lima_runtime._PACKVM_IMAGES, "arm64", image)
    monkeypatch.setenv("HOME", str(tmp_path))
    entry = (
        tmp_path
        / "Library"
        / "Caches"
        / "lima"
        / "download"
        / "by-url-sha256"
        / hashlib.sha256(source.encode()).hexdigest()
    )
    entry.mkdir(parents=True)
    (entry / "url").write_text(source, encoding="utf-8")
    (entry / "data").write_bytes(b"tampered")

    plan = manager.prepare()
    assert plan.image_download_required is False
    assert plan.image_cache_status == "unsafe"
    assert "digest does not match" in str(plan.image_cache_reason)
    assert plan.host_free_space_required_bytes == (
        PACKVM_DISK_SIZE_BYTES
        + PACKVM_HOST_STORAGE_RESERVE_BYTES
        + PACKVM_PINNED_IMAGE_VIRTUAL_SIZE_BYTES
    )
    with pytest.raises(ValueError, match="digest does not match"):
        manager.provision(_request(plan, approve=False))


def test_lima_converted_raw_cache_is_not_trusted_as_pinned_source(
    provisioner,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ecosystem.defaultspack.backend.sandbox.isolation import lima_runtime

    manager, fake, _command = provisioner
    content = b"expected"
    source = "https://example.invalid/pinned-packvm.img"
    image = dict(lima_runtime._PACKVM_IMAGES["arm64"])
    image.update(
        {
            "url": source,
            "digest": "sha256:" + hashlib.sha256(content).hexdigest(),
            "size_bytes": len(content),
        }
    )
    monkeypatch.setitem(lima_runtime._PACKVM_IMAGES, "arm64", image)
    monkeypatch.setenv("HOME", str(tmp_path))
    entry = (
        tmp_path
        / "Library"
        / "Caches"
        / "lima"
        / "download"
        / "by-url-sha256"
        / hashlib.sha256(source.encode()).hexdigest()
    )
    (entry / "imgconv").mkdir(parents=True)
    (entry / "url").write_text(source, encoding="utf-8")
    (entry / "data").write_bytes(content)
    (entry / "imgconv" / "raw").write_bytes(content)
    (entry / "imgconv" / "raw.digest").write_text(
        "sha256:" + hashlib.sha256(content).hexdigest(),
        encoding="utf-8",
    )

    plan = manager.prepare()
    assert plan.image_cache_status == "unsafe"
    assert "not independently bound" in str(plan.image_cache_reason)
    with pytest.raises(ValueError, match="not independently bound"):
        manager.provision(_request(plan, approve=False))
    assert fake.exists is False


def test_provision_doctor_stop_and_cleanup_are_authenticated(provisioner) -> None:
    manager, fake, _command = provisioner
    plan = manager.prepare()
    doctor = manager.provision(_request(plan))

    assert doctor.ready is True
    assert doctor.backend_id == PACKVM_BACKEND_ID
    assert doctor.attestation_digest
    assert manager.doctor().ready is True
    with pytest.raises(ValueError, match="exact confirmation"):
        manager.stop("STOP something-else")
    manager.stop(f"STOP {PACKVM_LIMA_INSTANCE}")
    assert manager.doctor().ready is False
    fake.running = True
    with pytest.raises(ValueError, match="exact confirmation"):
        manager.cleanup("DELETE something-else")
    manager.cleanup(f"DELETE {PACKVM_LIMA_INSTANCE}")
    assert not manager.state_path.exists()
    assert fake.exists is False


@pytest.mark.parametrize(
    "action, mutation",
    [
        ("stop", "machine"),
        ("stop", "runner"),
        ("stop", "config"),
        ("stop", "image"),
        ("stop", "directory"),
        ("cleanup", "machine"),
        ("cleanup", "runner"),
        ("cleanup", "config"),
        ("cleanup", "image"),
        ("cleanup", "directory"),
        ("cleanup", "symlink"),
    ],
)
def test_destructive_actions_refuse_same_name_replacement_and_identity_swaps(
    provisioner,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    action: str,
    mutation: str,
) -> None:
    manager, fake, command = provisioner
    assert manager.provision(_request(manager.prepare())).ready
    user_lima = tmp_path / "home" / ".lima"
    user_lima.mkdir()
    marker = user_lima / "do-not-touch"
    marker.write_text("user instance", encoding="utf-8")
    before = len(fake.commands)

    if mutation == "machine":
        fake.machine_id = "f" * 32
    elif mutation == "runner":
        fake.runner_digest = "sha256:" + "f" * 64
    elif mutation == "config":
        fake.config_marker = "foreign"
    elif mutation == "image":
        from ecosystem.defaultspack.backend.sandbox.isolation import lima_runtime

        replacement = dict(lima_runtime._PACKVM_IMAGES["arm64"])
        replacement["digest"] = "sha256:" + "a" * 64
        monkeypatch.setitem(lima_runtime._PACKVM_IMAGES, "arm64", replacement)
    else:
        fake.instance_dir.rmdir()
        if mutation == "directory":
            fake.instance_dir.mkdir()
        else:
            target = tmp_path / "foreign-instance"
            target.mkdir()
            fake.instance_dir.symlink_to(target, target_is_directory=True)

    confirmation = (
        f"STOP {PACKVM_LIMA_INSTANCE}" if action == "stop" else f"DELETE {PACKVM_LIMA_INSTANCE}"
    )
    with pytest.raises(PackVMForeignInstanceError, match="reconciliation"):
        getattr(manager, action)(confirmation)

    destructive = {
        command_tuple[1]
        for command_tuple in fake.commands[before:]
        if len(command_tuple) > 1 and command_tuple[1] in {"stop", "delete"}
    }
    assert destructive == set()
    assert fake.exists is True
    assert marker.read_text(encoding="utf-8") == "user instance"
    assert command.parent != user_lima


def test_restarted_provisioner_refuses_replaced_fixed_name_instance(
    provisioner,
) -> None:
    manager, fake, command = provisioner
    assert manager.provision(_request(manager.prepare())).ready
    fake.instance_dir.rmdir()
    fake.instance_dir.mkdir()
    restarted = PackVMLimaProvisioner(
        command_path=str(command),
        runner=fake,
        state_dir=manager.state_path.parent,
        machine="arm64",
    )

    assert restarted.doctor().ready is False
    before = len(fake.commands)
    with pytest.raises(PackVMForeignInstanceError, match="reconciliation"):
        restarted.cleanup(f"DELETE {PACKVM_LIMA_INSTANCE}")
    assert not any(
        len(item) > 1 and item[1] in {"stop", "delete"} for item in fake.commands[before:]
    )


def test_failed_provision_cleanup_refuses_replaced_same_name_orphan(
    provisioner,
) -> None:
    manager, fake, _command = provisioner
    fake.fail_start_after_create = True
    fake.fail_delete = True
    with pytest.raises(PackVMProcessError):
        manager.provision(_request(manager.prepare()))
    recovery = manager._load_authenticated_recovery()
    fake.instance_dir.rmdir()
    fake.instance_dir.mkdir()
    fake.fail_delete = False
    before = len(fake.commands)

    with pytest.raises(PackVMForeignInstanceError, match="reconciliation"):
        manager.cleanup_failed_provision(f"DELETE {PACKVM_LIMA_INSTANCE}", recovery)
    assert not any(len(item) > 1 and item[1] == "delete" for item in fake.commands[before:])


def test_runtime_surface_recomputes_exact_packvm_attestation_digest(
    provisioner,
) -> None:
    from core_runtime.runtime_surface_v4 import _packvm_attested

    manager, _fake, _command = provisioner
    plan = manager.prepare()
    manager.provision(_request(plan))
    snapshot = manager.readiness_snapshot()

    assert _packvm_attested(snapshot) is True
    assert snapshot["config_digest"] == plan.config_digest
    assert snapshot["image_digest"] == plan.image_digest
    assert snapshot["guest_runner_digest"] == plan.guest_runner_digest
    assert snapshot["host_build_digest"] == plan.host_build_digest

    tampered = {**snapshot, "guest_runner_digest": "sha256:" + "0" * 64}
    assert _packvm_attested(tampered) is False
    expired = {**snapshot, "observed_unix": int(time.time()) - 31}
    assert _packvm_attested(expired) is False


@pytest.mark.parametrize(
    "mutation, expected",
    [
        ("state", "authentication failed"),
        ("binary", "limactl binary changed"),
        ("instance", "instance identity changed"),
        ("runner", "guest supervisor changed"),
    ],
)
def test_doctor_rejects_tampered_identity(provisioner, mutation: str, expected: str) -> None:
    manager, fake, command = provisioner
    plan = manager.prepare()
    assert manager.provision(_request(plan)).ready
    if mutation == "state":
        payload = json.loads(manager.state_path.read_text(encoding="utf-8"))
        payload["config_digest"] = "sha256:" + "0" * 64
        manager.state_path.write_text(json.dumps(payload), encoding="utf-8")
        manager.state_path.chmod(0o600)
    elif mutation == "binary":
        command.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
        command.chmod(0o755)
    elif mutation == "instance":
        fake.machine_id = "f" * 32
    else:
        fake.runner_digest = "sha256:" + "f" * 64
    result = manager.doctor()
    assert result.ready is False
    assert expected in str(result.reason)


def test_symlinked_cli_and_state_fail_closed(provisioner, tmp_path: Path) -> None:
    manager, _fake, command = provisioner
    symlink = tmp_path / "limactl-link"
    symlink.symlink_to(command)
    linked = PackVMLimaProvisioner(
        command_path=str(symlink), state_dir=tmp_path / "linked", machine="arm64"
    )
    linked_plan = linked.prepare()
    assert linked_plan.limactl is None
    assert "regular executable" in str(linked_plan.launcher_reason)

    plan = manager.prepare()
    assert manager.provision(_request(plan)).ready
    state_copy = manager.state_path.read_bytes()
    manager.state_path.unlink()
    target = tmp_path / "state-copy"
    target.write_bytes(state_copy)
    target.chmod(0o600)
    manager.state_path.symlink_to(target)
    assert manager.doctor().ready is False
    assert "unsafe PackVM state" in str(manager.doctor().reason)


def test_partial_provision_stops_guest_without_attesting(provisioner) -> None:
    manager, fake, _command = provisioner
    fake.fail_install = True
    plan = manager.prepare()
    with pytest.raises(PackVMProcessError, match="install failed"):
        manager.provision(_request(plan))
    assert fake.exists is False
    assert fake.running is False
    assert not manager.state_path.exists()
    assert "provision_failed" in manager.audit_path.read_text(encoding="utf-8")


def test_failed_start_reconciles_created_stopped_instance(provisioner) -> None:
    manager, fake, _command = provisioner
    fake.fail_start_after_create = True
    plan = manager.prepare()

    with pytest.raises(PackVMProcessError) as captured:
        manager.provision(_request(plan))

    assert captured.value.stage == "start"
    assert captured.value.kind == "exit"
    assert captured.value.exit_code == 23
    assert captured.value.stderr == "start failed at <host-path>"
    assert fake.exists is False
    assert manager.recovery_path.exists() is False
    assert "failed_provision_reconciled" in manager.audit_path.read_text(encoding="utf-8")


def test_failed_start_timeout_preserves_typed_bounded_diagnostic(provisioner) -> None:
    manager, fake, _command = provisioner
    fake.timeout_start = True
    plan = manager.prepare()

    with pytest.raises(PackVMProcessError) as captured:
        manager.provision(_request(plan))

    assert captured.value.kind == "timeout"
    assert captured.value.exit_code is None
    assert captured.value.stderr == "download stalled at <host-path>"
    assert "/private/secret" not in str(captured.value)


def test_reconciled_failed_provision_cleanup_is_safely_idempotent(provisioner) -> None:
    manager, fake, _command = provisioner
    fake.fail_start_after_create = True
    lifecycle = PackVMLifecycleV4(manager)
    plan = lifecycle.prepare(session_id="panel-session-a")
    consent = lifecycle.consent(
        {
            "plan_digest": plan["plan_digest"],
            "ceremony_nonce": plan["ceremony_nonce"],
            "confirmation": plan["confirmation"],
            "approve_image_download": True,
        },
        session_id="panel-session-a",
    )
    provision_operation_id = str(uuid.uuid4())
    lifecycle.provision(
        {"consent_id": consent["consent_id"], "operation_id": provision_operation_id},
        session_id="panel-session-a",
    )
    assert _wait_operation(lifecycle, provision_operation_id)["state"] == "failed"
    assert fake.exists is False
    cleanup_operation_id = str(uuid.uuid4())
    lifecycle.cleanup(
        {
            "confirmation": f"DELETE {PACKVM_LIMA_INSTANCE}",
            "operation_id": cleanup_operation_id,
            "source_operation_id": provision_operation_id,
        },
        session_id="panel-session-a",
    )
    result = _wait_operation(lifecycle, cleanup_operation_id)
    assert result["state"] == "succeeded"
    assert result["result"]["missing"] is True


def test_failed_provision_cleanup_is_durable_session_bound_and_replay_safe(
    provisioner,
) -> None:
    manager, fake, _command = provisioner
    fake.fail_start_after_create = True
    fake.fail_delete = True
    lifecycle = PackVMLifecycleV4(manager)
    session_id = "panel-session-a"
    plan = lifecycle.prepare(session_id=session_id)
    consent = lifecycle.consent(
        {
            "plan_digest": plan["plan_digest"],
            "ceremony_nonce": plan["ceremony_nonce"],
            "confirmation": plan["confirmation"],
            "approve_image_download": True,
        },
        session_id=session_id,
    )
    provision_operation_id = str(uuid.uuid4())
    lifecycle.provision(
        {"consent_id": consent["consent_id"], "operation_id": provision_operation_id},
        session_id=session_id,
    )
    failed = _wait_operation(lifecycle, provision_operation_id)
    assert failed["state"] == "failed"
    assert failed["operation_kind"] == "provision"
    assert failed["diagnostic"] == {
        "code": "packvm_lima_process_failed",
        "stage": "start",
        "kind": "exit",
        "exit_code": 23,
        "stderr": "start failed at <host-path>",
    }
    assert "recovery_proof" not in failed
    assert manager.recovery_path.exists()
    assert fake.exists

    recovery = manager._load_authenticated_recovery()
    with pytest.raises(ValueError, match="proof does not match"):
        manager.cleanup_failed_provision(
            f"DELETE {PACKVM_LIMA_INSTANCE}",
            {**recovery, "image_digest": "sha256:" + "0" * 64},
        )

    cleanup_operation_id = str(uuid.uuid4())
    cleanup_payload = {
        "confirmation": f"DELETE {PACKVM_LIMA_INSTANCE}",
        "operation_id": cleanup_operation_id,
        "source_operation_id": provision_operation_id,
    }
    with pytest.raises(ValueError, match="another authenticated session"):
        lifecycle.progress(provision_operation_id, session_id="wrong-session")
    with pytest.raises(ValueError, match="source is invalid"):
        lifecycle.cleanup(cleanup_payload, session_id="wrong-session")
    with pytest.raises(ValueError, match="exact confirmation"):
        lifecycle.cleanup(
            {**cleanup_payload, "confirmation": "DELETE default"},
            session_id=session_id,
        )

    fake.fail_delete = False
    queued = lifecycle.cleanup(cleanup_payload, session_id=session_id)
    assert queued["operation_kind"] == "cleanup"
    assert queued["state"] in {"queued", "running"}
    cleaned = _wait_operation(lifecycle, cleanup_operation_id)
    assert cleaned["state"] == "succeeded"
    assert cleaned["result"] == {
        "ready": False,
        "instance": PACKVM_LIMA_INSTANCE,
        "cleanup_confirmation": f"DELETE {PACKVM_LIMA_INSTANCE}",
        "missing": False,
    }
    assert fake.exists is False
    assert manager.recovery_path.exists() is False
    assert lifecycle.cleanup(cleanup_payload, session_id=session_id) == cleaned
    with pytest.raises(ValueError, match="already bound"):
        lifecycle.cleanup(
            {**cleanup_payload, "operation_id": str(uuid.uuid4())},
            session_id=session_id,
        )

    restarted = PackVMLifecycleV4(manager)
    assert restarted.progress(cleanup_operation_id, session_id=session_id) == cleaned


def test_running_cleanup_recovers_as_interrupted_after_host_restart(provisioner) -> None:
    manager, fake, _command = provisioner
    assert manager.provision(_request(manager.prepare())).ready
    lifecycle = PackVMLifecycleV4(manager)
    fake.block_delete = True
    operation_id = str(uuid.uuid4())
    lifecycle.cleanup(
        {
            "confirmation": f"DELETE {PACKVM_LIMA_INSTANCE}",
            "operation_id": operation_id,
            "source_operation_id": None,
        },
        session_id="panel-session-a",
    )
    assert fake.delete_started.wait(timeout=2)

    restarted = PackVMLifecycleV4(manager)
    interrupted = restarted.progress(operation_id, session_id="panel-session-a")
    assert interrupted["operation_kind"] == "cleanup"
    assert interrupted["state"] == "interrupted"
    assert interrupted["error_type"] == "PackVMOperationInterrupted"
    fake.delete_release.set()


def test_orphan_cleanup_rejects_symlinked_dedicated_lima_home(
    provisioner,
    tmp_path: Path,
) -> None:
    manager, fake, _command = provisioner
    fake.fail_start_after_create = True
    fake.fail_delete = True
    with pytest.raises(PackVMProcessError):
        manager.provision(_request(manager.prepare()))
    recovery = manager._load_authenticated_recovery()
    original = manager.lima_home
    moved = tmp_path / "moved-lima-home"
    original.rename(moved)
    original.symlink_to(moved, target_is_directory=True)

    with pytest.raises(ValueError, match="symlinks|unsafe"):
        manager.cleanup_failed_provision(f"DELETE {PACKVM_LIMA_INSTANCE}", recovery)
    assert fake.exists is True


def test_reviewed_image_digest_cannot_change_before_provision(
    provisioner, monkeypatch: pytest.MonkeyPatch
) -> None:
    from ecosystem.defaultspack.backend.sandbox.isolation import lima_runtime

    manager, fake, _command = provisioner
    plan = manager.prepare()
    replacement = dict(lima_runtime._PACKVM_IMAGES["arm64"])
    replacement["digest"] = "sha256:" + "f" * 64
    monkeypatch.setitem(lima_runtime._PACKVM_IMAGES, "arm64", replacement)

    with pytest.raises(ValueError, match="plan changed"):
        manager.provision(_request(plan))
    assert fake.exists is False


def test_reviewed_config_cannot_change_before_provision(
    provisioner, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from ecosystem.defaultspack.backend.sandbox.isolation import lima_runtime

    manager, fake, _command = provisioner
    plan = manager.prepare()
    changed = tmp_path / "changed.yaml"
    changed.write_text(
        lima_runtime._PACKVM_CONFIG.read_text(encoding="utf-8") + "cpus: 8\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(lima_runtime, "_PACKVM_CONFIG", changed)

    with pytest.raises(ValueError, match="plan changed"):
        manager.provision(_request(plan))
    assert fake.exists is False


def test_doctor_rejects_a_changed_host_build(
    provisioner,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from ecosystem.defaultspack.backend.sandbox.isolation import lima_runtime

    manager, _fake, _command = provisioner
    plan = manager.prepare()
    assert manager.provision(_request(plan)).ready
    original_digest = lima_runtime._file_digest

    def changed_host_digest(path: Path) -> str:
        if path == Path(lima_runtime.__file__):
            return "sha256:" + "f" * 64
        return original_digest(path)

    monkeypatch.setattr(lima_runtime, "_file_digest", changed_host_digest)
    health = manager.doctor()
    assert health.ready is False
    assert "Host build changed" in str(health.reason)


def test_typed_consent_is_one_shot_and_attestation_survives_restart(provisioner) -> None:
    manager, fake, command = provisioner
    lifecycle = PackVMLifecycleV4(manager)
    plan = lifecycle.prepare()
    consent_payload = {
        "plan_digest": plan["plan_digest"],
        "ceremony_nonce": plan["ceremony_nonce"],
        "confirmation": plan["confirmation"],
        "approve_image_download": True,
    }
    consent = lifecycle.consent(consent_payload)
    with pytest.raises(ValueError, match="pending plan"):
        lifecycle.consent(consent_payload)
    operation_id = str(uuid.uuid4())
    started = lifecycle.provision(
        {"consent_id": consent["consent_id"], "operation_id": operation_id}
    )
    assert started["state"] in {"queued", "running"}
    for _ in range(100):
        progress = lifecycle.progress(operation_id)
        if progress["state"] == "succeeded":
            break
        time.sleep(0.01)
    assert progress["doctor"]["ready"] is True
    assert (
        lifecycle.provision({"consent_id": consent["consent_id"], "operation_id": operation_id})[
            "state"
        ]
        == "succeeded"
    )

    restarted = PackVMLimaProvisioner(
        command_path=str(command),
        runner=fake,
        state_dir=manager.state_path.parent,
        machine="arm64",
    )
    assert restarted.doctor().ready is True
    assert restarted.doctor().instance == PACKVM_LIMA_INSTANCE
    assert all("rumi-managed-runtime" not in command for command in fake.commands)
    restarted_lifecycle = PackVMLifecycleV4(restarted)
    assert restarted_lifecycle.progress(operation_id)["state"] == "succeeded"
    operations_path = manager.state_path.parent / "packvm-operations.json"
    operation_state = json.loads(operations_path.read_text(encoding="utf-8"))
    operation_state["operations"][operation_id]["state"] = "failed"
    operations_path.write_text(json.dumps(operation_state), encoding="utf-8")
    operations_path.chmod(0o600)
    with pytest.raises(ValueError, match="authentication failed"):
        PackVMLifecycleV4(restarted)


def test_restart_recovers_only_exact_session_plan_and_recovery_proof(
    provisioner,
) -> None:
    manager, _fake, _command = provisioner
    lifecycle = PackVMLifecycleV4(manager)
    session_id = "panel-session-a"
    plan = lifecycle.prepare(session_id=session_id)
    consent = lifecycle.consent(
        {
            "plan_digest": plan["plan_digest"],
            "ceremony_nonce": plan["ceremony_nonce"],
            "confirmation": plan["confirmation"],
            "approve_image_download": True,
        },
        session_id=session_id,
    )
    operation_id = str(uuid.uuid4())
    lifecycle.provision(
        {"consent_id": consent["consent_id"], "operation_id": operation_id},
        session_id=session_id,
    )
    assert _wait_operation(lifecycle, operation_id, session_id=session_id)["state"] == ("succeeded")

    operations_path = manager.state_path.parent / "packvm-operations.json"
    payload = json.loads(operations_path.read_text(encoding="utf-8"))
    exact = payload["operations"][operation_id]
    exact["state"] = "running"
    different_plan_id = str(uuid.uuid4())
    different_plan = json.loads(json.dumps(exact))
    different_plan.update(
        {
            "operation_id": different_plan_id,
            "state": "queued",
            "consent_digest": "sha256:" + hashlib.sha256(b"different").hexdigest(),
            "plan_digest": "sha256:" + "d" * 64,
        }
    )
    different_plan["recovery_proof"]["plan_digest"] = "sha256:" + "d" * 64
    tampered_proof_id = str(uuid.uuid4())
    tampered_proof = json.loads(json.dumps(exact))
    tampered_proof.update(
        {
            "operation_id": tampered_proof_id,
            "state": "running",
            "consent_digest": "sha256:" + hashlib.sha256(b"tampered").hexdigest(),
        }
    )
    tampered_proof["recovery_proof"]["guest_runner_digest"] = "sha256:" + "e" * 64
    payload["operations"][different_plan_id] = different_plan
    payload["operations"][tampered_proof_id] = tampered_proof
    _resign_operations(manager, payload)

    restarted = PackVMLifecycleV4(manager)
    recovered = restarted.progress(operation_id, session_id=session_id)
    assert recovered["state"] == "succeeded"
    for mismatched_id in (different_plan_id, tampered_proof_id):
        interrupted = restarted.progress(mismatched_id, session_id=session_id)
        assert interrupted["state"] == "interrupted"
        assert interrupted["error_type"] == "PackVMReconciliationRequired"
        assert "reconciliation is required" in str(interrupted["error"])
    assert (
        restarted.provision(
            {"consent_id": consent["consent_id"], "operation_id": operation_id},
            session_id=session_id,
        )["state"]
        == "succeeded"
    )
    with pytest.raises(ValueError, match="another consent"):
        restarted.provision(
            {"consent_id": "foreign-consent", "operation_id": operation_id},
            session_id=session_id,
        )


def test_operation_journal_compacts_with_authenticated_replay_and_dependencies(
    provisioner,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from core_runtime import packvm_lifecycle_v4

    class InertThread:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def start(self) -> None:
            pass

    monkeypatch.setattr(
        packvm_lifecycle_v4,
        "threading",
        SimpleNamespace(Thread=InertThread, RLock=threading.RLock),
    )
    manager, _fake, _command = provisioner
    lifecycle = PackVMLifecycleV4(manager)
    session_id = "panel-session-a"
    session_digest = "sha256:" + hashlib.sha256(session_id.encode()).hexdigest()
    operation_ids: list[str] = []
    consent_ids: dict[str, str] = {}
    for _index in range(140):
        plan = lifecycle.prepare(session_id=session_id)
        consent = lifecycle.consent(
            {
                "plan_digest": plan["plan_digest"],
                "ceremony_nonce": plan["ceremony_nonce"],
                "confirmation": plan["confirmation"],
                "approve_image_download": True,
            },
            session_id=session_id,
        )
        operation_id = str(uuid.uuid4())
        operation_ids.append(operation_id)
        consent_ids[operation_id] = str(consent["consent_id"])
        lifecycle.provision(
            {"consent_id": consent["consent_id"], "operation_id": operation_id},
            session_id=session_id,
        )
        cancelled = lifecycle.cancel({"operation_id": operation_id}, session_id=session_id)
        assert cancelled["state"] == "cancelled"
    source_id = str(uuid.uuid4())
    cleanup_id = str(uuid.uuid4())
    lifecycle._operations[source_id] = {
        "operation_id": source_id,
        "operation_kind": "provision",
        "session_digest": session_digest,
        "state": "failed",
        "plan_digest": "sha256:" + "a" * 64,
        "recovery_proof": {"retained": True},
        "cleanup_operation_id": cleanup_id,
        "updated_unix": 200,
    }
    lifecycle._operations[cleanup_id] = {
        "operation_id": cleanup_id,
        "operation_kind": "cleanup",
        "session_digest": session_digest,
        "source_operation_id": source_id,
        "state": "running",
        "plan_digest": "sha256:" + "a" * 64,
        "updated_unix": 201,
    }
    lifecycle._persist_operations()

    archive_path = manager.state_path.parent / "packvm-operations-archive.jsonl"
    assert archive_path.exists()
    assert len(lifecycle._operations) < 128
    assert source_id in lifecycle._operations
    assert cleanup_id in lifecycle._operations
    assert len(operation_ids) == 140
    archived_id = next(iter(lifecycle._archived_operations))

    restarted = PackVMLifecycleV4(manager)
    assert restarted.progress(archived_id, session_id=session_id)["state"] == "cancelled"
    assert restarted.progress(source_id, session_id=session_id)["state"] == "failed"
    assert restarted.progress(cleanup_id, session_id=session_id)["state"] == "interrupted"
    with pytest.raises(ValueError, match="another authenticated session"):
        restarted.progress(archived_id, session_id="foreign-session")
    replay = restarted.provision(
        {"consent_id": consent_ids[archived_id], "operation_id": archived_id},
        session_id=session_id,
    )
    assert replay["state"] == "cancelled"

    encoded = archive_path.read_bytes()
    archive_path.write_bytes(encoded.replace(b'"state":"cancelled"', b'"state":"tampered"', 1))
    archive_path.chmod(0o600)
    with pytest.raises(ValueError, match="authentication failed|digest failed"):
        PackVMLifecycleV4(manager)


def test_guest_runner_executes_only_the_explicit_staged_python_abi(tmp_path: Path) -> None:
    from ecosystem.defaultspack.backend.sandbox.isolation import lima_runtime

    implementation = tmp_path / "operation.py"
    implementation.write_text(
        "def tobkiri_packvm_invoke(operation_id, payload):\n"
        "    return {'operation_id': operation_id, 'value': payload['value']}\n",
        encoding="utf-8",
    )
    request = json.dumps(
        {
            "contract_id": "example.contract.v1",
            "operation_id": "example-pack.inspect",
            "payload": {"value": 7},
        }
    )
    result = subprocess.run(
        (
            sys.executable,
            "-I",
            "-S",
            str(lima_runtime._PACKVM_RUNNER),
            "--execute",
            str(implementation),
        ),
        input=request,
        text=True,
        capture_output=True,
        timeout=10,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {
        "operation_id": "example-pack.inspect",
        "value": 7,
    }

    implementation.write_text("RESULT = {}\n", encoding="utf-8")
    denied = subprocess.run(
        (
            sys.executable,
            "-I",
            "-S",
            str(lima_runtime._PACKVM_RUNNER),
            "--execute",
            str(implementation),
        ),
        input=request,
        text=True,
        capture_output=True,
        timeout=10,
        check=False,
    )
    assert denied.returncode == 1
    assert "does not export tobkiri_packvm_invoke" in denied.stderr
