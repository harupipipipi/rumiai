from __future__ import annotations

import os
import signal
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path


def _pack_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _ensure_import_path() -> None:
    for path in (_pack_root(), _pack_root().parents[1]):
        root = str(path)
        if root not in sys.path:
            sys.path.insert(0, root)


def _url() -> str:
    port = os.environ.get("RUMI_DEFAULTSPACK_PORT") or os.environ.get("DEFAULTS_HTTP_PORT") or "8766"
    return f"http://127.0.0.1:{port}/"


def _wait_until_ready(url: str, timeout: float = 10.0) -> bool:
    deadline = time.time() + timeout
    health_url = url.rstrip("/") + "/api/health"
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
    if surface_result in {"disabled", "webview"}:
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
