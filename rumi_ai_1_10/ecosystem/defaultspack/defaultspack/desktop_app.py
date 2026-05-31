from __future__ import annotations

import os
import signal
import sys
import time
import types
import urllib.error
import urllib.request
from pathlib import Path


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


def main() -> int:
    _ensure_import_path()
    os.environ.setdefault("DEFAULTS_HTTP_HOST", "127.0.0.1")
    os.environ.setdefault("DEFAULTS_HTTP_PORT", os.environ.get("RUMI_DEFAULTSPACK_PORT", "8766"))
    os.environ.setdefault("RUMI_DEFAULTSPACK_PORT", os.environ["DEFAULTS_HTTP_PORT"])
    try:
        from domain.integrations.secrets import load_integration_secrets_into_env

        load_integration_secrets_into_env()
    except Exception:
        pass
    try:
        from domain.scheduler.daemon import start_scheduler_daemon

        start_scheduler_daemon()
    except Exception:
        pass

    from transport.http import DefaultsHttpServer

    url = _url()
    server = DefaultsHttpServer(facade=None)
    try:
        server.start()
    except OSError:
        if not _wait_until_ready(url, timeout=1.0):
            raise
        server = None
    _wait_until_ready(url)

    from defaultspack.native_webview import open_desktop_surface

    surface_result = open_desktop_surface(url, title="Rumi Defaultspack")
    if surface_result == "webview":
        if server is not None:
            server.stop()
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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
