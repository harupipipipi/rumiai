from __future__ import annotations

import base64
import json
import struct

from ecosystem.defaultspack.backend.sandbox.sandbox_manager import SandboxManager


def _decode_data_uri(data_uri: str) -> bytes:
    prefix = "data:image/png;base64,"
    assert data_uri.startswith(prefix)
    return base64.b64decode(data_uri.removeprefix(prefix), validate=True)


def test_sandbox_registry_persists_instances_and_lifecycle(tmp_path):
    manager = SandboxManager(state_dir=tmp_path)

    created = manager.create(image="ubuntu:24.04", display=False)

    assert created["ok"] is True
    assert created["created"] is True
    assert created["status"] == "ready"
    sandbox_id = created["sandbox_id"]
    registry_path = tmp_path / "sandboxes.json"
    assert registry_path.is_file()

    reloaded = SandboxManager(state_dir=tmp_path)
    status = reloaded.status(sandbox_id)
    assert status["ok"] is True
    assert status["sandbox_id"] == sandbox_id
    assert status["image"] == "ubuntu:24.04"
    assert status["display"] is False
    assert status["status"] == "ready"

    destroyed = reloaded.destroy(sandbox_id)
    assert destroyed == {
        "ok": True,
        "destroyed": True,
        "sandbox_id": sandbox_id,
        "status": "destroyed",
    }

    lifecycle = SandboxManager(state_dir=tmp_path).status(sandbox_id)
    assert lifecycle["status"] == "destroyed"
    assert lifecycle["destroyed_at"] is not None
    assert lifecycle["updated_at"] >= lifecycle["created_at"]


def test_sandbox_screenshot_returns_deterministic_valid_png_data_uri(tmp_path):
    manager = SandboxManager(state_dir=tmp_path)
    sandbox_id = manager.create()["sandbox_id"]

    first = manager.screenshot(sandbox_id)
    second = manager.screenshot(sandbox_id)

    assert first["ok"] is True
    assert first["source"] == "local_fallback"
    assert first["gui_backend"] is False
    assert first["format"] == "png"
    assert first["mime_type"] == "image/png"
    assert first["screenshot"] == first["data_uri"]
    assert first["screenshot"] == second["screenshot"]
    assert first["base64"] == second["base64"]
    assert first["base64"] != "base64_placeholder"

    raw = _decode_data_uri(first["data_uri"])
    assert raw == base64.b64decode(first["base64"], validate=True)
    assert raw.startswith(b"\x89PNG\r\n\x1a\n")
    assert raw[12:16] == b"IHDR"
    width, height = struct.unpack("!II", raw[16:24])
    assert (width, height) == (2, 2)


def test_sandbox_not_found_and_destroyed_errors_are_clear(tmp_path):
    manager = SandboxManager(state_dir=tmp_path)

    missing = manager.screenshot("missing-sandbox")
    assert missing["ok"] is False
    assert missing["status_code"] == 404
    assert missing["code"] == "SANDBOX_NOT_FOUND"
    assert missing["sandbox_id"] == "missing-sandbox"
    assert "Sandbox not found" in missing["error"]

    sandbox_id = manager.create()["sandbox_id"]
    manager.destroy(sandbox_id)

    screenshot = manager.screenshot(sandbox_id)
    assert screenshot["ok"] is False
    assert screenshot["status_code"] == 409
    assert screenshot["code"] == "SANDBOX_NOT_RUNNING"
    assert screenshot["status"] == "destroyed"
    assert "destroyed" in screenshot["error"]

    click = manager.click(sandbox_id, 10, 20)
    assert click["ok"] is False
    assert click["status_code"] == 409
    assert click["code"] == "SANDBOX_NOT_RUNNING"


def test_sandbox_state_dir_env_override_is_used(monkeypatch, tmp_path):
    override = tmp_path / "local-state"
    monkeypatch.setenv("RUMI_DEFAULTSPACK_SANDBOX_STATE_DIR", str(override))

    manager = SandboxManager()
    sandbox_id = manager.create()["sandbox_id"]

    registry_path = override / "sandboxes.json"
    assert manager.registry_path == registry_path
    payload = json.loads(registry_path.read_text(encoding="utf-8"))
    assert sandbox_id in payload["instances"]
    assert SandboxManager().status(sandbox_id)["status"] == "ready"
