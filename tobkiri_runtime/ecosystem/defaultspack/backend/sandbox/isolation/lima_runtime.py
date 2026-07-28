from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any, Callable, Mapping, Sequence


LimaRunner = Callable[[Sequence[str], str | None, float | None], Any]


DEFAULT_LIMA_INSTANCE = "rumi-managed-runtime"
LIMA_STATE_VERSION = 1
LIMA_CONFIG_POLICY_VERSION = 2
LIMA_STATE_ENV = "RUMI_SANDBOX_LIMA_STATE"
MAX_LIMA_STATE_BYTES = 64 * 1024
LIMA_GUEST_WORKSPACE_ROOT = "/var/lib/rumi/workspaces"
LIMA_GUEST_PACK_DATA_ROOT = "/var/lib/rumi/pack-data"


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
        proc = subprocess.run(
            [limactl, "list", instance, "--format", "json"],
            capture_output=True,
            timeout=10,
            close_fds=True,
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
    return item


def validate_lima_instance_config(payload: Mapping[str, Any]) -> str | None:
    config = payload.get("config")
    if not isinstance(config, Mapping):
        return "Lima sandbox config is unavailable"
    if str(config.get("vmType") or payload.get("vmType") or "").casefold() != "vz":
        return "Lima sandbox must use the macOS Virtualization.framework driver"
    mounts = config.get("mounts")
    if mounts not in (None, []):
        return "Lima sandbox host mounts must be disabled"
    ssh = config.get("ssh")
    if not isinstance(ssh, Mapping) or ssh.get("forwardAgent") is not False:
        return "Lima sandbox SSH agent forwarding must be disabled"
    if (
        ssh.get("forwardX11") is not False
        or ssh.get("forwardX11Trusted") is not False
    ):
        return "Lima sandbox X11 forwarding must be disabled"
    containerd = config.get("containerd")
    if not isinstance(containerd, Mapping) or containerd.get("system") is not False or containerd.get("user") is not False:
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
    encoded = json.dumps(relevant, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
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
        or (
            cwd_path != visible_workspace
            and visible_workspace not in cwd_path.parents
        )
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
    if data_dir is not None:
        command.extend(("--tmpfs", LIMA_GUEST_PACK_DATA_ROOT))
    command.append("--clearenv")
    for key, value in sorted(env.items()):
        command.extend(("--setenv", str(key), str(value)))
    command.extend(("--chdir", cwd, "--"))
    command.extend(str(item) for item in argv)
    return tuple(command)


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
