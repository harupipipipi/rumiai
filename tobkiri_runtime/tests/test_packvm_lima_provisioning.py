from __future__ import annotations

import json
import subprocess
import sys
import time
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from ecosystem.defaultspack.backend.sandbox.isolation.lima_runtime import (
    PACKVM_BACKEND_ID,
    PACKVM_LIMA_INSTANCE,
    PackVMLimaProvisioner,
    PackVMProvisioningRequest,
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
        self.commands: list[tuple[str, ...]] = []
        self.fail_install = False

    def __call__(self, command, input_text, _timeout):
        argv = tuple(str(item) for item in command)
        self.commands.append(argv)
        args = argv[1:]
        if args == ("list", "--format", "{{.Name}}"):
            stdout = f"{PACKVM_LIMA_INSTANCE}\n" if self.exists else ""
            return SimpleNamespace(returncode=0, stdout=stdout, stderr="")
        if len(args) >= 4 and args[:2] == ("start", "--name"):
            self.exists = True
            self.running = True
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        if args[:3] == ("stop", "--force", PACKVM_LIMA_INSTANCE):
            self.running = False
            return SimpleNamespace(returncode=0, stdout="", stderr="")
        if args[:3] == ("delete", "--force", PACKVM_LIMA_INSTANCE):
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
            if request["operation"] == "invoke":
                import hashlib

                challenge = request["payload"]["challenge"]
                payload = {
                    "challenge_digest": "sha256:" + hashlib.sha256(challenge.encode()).hexdigest()
                }
            else:
                payload = None
            return SimpleNamespace(
                returncode=0,
                stdout=json.dumps(
                    {
                        "ok": True,
                        "protocol": "io.tobkiri.packvm-supervisor.v1",
                        "build_id": "tobkiri-packvm-runner-1",
                        **({"payload": payload} if payload is not None else {}),
                    }
                ),
                stderr="",
            )
        raise AssertionError(argv)


@pytest.fixture
def provisioner(tmp_path: Path):
    command = tmp_path / "limactl"
    command.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    command.chmod(0o755)
    instance_dir = tmp_path / PACKVM_LIMA_INSTANCE
    instance_dir.mkdir()
    fake = FakeLima(command, instance_dir)
    manager = PackVMLimaProvisioner(
        command_path=str(command),
        runner=fake,
        state_dir=tmp_path / "state",
        machine="arm64",
    )
    return manager, fake, command


def _request(plan, *, approve: bool = True) -> PackVMProvisioningRequest:
    return PackVMProvisioningRequest(
        plan_digest=plan.plan_digest,
        ceremony_nonce=plan.ceremony_nonce,
        confirmation=plan.confirmation,
        approve_image_download=approve,
    )


def test_fresh_provision_requires_download_approval_and_consumes_ceremony(
    provisioner,
) -> None:
    manager, fake, _command = provisioner
    plan = manager.prepare()
    assert plan.backend_id == PACKVM_BACKEND_ID
    assert plan.image_download_required is True
    assert plan.image_source.startswith("https://cloud-images.ubuntu.com/jammy/20260807/")
    assert plan.image_size_bytes > 600_000_000
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
    assert config["disk"] == "20GiB"
    assert config["mounts"] == []
    assert config["networks"] == []
    assert config["propagateProxyEnv"] is False
    assert config["images"][0]["digest"].startswith("sha256:")
    assert "provision" not in config


def test_provision_doctor_stop_and_cleanup_are_authenticated(provisioner) -> None:
    manager, fake, _command = provisioner
    plan = manager.prepare()
    doctor = manager.provision(_request(plan))

    assert doctor.ready is True
    assert doctor.backend_id == PACKVM_BACKEND_ID
    assert doctor.attestation_digest
    assert manager.doctor().ready is True
    manager.stop()
    assert manager.doctor().ready is False
    fake.running = True
    with pytest.raises(ValueError, match="exact confirmation"):
        manager.cleanup("DELETE something-else")
    manager.cleanup(f"DELETE {PACKVM_LIMA_INSTANCE}")
    assert not manager.state_path.exists()
    assert fake.exists is False


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
    with pytest.raises(ValueError, match="install failed"):
        manager.provision(_request(plan))
    assert fake.exists is False
    assert fake.running is False
    assert not manager.state_path.exists()
    assert "provision_failed" in manager.audit_path.read_text(encoding="utf-8")


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
