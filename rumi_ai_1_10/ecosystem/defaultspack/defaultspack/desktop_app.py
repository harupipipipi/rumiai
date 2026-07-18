from __future__ import annotations

import argparse
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
    # The HTTP server itself is loopback-only.  Do not hand the desktop
    # surface a hostname which might resolve to IPv6 (or another address) in
    # a debug run while the server is bound to IPv4 loopback.
    port = os.environ.get("DEFAULTS_HTTP_PORT") or os.environ.get("RUMI_DEFAULTSPACK_PORT") or "8766"
    return f"http://127.0.0.1:{port}/chat"


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


def _require_own_bind() -> bool:
    """Return whether this process must prove that it owns its HTTP listener.

    Debug isolation is intentionally fail-closed: attaching a new smoke run
    to an already-running server would mix approval/audit state across runs.
    The explicit flag is also useful for a harness which does not otherwise
    need the rest of the debug-isolation environment.
    """

    return (
        os.environ.get("RUMI_DEFAULTSPACK_REQUIRE_OWN_BIND") == "1"
        or os.environ.get("RUMI_DEFAULTSPACK_DEBUG_ISOLATION") == "1"
    )


def _configure_http_environment() -> None:
    """Normalize the two legacy port variables before constructing the server."""

    port = (
        os.environ.get("RUMI_DEFAULTSPACK_PORT")
        or os.environ.get("DEFAULTS_HTTP_PORT")
        or "8766"
    )
    os.environ.setdefault("DEFAULTS_HTTP_HOST", "127.0.0.1")
    os.environ["DEFAULTS_HTTP_PORT"] = port
    os.environ["RUMI_DEFAULTSPACK_PORT"] = port

    if not _require_own_bind():
        return
    if os.environ["DEFAULTS_HTTP_HOST"] != "127.0.0.1":
        raise RuntimeError(
            "RUMI_DEFAULTSPACK_REQUIRE_OWN_BIND requires DEFAULTS_HTTP_HOST=127.0.0.1"
        )
    if not port.isascii() or not port.isdecimal() or not 1 <= int(port) <= 65535:
        raise RuntimeError(
            "RUMI_DEFAULTSPACK_REQUIRE_OWN_BIND requires a decimal localhost port between 1 and 65535"
        )


def _parse_cli_args(argv: list[str]) -> None:
    """Parse command-line arguments before any runtime setup or imports."""

    parser = argparse.ArgumentParser(description="Launch the Rumi Defaultspack desktop app.")
    parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    # ``main()`` is also used as a library entry point in focused tests and
    # launch integrations.  Only the script entry point supplies argv; this
    # preserves that API while ensuring ``desktop_app.py --help`` has no
    # scheduler, secret-loader, HTTP-server, or surface side effects.
    if argv is not None:
        _parse_cli_args(argv)
    _ensure_import_path()
    _configure_http_environment()
    try:
        from domain.integrations.secrets import load_integration_secrets_into_env

        load_integration_secrets_into_env()
    except Exception:
        pass
    from transport.http import DefaultsHttpServer

    url = _url()
    server = DefaultsHttpServer(facade=None)
    try:
        server.start()
    except OSError:
        # A debug-isolated run must never adopt a healthy listener from some
        # other worktree/run.  Its harness owns the selected port and treats a
        # bind conflict as a retryable, fail-closed startup failure.
        if _require_own_bind():
            raise
        if not _wait_until_ready(url, timeout=1.0):
            raise
        server = None
    _wait_until_ready(url)

    # Do not start the scheduler if the process failed to claim its HTTP
    # listener.  In the legacy shared-port mode this remains after the
    # compatibility readiness fallback above.
    try:
        from domain.scheduler.daemon import start_scheduler_daemon

        start_scheduler_daemon()
    except Exception:
        pass

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
    raise SystemExit(main(sys.argv[1:]))
