from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import types
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

_DIAGNOSTIC_ENV_KEYS = (
    "DEFAULTS_HTTP_HOST",
    "DEFAULTS_HTTP_PORT",
    "RUMI_DEFAULTSPACK_OPEN_BROWSER",
    "RUMI_DEFAULTSPACK_PORT",
    "RUMI_DEFAULTSPACK_SURFACE",
    "RUMI_LOG_DIR",
    "RUMI_PROFILE_SURFACE",
    "RUMI_USER_DATA",
)


def _pack_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _ensure_import_path() -> None:
    pack_root = _pack_root()
    configured_roots = (
        os.environ.get("RUMI_APP_DIR"),
        os.environ.get("RUMI_CORE_DIR"),
        os.environ.get("REPO"),
    )
    for path in (
        pack_root,
        pack_root.parents[1],
        *(Path(root) for root in configured_roots if root),
    ):
        root = str(path)
        if root not in sys.path:
            sys.path.insert(0, root)
    _install_ecosystem_defaultspack_alias(pack_root)


def _install_ecosystem_defaultspack_alias(pack_root: Path) -> None:
    """Expose a managed pack root as ecosystem.defaultspack.

    Repo installs naturally import ``ecosystem.defaultspack`` via
    ``rumi_ai_1_10/ecosystem/defaultspack``. Managed pack versions live under
    user-data without that parent ``ecosystem`` directory, but some legacy
    modules still import the canonical package path.
    """
    ecosystem_dirs = _candidate_ecosystem_dirs(pack_root)
    ecosystem = sys.modules.get("ecosystem")
    if ecosystem is None:
        ecosystem = types.ModuleType("ecosystem")
        ecosystem.__path__ = [str(path) for path in ecosystem_dirs]  # type: ignore[attr-defined]
        sys.modules["ecosystem"] = ecosystem
    elif not hasattr(ecosystem, "__path__"):
        ecosystem.__path__ = [str(path) for path in ecosystem_dirs]  # type: ignore[attr-defined]
    else:
        paths = list(getattr(ecosystem, "__path__", []))
        for ecosystem_dir in ecosystem_dirs:
            ecosystem_path = str(ecosystem_dir)
            if ecosystem_path not in paths:
                paths.insert(0, ecosystem_path)
        ecosystem.__path__ = paths  # type: ignore[attr-defined]

    defaultspack = sys.modules.get("ecosystem.defaultspack")
    pack_path = str(pack_root)
    if defaultspack is None:
        defaultspack = types.ModuleType("ecosystem.defaultspack")
        defaultspack.__path__ = [pack_path]  # type: ignore[attr-defined]
        defaultspack.__package__ = "ecosystem.defaultspack"
        sys.modules["ecosystem.defaultspack"] = defaultspack
    else:
        paths = list(getattr(defaultspack, "__path__", []))
        if pack_path not in paths:
            paths.insert(0, pack_path)
            defaultspack.__path__ = paths  # type: ignore[attr-defined]
    setattr(ecosystem, "defaultspack", defaultspack)


def _candidate_ecosystem_dirs(pack_root: Path) -> list[Path]:
    candidates: list[Path] = []

    if pack_root.parent.name == "ecosystem":
        candidates.append(pack_root.parent)

    for root in (
        os.environ.get("RUMI_APP_DIR"),
        os.environ.get("RUMI_CORE_DIR"),
        os.environ.get("REPO"),
    ):
        if root:
            candidates.append(Path(root) / "ecosystem")

    for entry in sys.path:
        if entry:
            candidates.append(Path(entry) / "ecosystem")

    resolved: list[Path] = []
    seen: set[str] = set()
    for candidate in candidates:
        try:
            path = candidate.resolve()
        except OSError:
            path = candidate
        key = str(path)
        if key in seen or not candidate.exists() or not candidate.is_dir():
            continue
        seen.add(key)
        resolved.append(candidate)
    return resolved


def _url() -> str:
    port = os.environ.get("RUMI_DEFAULTSPACK_PORT") or os.environ.get("DEFAULTS_HTTP_PORT") or "8766"
    return f"http://localhost:{port}/chat"


def _diagnostic_log_path() -> Path:
    explicit = os.environ.get("RUMI_DEFAULTSPACK_LAUNCH_LOG")
    if explicit:
        return Path(explicit).expanduser()

    log_dir = os.environ.get("RUMI_LOG_DIR")
    if log_dir:
        return Path(log_dir).expanduser() / "defaultspack-launch.jsonl"

    user_data = os.environ.get("RUMI_USER_DATA")
    if user_data:
        return Path(user_data).expanduser().parent / "logs" / "defaultspack-launch.jsonl"

    return Path(tempfile.gettempdir()) / "rumi-defaultspack-launch.jsonl"


def _safe_cwd() -> str:
    try:
        return str(Path.cwd())
    except OSError:
        return "<unavailable>"


def _diagnostic_env() -> dict[str, str]:
    return {key: value for key in _DIAGNOSTIC_ENV_KEYS if (value := os.environ.get(key))}


def _write_launch_event(event: str, **fields: object) -> None:
    payload = {
        "ts": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "event": event,
        "pid": os.getpid(),
        "ppid": os.getppid(),
        "cwd": _safe_cwd(),
        **fields,
    }
    try:
        path = _diagnostic_log_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=True, sort_keys=True) + "\n")
    except Exception:
        # Launch diagnostics must never make the user-facing app fail to open.
        pass


def _port_owner_snapshot(port: str) -> list[dict[str, str]]:
    if not port.isdigit():
        return []
    try:
        result = subprocess.run(
            ["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-F", "pcL"],
            check=False,
            capture_output=True,
            text=True,
            timeout=1.0,
        )
    except Exception:
        return []
    if result.returncode != 0 or not result.stdout:
        return []

    owners: list[dict[str, str]] = []
    current: dict[str, str] = {}
    for raw_line in result.stdout.splitlines():
        if not raw_line:
            continue
        key, value = raw_line[0], raw_line[1:]
        if key == "p":
            if current:
                owners.append(current)
            current = {"pid": value}
        elif key == "c":
            current["command"] = value
        elif key == "L":
            current["user"] = value
    if current:
        owners.append(current)
    return owners


def _port_from_url(url: str) -> str:
    try:
        return url.split(":", 2)[2].split("/", 1)[0]
    except IndexError:
        return ""


def _wait_until_ready(url: str, timeout: float = 10.0) -> bool:
    deadline = time.time() + timeout
    health_url = url.split("/chat", 1)[0].rstrip("/") + "/api/health"
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(health_url, timeout=1.0) as response:
                return 200 <= response.status < 300
        except (OSError, urllib.error.URLError):
            time.sleep(0.2)
    return False


def _wait_until_chat_ready(url: str, timeout: float = 10.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1.0) as response:
                body = response.read(2048).decode("utf-8", "ignore")
                if 200 <= response.status < 300 and ("<title>" in body or 'id="root"' in body):
                    return True
        except (OSError, urllib.error.URLError):
            time.sleep(0.2)
    return False


def main() -> int:
    _ensure_import_path()
    os.environ.setdefault("DEFAULTS_HTTP_HOST", "127.0.0.1")
    os.environ.setdefault("DEFAULTS_HTTP_PORT", os.environ.get("RUMI_DEFAULTSPACK_PORT", "8766"))
    os.environ.setdefault("RUMI_DEFAULTSPACK_PORT", os.environ["DEFAULTS_HTTP_PORT"])
    url = _url()
    port = _port_from_url(url)
    _write_launch_event(
        "start",
        env=_diagnostic_env(),
        log_path=str(_diagnostic_log_path()),
        port=port,
        url=url,
    )
    try:
        from domain.integrations.secrets import load_integration_secrets_into_env

        load_integration_secrets_into_env()
    except Exception as exc:
        _write_launch_event("secrets_load_skipped", error=repr(exc), port=port, url=url)
    try:
        from domain.scheduler.daemon import start_scheduler_daemon

        start_scheduler_daemon()
    except Exception as exc:
        _write_launch_event("scheduler_start_skipped", error=repr(exc), port=port, url=url)

    from transport.http import DefaultsHttpServer

    server = DefaultsHttpServer(facade=None)
    reused_existing_server = False
    try:
        _write_launch_event("server_start_attempt", port=port, url=url)
        server.start()
        _write_launch_event("server_started", port=port, url=url)
    except OSError as exc:
        existing_ready = _wait_until_ready(url, timeout=1.0)
        _write_launch_event(
            "server_start_oserror",
            error=repr(exc),
            existing_ready=existing_ready,
            port=port,
            port_owners=_port_owner_snapshot(port),
            url=url,
        )
        if not existing_ready:
            raise
        server = None
        reused_existing_server = True

    health_ready = _wait_until_ready(url)
    chat_ready = _wait_until_chat_ready(url)
    _write_launch_event(
        "readiness_complete",
        chat_ready=chat_ready,
        health_ready=health_ready,
        port=port,
        url=url,
    )

    from defaultspack.native_webview import open_desktop_surface

    surface_result = open_desktop_surface(url, title="Rumi Defaultspack")
    _write_launch_event(
        "surface_opened",
        port=port,
        reused_existing_server=reused_existing_server,
        surface_result=surface_result,
        url=url,
    )
    if surface_result == "webview":
        if server is not None:
            server.stop()
            _write_launch_event("server_stopped_after_webview", port=port, url=url)
        return 0
    if server is None:
        _write_launch_event("duplicate_launcher_exit", port=port, url=url)
        return 0

    stop = False

    def _handle_signal(_signum, _frame):
        nonlocal stop
        stop = True

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    try:
        while not stop:
            time.sleep(0.5)
    finally:
        if server is not None:
            server.stop()
            _write_launch_event("server_stopped", port=port, url=url)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
