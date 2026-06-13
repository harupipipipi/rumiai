#!/usr/bin/env python3
"""Run the README viewer-first launch path up to Defaultspack v2 readiness."""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable


KERNEL_HEALTH_URL = "http://127.0.0.1:8765/health"
DEFAULTSPACK_HEALTH_URL = "http://127.0.0.1:8766/api/health"
DEFAULTSPACK_CHAT_URL = "http://127.0.0.1:8766/chat"


def main() -> int:
    repo_root = Path(__file__).resolve().parents[2]
    temp_root = Path(os.environ.get("RUNNER_TEMP", repo_root / ".tmp")).resolve()
    smoke_root = temp_root / "readme-viewer-defaultspack-smoke"
    home_dir = smoke_root / "home"
    log_dir = smoke_root / "logs"
    venv_dir = repo_root / ".venv"
    tauri_log = log_dir / "cargo-tauri-dev.log"

    log_dir.mkdir(parents=True, exist_ok=True)
    home_dir.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    original_home = Path(env.get("HOME", str(Path.home()))).expanduser()
    env.setdefault("CARGO_HOME", str(original_home / ".cargo"))
    env.setdefault("RUSTUP_HOME", str(original_home / ".rustup"))
    env.update(
        {
            "HOME": str(home_dir),
            "RUMI_AUTO_APPROVE_LOCAL": "true",
            "RUMI_DEFAULTSPACK_OPEN_BROWSER": "0",
            "RUST_BACKTRACE": "1",
            "PYTHONUNBUFFERED": "1",
        }
    )
    env["PATH"] = prepend_path(venv_bin_dir(venv_dir), env.get("PATH", ""))

    preexisting_port_pids = port_listener_pids((8765, 8766))
    if preexisting_port_pids:
        details = ", ".join(f"{port}: {sorted(pids)}" for port, pids in sorted(preexisting_port_pids.items()))
        raise RuntimeError(f"README smoke requires free ports before launch ({details})")

    print("README smoke: starting `RUMI_AUTO_APPROVE_LOCAL=true cargo tauri dev`")
    process = start_tauri_dev(repo_root, env, tauri_log)
    try:
        wait_for_process_or_condition(
            process,
            lambda: kernel_runtime_ready(),
            timeout_seconds=600,
            description="kernel runtime_ready",
            log_path=tauri_log,
        )
        print("README smoke: kernel is runtime_ready")

        token_path = wait_for_desktop_token(home_dir, timeout_seconds=60)
        user_data_dir = token_path.parent / "user_data"
        if not user_data_dir.is_dir():
            raise RuntimeError(f"user_data directory was not created at {user_data_dir}")
        print(f"README smoke: desktop API token found at {token_path}")

        smoke_env = env.copy()
        smoke_env.update(
            {
                "RUMI_VIEWER_SMOKE_REPO_ROOT": str(repo_root),
                "RUMI_VIEWER_SMOKE_USER_DATA": str(user_data_dir),
                "RUMI_VIEWER_SMOKE_VENV_DIR": str(venv_dir),
            }
        )
        run(
            [
                "cargo",
                "test",
                "--locked",
                "readme_defaultspack_launch_smoke",
                "--",
                "--ignored",
                "--nocapture",
            ],
            cwd=repo_root / "rumi_viewer" / "src-tauri",
            env=smoke_env,
        )

        wait_for_json(
            DEFAULTSPACK_HEALTH_URL,
            lambda data: data.get("status") in {"ok", "healthy"} or data.get("success") is True,
            timeout_seconds=60,
            description="Defaultspack v2 /api/health",
        )
        wait_for_http_status(
            DEFAULTSPACK_CHAT_URL,
            timeout_seconds=60,
            description="Defaultspack v2 /chat",
        )
        print("README smoke: Defaultspack v2 is reachable at http://127.0.0.1:8766/chat")
        return 0
    except Exception as exc:
        print(f"README smoke failed: {exc}", file=sys.stderr)
        print_log_tail(tauri_log)
        return 1
    finally:
        terminate_process(process)
        cleanup_known_ports((8765, 8766), exclude=preexisting_port_pids)


def prepend_path(path: Path, current: str) -> str:
    return f"{path}{os.pathsep}{current}" if current else str(path)


def venv_bin_dir(venv_dir: Path) -> Path:
    return venv_dir / ("Scripts" if os.name == "nt" else "bin")


def start_tauri_dev(repo_root: Path, env: dict[str, str], log_path: Path) -> subprocess.Popen[bytes]:
    log_handle = log_path.open("wb")
    return subprocess.Popen(
        ["cargo", "tauri", "dev"],
        cwd=repo_root / "rumi_viewer",
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=log_handle,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )


def run(cmd: list[str], *, cwd: Path, env: dict[str, str]) -> None:
    print(f"+ {' '.join(cmd)}")
    subprocess.run(cmd, cwd=cwd, env=env, check=True)


def wait_for_process_or_condition(
    process: subprocess.Popen[bytes],
    condition: Callable[[], bool],
    *,
    timeout_seconds: float,
    description: str,
    log_path: Path,
) -> None:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if process.poll() is not None:
            print_log_tail(log_path)
            raise RuntimeError(f"`cargo tauri dev` exited before {description} (code {process.returncode})")
        if condition():
            return
        fatal_log_error = detect_tauri_dev_failure(log_path)
        if fatal_log_error:
            raise RuntimeError(f"`cargo tauri dev` failed before {description}: {fatal_log_error}")
        time.sleep(1)
    raise TimeoutError(f"Timed out waiting for {description}")


def detect_tauri_dev_failure(log_path: Path) -> str | None:
    if not log_path.exists():
        return None
    text = log_path.read_text(encoding="utf-8", errors="replace")
    fatal_markers = (
        'The "beforeDevCommand" terminated',
        "error: could not compile",
        "failed to build archive",
        "No space left on device",
    )
    for marker in fatal_markers:
        if marker in text:
            return marker
    return None


def kernel_runtime_ready() -> bool:
    try:
        data = fetch_json(KERNEL_HEALTH_URL, timeout=2)
    except Exception:
        return False
    payload = data.get("data") if isinstance(data.get("data"), dict) else data
    return bool(payload.get("runtime_ready") or payload.get("runtime_status") == "runtime_ready")


def wait_for_desktop_token(home_dir: Path, *, timeout_seconds: float) -> Path:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        matches = sorted(home_dir.rglob(".desktop_api_token"))
        for path in matches:
            try:
                if path.read_text(encoding="utf-8").strip():
                    return path
            except OSError:
                pass
        time.sleep(1)
    raise TimeoutError(f"Timed out waiting for .desktop_api_token under {home_dir}")


def wait_for_json(
    url: str,
    predicate: Callable[[dict[str, object]], bool],
    *,
    timeout_seconds: float,
    description: str,
) -> dict[str, object]:
    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            data = fetch_json(url, timeout=2)
            if predicate(data):
                return data
            last_error = RuntimeError(f"Unexpected response from {url}: {data}")
        except Exception as exc:
            last_error = exc
        time.sleep(1)
    raise TimeoutError(f"Timed out waiting for {description}: {last_error}")


def wait_for_http_status(url: str, *, timeout_seconds: float, description: str) -> int:
    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=2) as response:
                if 200 <= response.status < 400:
                    return response.status
                last_error = RuntimeError(f"HTTP {response.status} from {url}")
        except Exception as exc:
            last_error = exc
        time.sleep(1)
    raise TimeoutError(f"Timed out waiting for {description}: {last_error}")


def fetch_json(url: str, *, timeout: float) -> dict[str, object]:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        body = response.read().decode("utf-8")
    data = json.loads(body)
    if not isinstance(data, dict):
        raise RuntimeError(f"Expected JSON object from {url}, got {type(data).__name__}")
    return data


def terminate_process(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except Exception:
        process.terminate()
    try:
        process.wait(timeout=15)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except Exception:
            process.kill()
        process.wait(timeout=10)


def port_listener_pids(ports: tuple[int, ...]) -> dict[int, set[int]]:
    listeners: dict[int, set[int]] = {}
    if shutil.which("lsof") is None:
        return listeners
    for port in ports:
        result = subprocess.run(
            ["lsof", "-ti", f"tcp:{port}"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            check=False,
        )
        pids = {int(raw_pid) for raw_pid in result.stdout.splitlines() if raw_pid.strip().isdigit()}
        if pids:
            listeners[port] = pids
    return listeners


def cleanup_known_ports(ports: tuple[int, ...], *, exclude: dict[int, set[int]]) -> None:
    listeners = port_listener_pids(ports)
    for port, pids in listeners.items():
        excluded = exclude.get(port, set())
        for pid in sorted(pids - excluded):
            try:
                os.kill(pid, signal.SIGTERM)
            except Exception:
                pass


def print_log_tail(path: Path, *, max_lines: int = 120) -> None:
    if not path.exists():
        print(f"Log file not found: {path}")
        return
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    print(f"--- tail {path} ---")
    for line in lines[-max_lines:]:
        print(line)
    print(f"--- end tail {path} ---")


if __name__ == "__main__":
    raise SystemExit(main())
