from __future__ import annotations

import json
import os
import shlex
import sys
from pathlib import Path
from unittest import mock

import pytest

ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def test_default_di_registers_desktop_capability_handler():
    from core_runtime.di_container import get_container, reset_container

    reset_container()
    try:
        container = get_container()
        assert container.has("desktop_capability_handler")
        assert container.get("desktop_capability_handler").__class__.__name__ == "DesktopCapabilityHandler"
    finally:
        reset_container()


def test_permissions_config_maps_core_desktop_capability():
    config = json.loads((ROOT / "core_runtime" / "config" / "permissions.json").read_text(encoding="utf-8"))
    assert config["core_function_handlers"]["core_desktop_capability"] == "desktop_capability_handler"


def test_core_desktop_execute_manifest_uses_dot_permission_id():
    manifest = json.loads(
        (
            ROOT
            / "core_runtime"
            / "core_pack"
            / "core_desktop_capability"
            / "functions"
            / "execute"
            / "manifest.json"
        ).read_text(encoding="utf-8")
    )
    assert manifest["requires"] == ["desktop_app.execute"]
    assert manifest["grant_config"]["permission_id"] == "desktop_app.execute"


def test_runtime_registers_desktop_launch_handlers():
    from core_runtime.kernel_handlers_runtime import KernelRuntimeHandlersMixin

    class Stub(KernelRuntimeHandlersMixin):
        pass

    handlers = Stub()._register_runtime_handlers()
    assert handlers["kernel:desktop.launch"].__name__ == "_h_desktop_launch"
    assert handlers["kernel:desktop.stop"].__name__ == "_h_desktop_stop"


def test_defaultspack_ecosystem_registers_desktop_app_metadata(tmp_path):
    from core_runtime.desktop_app_manager import DesktopAppManager

    pack_shell = tmp_path / "pack-shell"
    pack_shell.write_text("#!/bin/sh\n", encoding="utf-8")
    pack_shell.chmod(0o755)
    manager = DesktopAppManager(repo_dir=str(tmp_path / "repo"))

    with mock.patch.dict(os.environ, {"RUMI_PACK_SHELL_PATH": str(pack_shell)}):
        with mock.patch.object(manager, "_create_shortcut", return_value=str(tmp_path / "Defaultspack.app")):
            result = manager.register_from_ecosystem(str(DEFAULTSPACK_ROOT / "ecosystem.json"))

    assert result["success"] is True
    meta_path = tmp_path / "repo" / "user_data" / "apps" / "defaultspack.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    assert meta["pack_id"] == "defaultspack"
    assert meta["command"] == "python defaultspack/desktop_app.py"
    assert meta["pack_dir"] == str(DEFAULTSPACK_ROOT)
    assert meta["env"]["RUMI_DEFAULTSPACK_PORT"] == "8766"


def test_desktop_capability_can_launch_registered_pack_with_issued_token():
    from core_runtime.desktop_capability import DesktopCapabilityHandler

    handler = DesktopCapabilityHandler()
    with mock.patch("core_runtime.desktop_app_manager.DesktopAppManager.launch_app_with_env") as mock_launch:
        mock_launch.return_value = {"success": True, "status": "launched", "pid": 123}
        result = handler.handle_execute(
            principal_id="defaultspack",
            args={"pack_id": "defaultspack", "action": "launch"},
            grant_config={"allowed_packs": ["defaultspack"], "max_token_lifetime": 300},
        )

    assert result["expires_in"] == 300
    assert result["app"]["status"] == "launched"
    mock_launch.assert_called_once()
    assert mock_launch.call_args.kwargs["api_token"] == result["token"]


def test_desktop_capability_denies_empty_allowed_packs():
    from core_runtime.desktop_capability import DesktopCapabilityHandler

    handler = DesktopCapabilityHandler()
    result = handler.handle_execute(
        principal_id="defaultspack",
        args={"pack_id": "defaultspack", "action": "launch"},
        grant_config={"allowed_packs": []},
    )

    assert result == {"error": "Pack not allowed for desktop app execution: defaultspack"}


def test_desktop_capability_allows_only_explicit_pack_list():
    from core_runtime.desktop_capability import DesktopCapabilityHandler

    handler = DesktopCapabilityHandler()

    with mock.patch("core_runtime.desktop_app_manager.DesktopAppManager.launch_app_with_env") as mock_launch:
        mock_launch.return_value = {"success": True, "status": "launched", "pid": 123}
        allowed = handler.handle_execute(
            principal_id="defaultspack",
            args={"pack_id": "defaultspack", "action": "launch"},
            grant_config={"allowed_packs": ["defaultspack"]},
        )
        denied = handler.handle_execute(
            principal_id="otherpack",
            args={"pack_id": "otherpack", "action": "launch"},
            grant_config={"allowed_packs": ["defaultspack"]},
        )

    assert allowed["app"]["success"] is True
    assert denied == {"error": "Pack not allowed for desktop app execution: otherpack"}


def test_desktop_capability_explicit_wildcard_allows_any_pack():
    from core_runtime.desktop_capability import DesktopCapabilityHandler

    handler = DesktopCapabilityHandler()
    result = handler.handle_execute(
        principal_id="otherpack",
        args={"pack_id": "otherpack", "action": "token"},
        grant_config={"allowed_packs": ["*"]},
    )

    assert result["expires_in"] == DesktopCapabilityHandler.DEFAULT_TOKEN_LIFETIME
    assert handler.verify_token(result["token"])["pack_id"] == "otherpack"


def test_desktop_capability_launch_then_stop_uses_same_manager(tmp_path):
    from core_runtime.desktop_app_manager import DesktopAppManager
    from core_runtime.desktop_capability import DesktopCapabilityHandler

    repo_dir = tmp_path / "repo"
    apps_dir = repo_dir / "user_data" / "apps"
    apps_dir.mkdir(parents=True)
    pack_dir = tmp_path / "pack"
    pack_dir.mkdir()
    (apps_dir / "defaultspack.json").write_text(
        json.dumps(
            {
                "pack_id": "defaultspack",
                "command": (
                    f"{shlex.quote(sys.executable)} -c "
                    "\"import time; time.sleep(60)\""
                ),
                "pack_dir": str(pack_dir),
                "requires_api_token": True,
                "env": {},
                "working_dir": str(pack_dir),
            }
        ),
        encoding="utf-8",
    )

    manager = DesktopAppManager(repo_dir=str(repo_dir))
    handler = DesktopCapabilityHandler(desktop_app_manager=manager)

    launch = handler.handle_execute(
        principal_id="defaultspack",
        args={"pack_id": "defaultspack", "action": "launch"},
        grant_config={"allowed_packs": ["defaultspack"]},
    )
    assert launch["app"]["success"] is True

    stop = handler.handle_execute(
        principal_id="defaultspack",
        args={"pack_id": "defaultspack", "action": "stop"},
        grant_config={"allowed_packs": ["defaultspack"]},
    )
    assert stop["app"] == {"success": True, "status": "stopped"}


@pytest.mark.parametrize("action", ["stop", "status"])
def test_desktop_capability_delegates_non_launch_actions(action):
    from core_runtime.desktop_capability import DesktopCapabilityHandler

    handler = DesktopCapabilityHandler()
    if action == "stop":
        target = "core_runtime.desktop_app_manager.DesktopAppManager.stop_app"
        expected_key = "status"
        expected_value = "stopped"
        return_value = {"success": True, "status": "stopped"}
    else:
        target = "core_runtime.desktop_app_manager.DesktopAppManager.list_registered_apps"
        expected_key = "registered_apps"
        expected_value = []
        return_value = []

    with mock.patch(target, return_value=return_value) as delegated:
        result = handler.handle_execute(
            principal_id="defaultspack",
            args={"pack_id": "defaultspack", "action": action},
            grant_config={"allowed_packs": ["defaultspack"]},
        )

    assert result["app"][expected_key] == expected_value
    delegated.assert_called_once()
