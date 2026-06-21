from __future__ import annotations

import base64
import json
import struct

from ecosystem.defaultspack.backend.sandbox.gui_sandbox import GUISandbox
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
    assert status["provider_id"] == "local_compat"
    assert status["template_id"] == "tool.ephemeral"

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


def test_sandbox_destroy_marks_error_when_backend_teardown_fails(tmp_path):
    class Backend:
        def __init__(self):
            self.destroyed = []

        def create_session(self, title):
            return {"session_id": "backend-session-1"}

        def destroy_session(self, sandbox_id):
            self.destroyed.append(sandbox_id)
            return {"ok": False, "error": "teardown refused"}

    backend = Backend()
    manager = SandboxManager(state_dir=tmp_path, gui_backend=backend)
    sandbox_id = manager.create()["sandbox_id"]

    result = manager.destroy(sandbox_id)

    assert result["ok"] is False
    assert result["destroyed"] is False
    assert result["code"] == "SANDBOX_BACKEND_DESTROY_FAILED"
    assert result["status"] == "error"
    assert result["error"] == "teardown refused"
    assert backend.destroyed == [sandbox_id]

    persisted = SandboxManager(state_dir=tmp_path).status(sandbox_id)
    assert persisted["status"] == "error"
    assert persisted["destroyed_at"] is None
    assert persisted["last_error"] == "teardown refused"


def test_sandbox_input_actions_fail_closed_without_backend(tmp_path):
    manager = SandboxManager(state_dir=tmp_path)
    sandbox_id = manager.create()["sandbox_id"]

    click = manager.click(sandbox_id, 10, 20)
    typed = manager.type_text(sandbox_id, "hello")
    scroll = manager.scroll(sandbox_id, direction="up", amount=2)

    for result, action, success_key in (
        (click, "click", "clicked"),
        (typed, "type_text", "typed"),
        (scroll, "scroll", "scrolled"),
    ):
        assert result["ok"] is False
        assert result["code"] == "SANDBOX_BACKEND_UNAVAILABLE"
        assert result["status_code"] == 503
        assert result["sandbox_id"] == sandbox_id
        assert result["status"] == "ready"
        assert result["gui_backend"] is False
        assert result["action"] == action
        assert success_key not in result
        assert "recorded" not in result
        assert "backend unavailable" in result["error"]

    status = manager.status(sandbox_id)
    assert status["ok"] is True
    assert status["status"] == "ready"
    assert status["last_activity_at"] is None
    assert status["last_error"] is None


def test_sandbox_input_actions_route_to_backend_before_reporting_success(tmp_path):
    class Backend:
        def __init__(self):
            self.calls = []

        def click(self, sandbox_id, x, y):
            self.calls.append(("click", sandbox_id, x, y))
            return {"ok": True, "backend_action": "click"}

        def type_text(self, sandbox_id, text):
            self.calls.append(("type_text", sandbox_id, text))
            return {"ok": True, "backend_action": "type_text"}

        def scroll(self, sandbox_id, amount):
            self.calls.append(("scroll", sandbox_id, amount))
            return {"ok": True, "backend_action": "scroll"}

    backend = Backend()
    manager = SandboxManager(state_dir=tmp_path, gui_backend=backend)
    sandbox_id = manager.create()["sandbox_id"]

    click = manager.click(sandbox_id, 10, 20)
    typed = manager.type_text(sandbox_id, "hello")
    scroll = manager.scroll(sandbox_id, direction="up", amount=2)

    assert click["ok"] is True
    assert click["clicked"] is True
    assert click["gui_backend"] is True
    assert click["x"] == 10
    assert click["y"] == 20
    assert typed["ok"] is True
    assert typed["typed"] is True
    assert typed["text"] == "hello"
    assert scroll["ok"] is True
    assert scroll["scrolled"] is True
    assert scroll["direction"] == "up"
    assert scroll["amount"] == 2
    assert backend.calls == [
        ("click", sandbox_id, 10, 20),
        ("type_text", sandbox_id, "hello"),
        ("scroll", sandbox_id, 2),
    ]
    assert manager.status(sandbox_id)["last_activity_at"] is not None


def test_sandbox_manager_uses_gui_backend_session_for_input_actions(tmp_path):
    backend = GUISandbox()
    manager = SandboxManager(state_dir=tmp_path, gui_backend=backend)
    sandbox_id = manager.create()["sandbox_id"]

    result = manager.click(sandbox_id, 1, 2)

    assert result["ok"] is True
    assert result["clicked"] is True
    assert result["gui_backend"] is True
    session = backend.get_session(sandbox_id)
    assert session is not None
    assert session.events[-1]["action"] == "click"
    assert session.events[-1]["x"] == 1
    assert session.events[-1]["y"] == 2


def test_sandbox_input_backend_failures_do_not_gain_success_flags(tmp_path):
    class Backend:
        def click(self, sandbox_id, x, y):
            return {"ok": False, "error": "window missing", "clicked": True, "recorded": True}

    manager = SandboxManager(state_dir=tmp_path, gui_backend=Backend())
    sandbox_id = manager.create()["sandbox_id"]

    result = manager.click(sandbox_id, 10, 20)

    assert result["ok"] is False
    assert result["code"] == "SANDBOX_BACKEND_ACTION_FAILED"
    assert result["status_code"] == 502
    assert result["sandbox_id"] == sandbox_id
    assert result["gui_backend"] is True
    assert result["action"] == "click"
    assert result["error"] == "window missing"
    assert "clicked" not in result
    assert "recorded" not in result
    assert manager.status(sandbox_id)["last_activity_at"] is None


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


def test_legacy_ready_registry_records_are_not_treated_as_live(tmp_path):
    registry_path = tmp_path / "sandboxes.json"
    registry_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "instances": {
                    "legacy-seat": {
                        "sandbox_id": "legacy-seat",
                        "image": "ubuntu:22.04",
                        "display": True,
                        "status": "ready",
                        "created_at": 10,
                    },
                },
            }
        ),
        encoding="utf-8",
    )

    manager = SandboxManager(state_dir=tmp_path)
    status = manager.status("legacy-seat")
    screenshot = manager.screenshot("legacy-seat")

    assert status["ok"] is True
    assert status["status"] == "stopped"
    assert status["provider_id"] == "legacy_placeholder"
    assert "fake-ready" in status["last_error"]
    assert screenshot["ok"] is False
    assert screenshot["code"] == "SANDBOX_NOT_RUNNING"
    assert screenshot["status"] == "stopped"
