"""Packaged Pack v4 bootstrap regression tests."""

from __future__ import annotations

import json
import socket
from pathlib import Path
from urllib.request import urlopen

from core_runtime.bootstrap.runtime import Kernel


def _free_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def test_public_kernel_bootstrap_reaches_runtime_ready_http(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """The canonical public bootstrap serves ready HTTP from isolated data."""
    port = _free_port()
    monkeypatch.setenv("RUMI_PORT", str(port))
    monkeypatch.setenv("RUMI_USER_DATA", str(tmp_path / "user_data"))
    monkeypatch.setenv("RUMI_LOG_DIR", str(tmp_path / "logs"))

    kernel = Kernel()
    try:
        kernel.run_startup_until("api_init")
        kernel.run_startup_remaining()
        with urlopen(f"http://127.0.0.1:{port}/health", timeout=5) as response:
            envelope = json.load(response)
        assert envelope["success"] is True
        assert envelope["data"]["panel_ready"] is True
        assert envelope["data"]["runtime_ready"] is True
    finally:
        kernel.shutdown()
