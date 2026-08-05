"""Packaged Pack v4 bootstrap regression tests."""

from __future__ import annotations

import json
import socket
import urllib.error
from pathlib import Path
from urllib.request import Request, urlopen

import pytest

from core_runtime.bootstrap.runtime import Kernel
from core_runtime.bootstrap.profile_capture import capture_default_profile
from core_runtime.di_container import get_container
from tobkiri_host.broker import RequestBroker
from tobkiri_host.runtime import V4DispatchSession


def _free_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def test_public_kernel_first_start_requires_confirmed_defaults_transaction(
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
        remaining = kernel.run_startup_remaining()
        assert remaining["status"] == "setup_required"
        with urlopen(f"http://127.0.0.1:{port}/health", timeout=5) as response:
            envelope = json.load(response)
        assert envelope["success"] is True
        assert envelope["data"]["panel_ready"] is True
        assert envelope["data"]["runtime_ready"] is False

        with urlopen(
            f"http://127.0.0.1:{port}/api/setup/packs", timeout=5
        ) as response:
            setup = json.load(response)["data"]
        assert setup["state"] == "review_required"
        request = Request(
            f"http://127.0.0.1:{port}/api/setup/packs/install",
            method="POST",
            headers={"Content-Type": "application/json"},
            data=json.dumps(
                {
                    "setup_api_version": "io.tobkiri.setup-state.v4",
                    "operation_id": "defaults.activate",
                    "confirmed": True,
                    "confirmation": setup["recommended_default_profile"][
                        "confirmation"
                    ],
                }
            ).encode(),
        )
        with urlopen(request, timeout=5) as response:
            activated = json.load(response)["data"]
        assert activated["state"] == "active"
        assert activated["audit_receipt"]["state"] == "committed"
        assert activated["audit_receipt"]["activation_id"] == activated[
            "activation_id"
        ]
        with pytest.raises(urllib.error.HTTPError) as replay:
            urlopen(request, timeout=5)
        assert replay.value.code == 401
        with urlopen(f"http://127.0.0.1:{port}/health", timeout=5) as response:
            ready = json.load(response)["data"]
        assert ready["runtime_ready"] is True
    finally:
        kernel.shutdown()


def test_clean_bootstrap_captures_and_restarts_without_legacy_profile(
    tmp_path: Path,
    monkeypatch,
) -> None:
    """A fresh Host persists one exact Defaults activation and reloads it."""
    user_data = tmp_path / "clean-home"
    monkeypatch.setenv("TOBKIRI_USER_DATA", str(user_data))
    from core_runtime.bootstrap.profile_capture import (
        prepare_default_profile_confirmation,
    )

    first = capture_default_profile(
        confirmation=prepare_default_profile_confirmation()
    )
    restarted = capture_default_profile()

    assert first.activation == restarted.activation
    assert first.resolved.plan == restarted.resolved.plan
    assert first.resolved.profile["base"]["pack_id"] == "defaults-basepack"
    assert first.resolved.profile["shell"]["provider_id"] == "shell.tauri.default"
    providers = [
        binding
        for binding in first.resolved.plan["bindings"]
        if binding["contract_id"] == "conversation.turn.v1"
    ]
    assert len(providers) == 1
    assert not (user_data / "settings" / "startup_profiles.json").exists()

    kernel = Kernel()
    monkeypatch.setenv("RUMI_PORT", str(_free_port()))
    try:
        kernel.run_startup_until("api_init")
        session = get_container().get("v4_dispatch_session")
        assert isinstance(session, V4DispatchSession)
        assert isinstance(session.broker, RequestBroker)
        assert session.authority_control is not None
        assert session.profile_id == "defaults"
        assert session.plan_digest == first.resolved.plan["plan_digest"]
    finally:
        kernel.shutdown()
