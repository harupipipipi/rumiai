from __future__ import annotations

import hashlib
import hmac
import json
import os
import platform
import secrets
import shutil
import stat
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Mapping, Sequence

import yaml  # type: ignore[import-untyped]

from core_runtime.bounded_process_runner import (
    HostBoundedProcessRunner,
    ProcessExecutionPolicy,
)
from core_runtime.hmac_key_manager import generate_or_load_signing_key


LimaRunner = Callable[[Sequence[str], str | None, float | None], Any]
DiskUsage = Callable[[Path], Any]


DEFAULT_LIMA_INSTANCE = "rumi-managed-runtime"
PACKVM_LIMA_INSTANCE = "tobkiri-packvm-v4"
LIMA_STATE_VERSION = 1
LIMA_CONFIG_POLICY_VERSION = 4
LIMA_STATE_ENV = "RUMI_SANDBOX_LIMA_STATE"
MAX_LIMA_STATE_BYTES = 64 * 1024
LIMA_GUEST_WORKSPACE_ROOT = "/var/lib/rumi/workspaces"
LIMA_GUEST_PACK_DATA_ROOT = "/var/lib/rumi/pack-data"
PACKVM_BACKEND_ID = "tobkiri.python-pack-v4"
PACKVM_GUEST_RUNNER = "/usr/local/libexec/tobkiri-packvm-supervisor"
PACKVM_PROTOCOL = "io.tobkiri.packvm-supervisor.v1"
PACKVM_ATTESTATION_VERSION = 2
PACKVM_CONFIRMATION_PREFIX = "PROVISION"
PACKVM_STOP_PREFIX = "STOP"
PACKVM_CLEANUP_PREFIX = "DELETE"
MAX_PACKVM_ARTIFACT_REQUEST_BYTES = 700 * 1024 * 1024
PACKVM_PINNED_IMAGE_VIRTUAL_SIZE_BYTES = 2_361_393_152
PACKVM_ARTIFACT_STORAGE_BUDGET_BYTES = 768 * 1024 * 1024
PACKVM_GUEST_FREE_RESERVE_BYTES = 512 * 1024 * 1024
PACKVM_SYSTEM_GROWTH_BUDGET_BYTES = 512 * 1024 * 1024
PACKVM_MIN_DISK_SIZE_BYTES = (
    PACKVM_PINNED_IMAGE_VIRTUAL_SIZE_BYTES
    + PACKVM_ARTIFACT_STORAGE_BUDGET_BYTES
    + PACKVM_GUEST_FREE_RESERVE_BYTES
    + PACKVM_SYSTEM_GROWTH_BUDGET_BYTES
)
PACKVM_DISK_SIZE_BYTES = 4 * 1024 * 1024 * 1024
PACKVM_HOST_STORAGE_RESERVE_BYTES = 512 * 1024 * 1024
_PACKVM_RESOURCE_ROOT = Path(__file__).with_name("resources")
_PACKVM_CONFIG = _PACKVM_RESOURCE_ROOT / "packvm-lima.v1.yaml"
_PACKVM_RUNNER = _PACKVM_RESOURCE_ROOT / "packvm_guest_runner.py"
_PACKVM_IMAGES = {
    "arm64": {
        "lima_arch": "aarch64",
        "url": "https://cloud-images.ubuntu.com/jammy/20260807/jammy-server-cloudimg-arm64.img",
        "digest": "sha256:b17d9ac9b6249ab30f8c95630acdab3b7a51d76050229ab0ce6c013e303f5ccd",
        "size_bytes": 703_594_496,
        "virtual_size_bytes": PACKVM_PINNED_IMAGE_VIRTUAL_SIZE_BYTES,
    },
    "amd64": {
        "lima_arch": "x86_64",
        "url": "https://cloud-images.ubuntu.com/jammy/20260807/jammy-server-cloudimg-amd64.img",
        "digest": "sha256:ff271290a23279ce764561dbe2e9c3ec29da899535b571a987c37b47970c2ad9",
        "size_bytes": 734_327_808,
        "virtual_size_bytes": PACKVM_PINNED_IMAGE_VIRTUAL_SIZE_BYTES,
    },
}


@dataclass(frozen=True)
class PackVMProvisioningPlan:
    """User-visible, immutable facts for one explicit provisioning ceremony."""

    backend_id: str
    instance: str
    limactl: str | None
    launcher_reason: str | None
    architecture: str
    image_source: str
    image_digest: str
    image_size_bytes: int
    image_download_required: bool
    image_cache_status: str
    image_cache_reason: str | None
    disk_size_bytes: int
    host_free_space_required_bytes: int
    host_free_space_available_bytes: int
    host_free_space_reason: str | None
    config_digest: str
    guest_runner_digest: str
    host_build_digest: str
    ceremony_nonce: str
    plan_digest: str
    confirmation: str


@dataclass(frozen=True)
class PackVMProvisioningRequest:
    """Typed user/setup authorization for one exact provisioning plan."""

    plan_digest: str
    ceremony_nonce: str
    confirmation: str
    approve_image_download: bool = False


@dataclass(frozen=True)
class PackVMDoctor:
    """Fail-closed health status for the managed PackVM supervisor."""

    ready: bool
    backend_id: str
    platform: str
    instance: str
    reason: str | None = None
    attestation_digest: str | None = None


def lima_state_path() -> Path:
    configured = str(os.environ.get(LIMA_STATE_ENV) or "").strip()
    if configured:
        return Path(configured).expanduser()
    user_data = str(os.environ.get("RUMI_USER_DATA") or "").strip()
    if user_data:
        root = Path(user_data).expanduser()
    else:
        root = Path(__file__).resolve().parents[5] / "user_data"
    return root / "sandbox" / "lima-runtime.json"


def save_lima_runtime_state(
    limactl: str,
    instance: str = DEFAULT_LIMA_INSTANCE,
    *,
    runner: LimaRunner | None = None,
) -> dict[str, Any]:
    payload = lima_instance_payload(limactl, instance, runner=runner)
    violation = validate_lima_instance_config(payload)
    if violation:
        raise ValueError(violation)
    state = {
        "version": LIMA_STATE_VERSION,
        "policy_version": LIMA_CONFIG_POLICY_VERSION,
        "instance": instance,
        "config_hash": stable_lima_config_hash(instance, payload),
    }
    path = lima_state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".lima-runtime-", suffix=".json", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(state, handle, ensure_ascii=False, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except OSError:
            pass
    return state


def load_lima_runtime_state() -> dict[str, Any]:
    path = lima_state_path()
    try:
        if path.stat().st_size > MAX_LIMA_STATE_BYTES:
            raise ValueError("Lima sandbox state file is too large")
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError("Lima sandbox has not been provisioned by Rumi") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("Lima sandbox state is unreadable") from exc
    if not isinstance(payload, dict):
        raise ValueError("Lima sandbox state is invalid")
    if payload.get("version") != LIMA_STATE_VERSION:
        raise ValueError("Lima sandbox state version is unsupported")
    if payload.get("policy_version") != LIMA_CONFIG_POLICY_VERSION:
        raise ValueError("Lima sandbox policy changed; provision the runtime again")
    return payload


def resolve_attested_lima_runtime() -> tuple[str, str]:
    limactl = resolve_limactl_path()
    if limactl is None:
        raise ValueError("Lima sandbox runtime is not installed; run `brew install lima`")
    state = load_lima_runtime_state()
    instance = str(state.get("instance") or "").strip()
    expected_hash = str(state.get("config_hash") or "").strip().lower()
    if not instance or not expected_hash:
        raise ValueError("Lima sandbox state is incomplete")
    payload = lima_instance_payload(limactl, instance)
    violation = validate_lima_instance_config(payload)
    if violation:
        raise ValueError(violation)
    current_hash = stable_lima_config_hash(instance, payload)
    if current_hash != expected_hash:
        raise ValueError("Lima sandbox config changed; provision the runtime again")
    if str(payload.get("status") or "").casefold() != "running":
        raise ValueError("Lima sandbox instance is not running")
    return limactl, instance


def resolve_limactl_path() -> str | None:
    """Find limactl for shell and Finder-launched macOS applications."""
    discovered = shutil.which("limactl")
    if discovered:
        return discovered
    for candidate in (
        Path("/opt/homebrew/bin/limactl"),
        Path("/usr/local/bin/limactl"),
    ):
        if candidate.is_file() and os.access(candidate, os.X_OK):
            return str(candidate)
    return None


def lima_instance_payload(
    limactl: str,
    instance: str,
    *,
    runner: LimaRunner | None = None,
) -> dict[str, Any]:
    if runner is None:
        executable = (
            str(Path(limactl).resolve()) if Path(limactl).is_absolute() else shutil.which(limactl)
        )
        if executable is None:
            raise ValueError("limactl is unavailable")
        argv = (executable, "list", instance, "--format", "json")
        cwd = Path.cwd().resolve()
        environment = {
            str(key): str(value)
            for key, value in os.environ.items()
            if isinstance(key, str)
            and isinstance(value, str)
            and key
            and "=" not in key
            and "\x00" not in key
            and "\x00" not in value
        }
        result = HostBoundedProcessRunner().run_local(
            argv=argv,
            cwd=cwd,
            stdin=None,
            timeout_seconds=10,
            environment=environment,
            policy=ProcessExecutionPolicy(
                allowed_executables=frozenset({argv[0]}),
                allowed_argv=(argv,),
                allowed_cwds=(cwd,),
                allowed_environment=frozenset(environment),
                max_stdin_bytes=1,
                max_stdout_bytes=MAX_LIMA_STATE_BYTES,
                max_stderr_bytes=MAX_LIMA_STATE_BYTES,
                max_timeout_seconds=10,
            ),
        )
        if result.timed_out:
            raise ValueError("limactl list timed out")
        proc = subprocess.CompletedProcess(
            args=list(argv),
            returncode=result.exit_code if result.exit_code is not None else 1,
            stdout=result.stdout,
            stderr=result.stderr or result.transport_error or "",
        )
    else:
        proc = runner((limactl, "list", instance, "--format", "json"), None, 10)
    if proc.returncode != 0:
        raise ValueError(_decode(proc.stderr) or "limactl list failed")
    try:
        payload = json.loads(_decode(proc.stdout))
    except json.JSONDecodeError as exc:
        raise ValueError("limactl returned invalid JSON") from exc
    if isinstance(payload, list):
        item = next(
            (
                candidate
                for candidate in payload
                if isinstance(candidate, dict)
                and str(candidate.get("name") or "").strip() == instance
            ),
            None,
        )
    else:
        item = payload
    if not isinstance(item, dict) or str(item.get("name") or "").strip() != instance:
        raise ValueError("Lima sandbox instance was not found")
    return _with_resolved_mounts(item, instance)


def validate_lima_instance_config(payload: Mapping[str, Any]) -> str | None:
    config = payload.get("config")
    if not isinstance(config, Mapping):
        return "Lima sandbox config is unavailable"
    if str(config.get("vmType") or payload.get("vmType") or "").casefold() != "vz":
        return "Lima sandbox must use the macOS Virtualization.framework driver"
    mounts = config.get("mounts")
    if mounts != []:
        return "Lima sandbox host mounts must be disabled"
    if config.get("networks") != []:
        return "Lima sandbox network attachments must be disabled"
    ssh = config.get("ssh")
    if not isinstance(ssh, Mapping) or ssh.get("forwardAgent") is not False:
        return "Lima sandbox SSH agent forwarding must be disabled"
    if ssh.get("forwardX11") is not False or ssh.get("forwardX11Trusted") is not False:
        return "Lima sandbox X11 forwarding must be disabled"
    containerd = config.get("containerd")
    if (
        not isinstance(containerd, Mapping)
        or containerd.get("system") is not False
        or containerd.get("user") is not False
    ):
        return "Lima sandbox containerd services must be disabled"
    if config.get("propagateProxyEnv") is not False:
        return "Lima sandbox host proxy propagation must be disabled"
    host_resolver = config.get("hostResolver")
    if not isinstance(host_resolver, Mapping) or host_resolver.get("enabled") is not False:
        return "Lima sandbox host resolver bridging must be disabled"
    port_forwards = config.get("portForwards")
    if not _all_guest_ports_ignored(port_forwards):
        return "Lima sandbox guest port forwarding must be disabled"
    return None


def stable_lima_config_hash(instance: str, payload: Mapping[str, Any]) -> str:
    config = payload.get("config")
    relevant = {
        "instance": instance,
        "arch": payload.get("arch"),
        "vmType": payload.get("vmType"),
        "config": config if isinstance(config, Mapping) else {},
    }
    encoded = json.dumps(
        relevant, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str
    )
    return hashlib.sha256(encoded.encode("utf-8", errors="replace")).hexdigest()


def build_guest_bwrap_argv(
    *,
    workspace: str,
    cwd: str,
    argv: Sequence[str],
    env: Mapping[str, str],
    network_enabled: bool,
    data_dir: str | None = None,
) -> tuple[str, ...]:
    workspace_path = PurePosixPath(workspace)
    workspace_root = PurePosixPath(LIMA_GUEST_WORKSPACE_ROOT)
    cwd_path = PurePosixPath(cwd)
    visible_workspace = PurePosixPath("/workspace")
    if (
        not workspace_path.is_absolute()
        or workspace_path.parent != workspace_root
        or workspace_path.name in {"", ".", ".."}
        or not cwd_path.is_absolute()
        or (cwd_path != visible_workspace and visible_workspace not in cwd_path.parents)
        or ".." in cwd_path.parts
    ):
        raise ValueError("guest sandbox paths must be absolute")
    if data_dir is not None:
        data_path = PurePosixPath(data_dir)
        if (
            not data_path.is_absolute()
            or data_path.parent != PurePosixPath(LIMA_GUEST_PACK_DATA_ROOT)
            or data_path.name in {"", ".", ".."}
        ):
            raise ValueError("guest Pack data path is outside the managed root")
    command = [
        "bwrap",
        "--die-with-parent",
        "--new-session",
        "--unshare-user",
        "--uid",
        "0",
        "--gid",
        "0",
        "--unshare-pid",
        "--unshare-ipc",
        "--unshare-uts",
    ]
    if not network_enabled:
        command.append("--unshare-net")
    command.extend(
        [
            "--ro-bind",
            "/",
            "/",
            "--dev",
            "/dev",
            "--proc",
            "/proc",
            "--tmpfs",
            "/tmp",
            "--tmpfs",
            "/home",
            "--tmpfs",
            "/run",
            "--bind",
            workspace,
            "/workspace",
        ]
    )
    if data_dir is not None:
        command.extend(("--bind", data_dir, "/data"))
    command.extend(("--tmpfs", LIMA_GUEST_WORKSPACE_ROOT))
    command.extend(("--tmpfs", LIMA_GUEST_PACK_DATA_ROOT))
    command.append("--clearenv")
    for key, value in sorted(env.items()):
        command.extend(("--setenv", str(key), str(value)))
    command.extend(("--chdir", cwd, "--"))
    command.extend(str(item) for item in argv)
    return tuple(command)


def _with_resolved_mounts(
    payload: Mapping[str, Any],
    instance: str,
) -> dict[str, Any]:
    """Fill omitted isolation fields from Lima's Host-owned instance YAML."""
    config = payload.get("config")
    missing_fields = {
        field
        for field in ("mounts", "networks")
        if not isinstance(config, Mapping) or field not in config
    }
    if not missing_fields:
        return dict(payload)
    instance_dir = Path(str(payload.get("dir") or ""))
    if not instance_dir.is_absolute() or instance_dir.name != instance or instance_dir.is_symlink():
        raise ValueError("Lima sandbox config attestation source is unavailable")
    config_path = instance_dir / "lima.yaml"
    try:
        metadata = config_path.lstat()
    except OSError as exc:
        raise ValueError("Lima sandbox config attestation source is unavailable") from exc
    if (
        not stat.S_ISREG(metadata.st_mode)
        or stat.S_ISLNK(metadata.st_mode)
        or metadata.st_size > MAX_LIMA_STATE_BYTES
        or (hasattr(os, "getuid") and metadata.st_uid != os.getuid())
    ):
        raise ValueError("Lima sandbox config attestation source is unsafe")
    try:
        raw_config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise ValueError("Lima sandbox config attestation source is invalid") from exc
    if not isinstance(raw_config, Mapping) or any(
        field not in raw_config for field in missing_fields
    ):
        raise ValueError("Lima sandbox config attestation is incomplete")
    resolved = dict(payload)
    resolved_config = dict(config) if isinstance(config, Mapping) else {}
    for field in missing_fields:
        resolved_config[field] = raw_config[field]
    resolved["config"] = resolved_config
    return resolved


def _all_guest_ports_ignored(value: Any) -> bool:
    if not isinstance(value, list) or not value:
        return False
    covers_all_ports = False
    for rule in value:
        if not isinstance(rule, Mapping):
            return False
        if rule.get("ignore") is not True:
            return False
        port_range = rule.get("guestPortRange")
        if not isinstance(port_range, list) or len(port_range) != 2:
            continue
        try:
            first_port = int(port_range[0])
            last_port = int(port_range[1])
        except (TypeError, ValueError):
            continue
        if first_port <= 1 and last_port >= 65535:
            covers_all_ports = True
    return covers_all_ports


def _decode(value: bytes | str | None) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value or "")


class PackVMLimaProvisioner:
    """Explicit, authenticated lifecycle for Tobkiri's dedicated Lima PackVM."""

    def __init__(
        self,
        *,
        command_path: str | None = None,
        runner: LimaRunner | None = None,
        state_dir: Path | None = None,
        machine: str | None = None,
        instance: str = PACKVM_LIMA_INSTANCE,
        disk_usage: DiskUsage | None = None,
    ) -> None:
        self._command_path = command_path
        self._runner = runner
        self._state_dir = (state_dir or lima_state_path().parent).resolve()
        self._machine = _normalize_packvm_machine(machine or platform.machine())
        self._instance = instance
        self._disk_usage = disk_usage or shutil.disk_usage
        self._pending: dict[str, str] = {}

    @property
    def state_path(self) -> Path:
        return self._state_dir / "packvm-lima-attestation.json"

    @property
    def audit_path(self) -> Path:
        return self._state_dir / "packvm-lima-audit.jsonl"

    def prepare(self) -> PackVMProvisioningPlan:
        """Return download and identity facts without creating or starting a VM."""
        image = _PACKVM_IMAGES[self._machine]
        limactl = self._resolve_command()
        config = self._rendered_config()
        image_cache_status, image_cache_reason = self._pinned_image_cache_status()
        image_download_required = not self._instance_exists(limactl) and (
            image_cache_status == "absent"
        )
        required_space = self._required_host_space(image_download_required)
        available_space, storage_reason = self._host_free_space(required_space)
        nonce = secrets.token_hex(16)
        facts = {
            "backend_id": PACKVM_BACKEND_ID,
            "instance": self._instance,
            "limactl_digest": _file_digest(Path(limactl)) if limactl else None,
            "architecture": self._machine,
            "image_source": image["url"],
            "image_digest": image["digest"],
            "image_size_bytes": image["size_bytes"],
            "image_download_required": image_download_required,
            "image_cache_status": image_cache_status,
            "disk_size_bytes": PACKVM_DISK_SIZE_BYTES,
            "host_free_space_required_bytes": required_space,
            "config_digest": _sha256(config),
            "guest_runner_digest": _file_digest(_PACKVM_RUNNER),
            "host_build_digest": _file_digest(Path(__file__)),
            "ceremony_nonce": nonce,
        }
        plan_digest = _canonical_digest(facts)
        confirmation = f"{PACKVM_CONFIRMATION_PREFIX} {self._instance} {plan_digest[7:19]}"
        self._pending.clear()
        self._pending[nonce] = plan_digest
        return PackVMProvisioningPlan(
            backend_id=PACKVM_BACKEND_ID,
            instance=self._instance,
            limactl=limactl,
            launcher_reason=self._launcher_reason(limactl),
            architecture=self._machine,
            image_source=str(image["url"]),
            image_digest=str(image["digest"]),
            image_size_bytes=int(str(image["size_bytes"])),
            image_download_required=bool(facts["image_download_required"]),
            image_cache_status=image_cache_status,
            image_cache_reason=image_cache_reason,
            disk_size_bytes=PACKVM_DISK_SIZE_BYTES,
            host_free_space_required_bytes=required_space,
            host_free_space_available_bytes=available_space,
            host_free_space_reason=storage_reason,
            config_digest=str(facts["config_digest"]),
            guest_runner_digest=str(facts["guest_runner_digest"]),
            host_build_digest=str(facts["host_build_digest"]),
            ceremony_nonce=nonce,
            plan_digest=plan_digest,
            confirmation=confirmation,
        )

    def provision(self, request: PackVMProvisioningRequest) -> PackVMDoctor:
        """Create and attest the guest after consuming an exact ceremony once."""
        expected = self._pending.pop(request.ceremony_nonce, None)
        if expected is None or not hmac.compare_digest(expected, request.plan_digest):
            raise ValueError("PackVM provisioning ceremony is invalid or already consumed")
        plan = self._plan_for_consumed_nonce(request.ceremony_nonce)
        if plan.plan_digest != request.plan_digest:
            raise ValueError("PackVM provisioning plan changed; review it again")
        if not hmac.compare_digest(plan.confirmation, request.confirmation):
            raise ValueError("PackVM provisioning confirmation does not match")
        if plan.limactl is None:
            raise ValueError("limactl is unavailable; install approved Lima first")
        if plan.image_download_required and not request.approve_image_download:
            raise ValueError(
                "PackVM image download requires explicit approval for the displayed source, size, and digest"
            )
        if self.state_path.exists():
            raise ValueError("PackVM is already provisioned; use doctor or explicit cleanup")
        if self._instance_exists(plan.limactl):
            raise ValueError(
                "unattested managed Lima instance already exists; explicit cleanup is required"
            )
        current_cache_status, current_cache_reason = self._pinned_image_cache_status()
        if current_cache_status != plan.image_cache_status:
            raise ValueError("PackVM provisioning plan changed; review it again")
        if current_cache_status == "unsafe":
            raise ValueError(current_cache_reason or "PackVM image cache is unsafe")
        self._require_host_capacity(plan.image_download_required)

        self._state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        created = False
        try:
            with tempfile.NamedTemporaryFile(
                prefix=".packvm-lima-",
                suffix=".yaml",
                dir=self._state_dir,
                delete=False,
            ) as handle:
                config_path = Path(handle.name)
                handle.write(self._rendered_config())
            os.chmod(config_path, 0o600)
            try:
                self._checked_call(
                    (plan.limactl, "start", "--name", self._instance, str(config_path)),
                    timeout=900,
                )
                created = True
            finally:
                config_path.unlink(missing_ok=True)
            self._install_guest_runner(plan.limactl)
            machine_id = self._guest_machine_id(plan.limactl)
            runner_digest = self._guest_runner_digest(plan.limactl)
            if runner_digest != plan.guest_runner_digest:
                raise ValueError("guest supervisor binary verification failed")
            self._verify_guest_doctor(plan.limactl)
            payload = lima_instance_payload(
                plan.limactl,
                self._instance,
                runner=self._runner,
            )
            violation = validate_lima_instance_config(payload)
            if violation:
                raise ValueError(violation)
            state = {
                "version": PACKVM_ATTESTATION_VERSION,
                "backend_id": PACKVM_BACKEND_ID,
                "instance": self._instance,
                "instance_machine_id": machine_id,
                "instance_config_hash": stable_lima_config_hash(self._instance, payload),
                "config_digest": plan.config_digest,
                "image_digest": plan.image_digest,
                "limactl_digest": _file_digest(Path(plan.limactl)),
                "guest_runner_digest": runner_digest,
                "host_build_digest": plan.host_build_digest,
                "ceremony_nonce_digest": _sha256(request.ceremony_nonce.encode()),
                "created_unix": int(time.time()),
            }
            state["attestation_digest"] = _canonical_digest(state)
            state["authentication"] = self._sign_state(state)
            _atomic_private_json(self.state_path, state)
            self._audit("provisioned", str(state["attestation_digest"]))
            return self.doctor()
        except Exception:
            if created and plan.limactl:
                self._call((plan.limactl, "stop", "--force", self._instance), timeout=60)
                self._call((plan.limactl, "delete", "--force", self._instance), timeout=120)
            self._audit("provision_failed", None)
            raise

    def doctor(self) -> PackVMDoctor:
        """Authenticate Host state, VM identity, config, and guest runner health."""
        platform_id = f"macos-{self._machine}"
        try:
            limactl = self._require_command()
            state = self._load_authenticated_state()
            if state.get("limactl_digest") != _file_digest(Path(limactl)):
                raise ValueError("limactl binary changed after provisioning")
            if state.get("config_digest") != _sha256(self._rendered_config()):
                raise ValueError("managed PackVM pinned config changed")
            if state.get("image_digest") != _PACKVM_IMAGES[self._machine]["digest"]:
                raise ValueError("managed PackVM pinned image changed")
            if state.get("guest_runner_digest") != _file_digest(_PACKVM_RUNNER):
                raise ValueError("packaged PackVM guest supervisor changed")
            if state.get("host_build_digest") != _file_digest(Path(__file__)):
                raise ValueError("PackVM Host build changed after provisioning")
            payload = lima_instance_payload(limactl, self._instance, runner=self._runner)
            violation = validate_lima_instance_config(payload)
            if violation:
                raise ValueError(violation)
            if str(payload.get("status") or "").casefold() != "running":
                raise ValueError("managed PackVM instance is not running")
            if state.get("instance_config_hash") != stable_lima_config_hash(
                self._instance, payload
            ):
                raise ValueError("managed PackVM config changed")
            if state.get("instance_machine_id") != self._guest_machine_id(limactl):
                raise ValueError("managed PackVM instance identity changed")
            if state.get("guest_runner_digest") != self._guest_runner_digest(limactl):
                raise ValueError("managed PackVM guest supervisor changed")
            self._verify_guest_doctor(limactl)
            return PackVMDoctor(
                True,
                PACKVM_BACKEND_ID,
                platform_id,
                self._instance,
                attestation_digest=str(state["attestation_digest"]),
            )
        except (OSError, ValueError) as exc:
            return PackVMDoctor(
                False, PACKVM_BACKEND_ID, platform_id, self._instance, reason=str(exc)
            )

    def stop(self, confirmation: str) -> None:
        """Stop only the authenticated instance after exact confirmation."""
        self._load_authenticated_state()
        expected = f"{PACKVM_STOP_PREFIX} {self._instance}"
        if not hmac.compare_digest(confirmation, expected):
            raise ValueError(f"PackVM stop requires exact confirmation: {expected}")
        limactl = self._require_command()
        self._checked_call((limactl, "stop", "--force", self._instance), timeout=60)
        self._audit("stopped", None)

    def cleanup(self, confirmation: str) -> None:
        """Delete only the authenticated instance after an exact typed ceremony."""
        state = self._load_authenticated_state()
        expected = f"{PACKVM_CLEANUP_PREFIX} {self._instance}"
        if not hmac.compare_digest(confirmation, expected):
            raise ValueError(f"PackVM cleanup requires exact confirmation: {expected}")
        limactl = self._require_command()
        self._checked_call((limactl, "delete", "--force", self._instance), timeout=120)
        self._audit("deleted", str(state["attestation_digest"]))
        self.state_path.unlink(missing_ok=True)
        (self._state_dir / "packvm-lima-attestation.key").unlink(missing_ok=True)

    def invoke_guest(self, request: Mapping[str, Any]) -> Mapping[str, Any]:
        """Invoke only through the authenticated guest supervisor channel."""
        health = self.doctor()
        if not health.ready:
            raise ValueError(health.reason or "managed PackVM is unavailable")
        encoded = json.dumps(request, sort_keys=True, separators=(",", ":"))
        if len(encoded.encode()) > 1024 * 1024:
            raise ValueError("PackVM supervisor request is too large")
        result = self._checked_call(
            (
                self._require_command(),
                "shell",
                self._instance,
                "--",
                "sudo",
                "timeout",
                "--signal=TERM",
                "--kill-after=1s",
                "60s",
                PACKVM_GUEST_RUNNER,
            ),
            input_text=encoded,
            timeout=65,
        )
        response = json.loads(_decode(result.stdout))
        if not isinstance(response, dict) or response.get("protocol") != PACKVM_PROTOCOL:
            raise ValueError("PackVM supervisor returned an unauthenticated response")
        return response

    def materialize_artifact(self, request: Mapping[str, Any]) -> Mapping[str, Any]:
        """Stage one Host-captured artifact through the root-owned guest supervisor."""

        if request.get("operation") != "materialize":
            raise ValueError("PackVM artifact request operation is invalid")
        health = self.doctor()
        if not health.ready:
            raise ValueError(health.reason or "managed PackVM is unavailable")
        encoded = json.dumps(request, sort_keys=True, separators=(",", ":"))
        encoded_size = len(encoded.encode())
        if encoded_size > MAX_PACKVM_ARTIFACT_REQUEST_BYTES:
            raise ValueError("PackVM artifact request is too large")
        result = self._checked_call(
            (
                self._require_command(),
                "shell",
                self._instance,
                "--",
                "sudo",
                PACKVM_GUEST_RUNNER,
            ),
            input_text=encoded,
            timeout=180,
            max_stdin_bytes=MAX_PACKVM_ARTIFACT_REQUEST_BYTES,
        )
        response = json.loads(_decode(result.stdout))
        if not isinstance(response, dict) or response.get("protocol") != PACKVM_PROTOCOL:
            raise ValueError("PackVM supervisor returned an unauthenticated response")
        return response

    def _plan_for_consumed_nonce(self, nonce: str) -> PackVMProvisioningPlan:
        # Rebuild immutable facts while preserving the already reviewed nonce.
        image = _PACKVM_IMAGES[self._machine]
        limactl = self._resolve_command()
        config = self._rendered_config()
        image_cache_status, image_cache_reason = self._pinned_image_cache_status()
        image_download_required = not self._instance_exists(limactl) and (
            image_cache_status == "absent"
        )
        required_space = self._required_host_space(image_download_required)
        available_space, storage_reason = self._host_free_space(required_space)
        facts = {
            "backend_id": PACKVM_BACKEND_ID,
            "instance": self._instance,
            "limactl_digest": _file_digest(Path(limactl)) if limactl else None,
            "architecture": self._machine,
            "image_source": image["url"],
            "image_digest": image["digest"],
            "image_size_bytes": image["size_bytes"],
            "image_download_required": image_download_required,
            "image_cache_status": image_cache_status,
            "disk_size_bytes": PACKVM_DISK_SIZE_BYTES,
            "host_free_space_required_bytes": required_space,
            "config_digest": _sha256(config),
            "guest_runner_digest": _file_digest(_PACKVM_RUNNER),
            "host_build_digest": _file_digest(Path(__file__)),
            "ceremony_nonce": nonce,
        }
        digest = _canonical_digest(facts)
        return PackVMProvisioningPlan(
            backend_id=PACKVM_BACKEND_ID,
            instance=self._instance,
            limactl=limactl,
            launcher_reason=self._launcher_reason(limactl),
            architecture=self._machine,
            image_source=str(image["url"]),
            image_digest=str(image["digest"]),
            image_size_bytes=int(str(image["size_bytes"])),
            image_download_required=bool(facts["image_download_required"]),
            image_cache_status=image_cache_status,
            image_cache_reason=image_cache_reason,
            disk_size_bytes=PACKVM_DISK_SIZE_BYTES,
            host_free_space_required_bytes=required_space,
            host_free_space_available_bytes=available_space,
            host_free_space_reason=storage_reason,
            config_digest=str(facts["config_digest"]),
            guest_runner_digest=str(facts["guest_runner_digest"]),
            host_build_digest=str(facts["host_build_digest"]),
            ceremony_nonce=nonce,
            plan_digest=digest,
            confirmation=f"{PACKVM_CONFIRMATION_PREFIX} {self._instance} {digest[7:19]}",
        )

    def _rendered_config(self) -> bytes:
        image = _PACKVM_IMAGES[self._machine]
        gibibyte = 1024**3
        if (
            PACKVM_DISK_SIZE_BYTES < PACKVM_MIN_DISK_SIZE_BYTES
            or PACKVM_DISK_SIZE_BYTES % gibibyte != 0
        ):
            raise ValueError("PackVM disk policy is below the bounded runtime minimum")
        template = _PACKVM_CONFIG.read_text(encoding="utf-8")
        rendered = (
            template.replace("{{ARCH}}", str(image["lima_arch"]))
            .replace("{{IMAGE_URL}}", str(image["url"]))
            .replace("{{IMAGE_DIGEST}}", str(image["digest"]))
            .replace("{{DISK_SIZE_GIB}}", str(PACKVM_DISK_SIZE_BYTES // gibibyte))
        )
        return rendered.encode()

    def _required_host_space(self, image_download_required: bool) -> int:
        """Return the fail-closed host capacity needed for sparse VM growth."""

        image_bytes = int(str(_PACKVM_IMAGES[self._machine]["size_bytes"]))
        return (
            PACKVM_DISK_SIZE_BYTES
            + PACKVM_HOST_STORAGE_RESERVE_BYTES
            + PACKVM_PINNED_IMAGE_VIRTUAL_SIZE_BYTES
            + (image_bytes if image_download_required else 0)
        )

    def _host_storage_path(self) -> Path:
        """Return the volume on which Lima stores its managed instance."""

        home = str(os.environ.get("HOME") or "").strip()
        if not home:
            raise ValueError("PackVM host storage preflight cannot resolve the user home")
        path = Path(home).expanduser()
        while not path.exists() and path != path.parent:
            path = path.parent
        if not path.exists():
            raise ValueError("PackVM host storage preflight path is unavailable")
        return path

    def _pinned_image_cache_status(self) -> tuple[str, str | None]:
        """Classify the exact Lima cache entry without trusting converted metadata."""

        image = _PACKVM_IMAGES[self._machine]
        source = str(image["url"])
        expected_size = int(str(image["size_bytes"]))
        expected_digest = str(image["digest"])
        home = str(os.environ.get("HOME") or "").strip()
        if not home:
            return "absent", None
        cache_root = Path(home).expanduser() / "Library" / "Caches" / "lima"
        entry = (
            cache_root / "download" / "by-url-sha256" / hashlib.sha256(source.encode()).hexdigest()
        )
        try:
            entry_metadata = entry.lstat()
        except FileNotFoundError:
            return "absent", None
        except OSError as exc:
            return "unsafe", f"PackVM pinned image cache cannot be inspected: {exc}"
        if entry.is_symlink() or not stat.S_ISDIR(entry_metadata.st_mode):
            return "unsafe", "PackVM pinned image cache entry is not a regular directory"
        try:
            for directory in (
                cache_root,
                cache_root / "download",
                cache_root / "download" / "by-url-sha256",
                entry,
            ):
                metadata = directory.lstat()
                if directory.is_symlink() or not stat.S_ISDIR(metadata.st_mode):
                    return "unsafe", "PackVM pinned image cache path is unsafe"
                if hasattr(os, "getuid") and metadata.st_uid != os.getuid():
                    return "unsafe", "PackVM pinned image cache owner changed"
            url_path = entry / "url"
            data_path = entry / "data"
            for path, maximum in ((url_path, 4096), (data_path, expected_size)):
                metadata = path.lstat()
                if (
                    path.is_symlink()
                    or not stat.S_ISREG(metadata.st_mode)
                    or metadata.st_size > maximum
                    or (hasattr(os, "getuid") and metadata.st_uid != os.getuid())
                ):
                    return "unsafe", "PackVM pinned image cache file is unsafe"
            if data_path.stat().st_size != expected_size:
                return "unsafe", "PackVM pinned image cache size does not match"
            if url_path.read_text(encoding="utf-8") != source:
                return "unsafe", "PackVM pinned image cache source does not match"
            if not hmac.compare_digest(
                _stable_regular_file_digest(data_path, expected_size), expected_digest
            ):
                return "unsafe", "PackVM pinned image cache digest does not match"
            converted = entry / "imgconv" / "raw"
            converted_digest = entry / "imgconv" / "raw.digest"
            if (
                converted.exists()
                or converted.is_symlink()
                or converted_digest.exists()
                or converted_digest.is_symlink()
            ):
                return "unsafe", (
                    "PackVM pinned image cache contains a Lima-converted raw image "
                    "that is not independently bound to the pinned qcow2 digest"
                )
            return "verified_source", None
        except (OSError, UnicodeError, ValueError) as exc:
            return "unsafe", f"PackVM pinned image cache verification failed: {exc}"

    def _host_free_space(self, required_space: int) -> tuple[int, str | None]:
        """Measure host capacity and format a stable insufficiency diagnostic."""

        try:
            available = int(self._disk_usage(self._host_storage_path()).free)
        except (AttributeError, OSError, TypeError, ValueError) as exc:
            return 0, f"PackVM host storage preflight failed: {exc}"
        if available < required_space:
            return available, (
                "PackVM provisioning requires at least "
                f"{_format_gib(required_space)} free on the Lima host volume; "
                f"only {_format_gib(available)} is available"
            )
        return available, None

    def _require_host_capacity(self, image_download_required: bool) -> None:
        """Fail before Lima mutation when bounded host capacity is unavailable."""

        required = self._required_host_space(image_download_required)
        _available, reason = self._host_free_space(required)
        if reason is not None:
            raise ValueError(reason)

    def _resolve_command(self) -> str | None:
        if self._command_path is None and platform.system() != "Darwin":
            return None
        candidate = self._command_path or resolve_limactl_path()
        if candidate is None:
            return None
        path = Path(candidate)
        try:
            metadata = path.lstat()
        except OSError:
            return None
        if path.is_symlink():
            try:
                resolved = path.resolve(strict=True)
            except OSError:
                return None
            trusted_roots = (
                Path("/opt/homebrew/Cellar/lima"),
                Path("/usr/local/Cellar/lima"),
            )
            if path not in {
                Path("/opt/homebrew/bin/limactl"),
                Path("/usr/local/bin/limactl"),
            } or not any(resolved.is_relative_to(root) for root in trusted_roots):
                return None
            path = resolved
            try:
                metadata = path.lstat()
            except OSError:
                return None
        if not stat.S_ISREG(metadata.st_mode) or not os.access(path, os.X_OK):
            return None
        return str(path.resolve())

    def _launcher_reason(self, resolved: str | None) -> str | None:
        if resolved is not None:
            return None
        if self._command_path is None and platform.system() != "Darwin":
            return "Lima PackVM provisioning is available only on macOS"
        candidate = self._command_path or resolve_limactl_path()
        if candidate is None:
            return "limactl was not detected; install an approved pinned Lima launcher"
        return "limactl must be a regular executable or a trusted versioned Homebrew link"

    def _require_command(self) -> str:
        command = self._resolve_command()
        if command is None:
            raise ValueError("limactl is unavailable or is not a regular executable")
        return command

    def _instance_exists(self, limactl: str | None) -> bool:
        if limactl is None:
            return False
        result = self._call((limactl, "list", "--format", "{{.Name}}"), timeout=10)
        return result.returncode == 0 and self._instance in {
            line.strip() for line in _decode(result.stdout).splitlines()
        }

    def _install_guest_runner(self, limactl: str) -> None:
        script = _PACKVM_RUNNER.read_text(encoding="utf-8")
        self._checked_call(
            (
                limactl,
                "shell",
                self._instance,
                "--",
                "sudo",
                "install",
                "-o",
                "root",
                "-g",
                "root",
                "-m",
                "0755",
                "/dev/stdin",
                PACKVM_GUEST_RUNNER,
            ),
            input_text=script,
            timeout=30,
        )

    def _guest_machine_id(self, limactl: str) -> str:
        result = self._checked_call(
            (limactl, "shell", self._instance, "--", "cat", "/etc/machine-id"),
            timeout=10,
        )
        machine_id = _decode(result.stdout).strip()
        if len(machine_id) != 32 or any(char not in "0123456789abcdef" for char in machine_id):
            raise ValueError("managed PackVM machine identity is invalid")
        return machine_id

    def _guest_runner_digest(self, limactl: str) -> str:
        result = self._checked_call(
            (limactl, "shell", self._instance, "--", "sha256sum", PACKVM_GUEST_RUNNER),
            timeout=10,
        )
        value = _decode(result.stdout).split(maxsplit=1)[0].lower()
        if len(value) != 64 or any(char not in "0123456789abcdef" for char in value):
            raise ValueError("managed PackVM guest supervisor digest is invalid")
        return f"sha256:{value}"

    def _verify_guest_doctor(self, limactl: str) -> None:
        result = self._checked_call(
            (limactl, "shell", self._instance, "--", PACKVM_GUEST_RUNNER),
            input_text='{"operation":"doctor"}',
            timeout=10,
        )
        response = json.loads(_decode(result.stdout))
        if (
            not isinstance(response, dict)
            or response.get("ok") is not True
            or response.get("protocol") != PACKVM_PROTOCOL
        ):
            raise ValueError("managed PackVM guest supervisor doctor failed")
        challenge = secrets.token_hex(32)
        invoked = self._checked_call(
            (limactl, "shell", self._instance, "--", PACKVM_GUEST_RUNNER),
            input_text=json.dumps(
                {
                    "operation": "invoke",
                    "contract_id": "io.tobkiri.packvm.attestation.v1",
                    "operation_id": "challenge",
                    "payload": {"challenge": challenge},
                },
                sort_keys=True,
                separators=(",", ":"),
            ),
            timeout=10,
        )
        invoke_response = json.loads(_decode(invoked.stdout))
        expected_digest = _sha256(challenge.encode())
        if (
            not isinstance(invoke_response, dict)
            or invoke_response.get("ok") is not True
            or invoke_response.get("protocol") != PACKVM_PROTOCOL
            or not isinstance(invoke_response.get("payload"), dict)
            or invoke_response["payload"].get("challenge_digest") != expected_digest
        ):
            raise ValueError("managed PackVM guest supervisor invoke challenge failed")

    def _call(
        self,
        command: Sequence[str],
        *,
        input_text: str | None = None,
        timeout: float,
        max_stdin_bytes: int = 1024 * 1024,
    ) -> Any:
        if self._runner is not None:
            return self._runner(command, input_text, timeout)
        environment = {"PATH": "/usr/bin:/bin:/usr/sbin:/sbin:/opt/homebrew/bin:/usr/local/bin"}
        if "HOME" in os.environ:
            environment["HOME"] = os.environ["HOME"]
        argv = tuple(str(item) for item in command)
        cwd = Path.cwd().resolve()
        bounded_timeout = min(max(float(timeout), 1.0), 900.0)
        result = HostBoundedProcessRunner().run_local(
            argv=argv,
            cwd=cwd,
            stdin=input_text,
            timeout_seconds=bounded_timeout,
            environment=environment,
            policy=ProcessExecutionPolicy(
                allowed_executables=frozenset({argv[0]}),
                allowed_argv=(argv,),
                allowed_cwds=(cwd,),
                allowed_environment=frozenset(environment),
                max_stdin_bytes=max_stdin_bytes,
                max_stdout_bytes=MAX_LIMA_STATE_BYTES,
                max_stderr_bytes=MAX_LIMA_STATE_BYTES,
                max_timeout_seconds=bounded_timeout,
            ),
        )
        return subprocess.CompletedProcess(
            argv,
            result.exit_code if result.exit_code is not None else 1,
            result.stdout,
            result.stderr or result.transport_error or "",
        )

    def _checked_call(
        self,
        command: Sequence[str],
        *,
        timeout: float,
        input_text: str | None = None,
        max_stdin_bytes: int = 1024 * 1024,
    ) -> Any:
        result = self._call(
            command,
            input_text=input_text,
            timeout=timeout,
            max_stdin_bytes=max_stdin_bytes,
        )
        if result.returncode != 0:
            raise ValueError(_decode(result.stderr)[:1000] or f"command failed: {command[1]}")
        return result

    def _sign_state(self, state: Mapping[str, Any]) -> str:
        key_path = self._state_dir / "packvm-lima-attestation.key"
        key = generate_or_load_signing_key(key_path)
        unsigned = {key: value for key, value in state.items() if key != "authentication"}
        return hmac.new(key, _canonical_json(unsigned), hashlib.sha256).hexdigest()

    def _load_authenticated_state(self) -> dict[str, Any]:
        try:
            raw = _read_private_file(self.state_path, MAX_LIMA_STATE_BYTES)
        except FileNotFoundError as exc:
            raise ValueError("managed PackVM has not completed explicit provisioning") from exc
        try:
            state = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError("PackVM attestation state is invalid") from exc
        if not isinstance(state, dict) or state.get("version") != PACKVM_ATTESTATION_VERSION:
            raise ValueError("PackVM attestation state is unsupported")
        if state.get("backend_id") != PACKVM_BACKEND_ID or state.get("instance") != self._instance:
            raise ValueError("PackVM attestation is bound to another runtime")
        authentication = str(state.get("authentication") or "")
        key = _read_private_file(self._state_dir / "packvm-lima-attestation.key", 64)
        unsigned = {key: value for key, value in state.items() if key != "authentication"}
        expected = hmac.new(key, _canonical_json(unsigned), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(authentication, expected):
            raise ValueError("PackVM attestation authentication failed")
        attested = dict(unsigned)
        attestation_digest = str(attested.pop("attestation_digest", ""))
        if attestation_digest != _canonical_digest(attested):
            raise ValueError("PackVM attestation digest failed")
        return state

    def _audit(self, event: str, attestation_digest: str | None) -> None:
        self._state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
        record = {
            "event": event,
            "backend_id": PACKVM_BACKEND_ID,
            "instance": self._instance,
            "attestation_digest": attestation_digest,
            "timestamp_unix": int(time.time()),
        }
        with self.audit_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n")
        os.chmod(self.audit_path, 0o600)


def _normalize_packvm_machine(value: str) -> str:
    machine = {"aarch64": "arm64", "x86_64": "amd64", "AMD64": "amd64"}.get(value, value.lower())
    if machine not in _PACKVM_IMAGES:
        raise ValueError(f"unsupported PackVM architecture: {machine}")
    return machine


def _sha256(value: bytes) -> str:
    return f"sha256:{hashlib.sha256(value).hexdigest()}"


def _format_gib(value: int) -> str:
    return f"{value / (1024**3):.2f} GiB"


def _file_digest(path: Path) -> str:
    metadata = path.lstat()
    if path.is_symlink() or not stat.S_ISREG(metadata.st_mode):
        raise ValueError(f"attested file is not a regular file: {path.name}")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _stable_regular_file_digest(path: Path, expected_size: int) -> str:
    """Hash one unlinked regular file descriptor and reject concurrent changes."""

    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        before = os.fstat(descriptor)
        if (
            not stat.S_ISREG(before.st_mode)
            or before.st_size != expected_size
            or (hasattr(os, "getuid") and before.st_uid != os.getuid())
        ):
            raise ValueError("PackVM pinned image cache file is unsafe")
        digest = hashlib.sha256()
        with os.fdopen(descriptor, "rb", closefd=False) as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        after = os.fstat(descriptor)
        if (
            before.st_dev,
            before.st_ino,
            before.st_size,
            before.st_mtime_ns,
            before.st_ctime_ns,
        ) != (
            after.st_dev,
            after.st_ino,
            after.st_size,
            after.st_mtime_ns,
            after.st_ctime_ns,
        ):
            raise ValueError("PackVM pinned image cache changed during verification")
        return f"sha256:{digest.hexdigest()}"
    finally:
        os.close(descriptor)


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _canonical_digest(value: object) -> str:
    return _sha256(_canonical_json(value))


def _read_private_file(path: Path, maximum: int) -> bytes:
    metadata = path.lstat()
    if path.is_symlink() or not stat.S_ISREG(metadata.st_mode) or metadata.st_size > maximum:
        raise ValueError(f"unsafe PackVM state file: {path.name}")
    if metadata.st_mode & 0o077:
        raise ValueError(f"PackVM state permissions are too broad: {path.name}")
    if hasattr(os, "getuid") and metadata.st_uid != os.getuid():
        raise ValueError(f"PackVM state owner changed: {path.name}")
    return path.read_bytes()


def _atomic_private_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except OSError:
            pass


def _atomic_private_json(path: Path, payload: Mapping[str, Any]) -> None:
    _atomic_private_bytes(path, _canonical_json(payload) + b"\n")
