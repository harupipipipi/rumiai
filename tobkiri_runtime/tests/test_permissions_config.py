"""
test_permissions_config.py - permissions.json 設定ファイルのテスト

施策5: Permission ID 定数の設定ファイル化
"""

import json
import os
import shutil
import tempfile
from pathlib import Path

import pytest


# --- helpers ---

def _config_path() -> Path:
    """permissions.json の絶対パスを返す。"""
    return (
        Path(__file__).resolve().parent.parent
        / "core_runtime" / "config" / "permissions.json"
    )


def _load_config() -> dict:
    """permissions.json を読み込んで dict を返す。"""
    return json.loads(_config_path().read_text(encoding="utf-8"))


# === テスト ===


class TestPermissionsConfigFile:
    """permissions.json ファイル自体のテスト"""

    def test_config_file_exists(self):
        """permissions.json が存在し、有効な JSON であること。"""
        p = _config_path()
        assert p.is_file(), f"permissions.json not found at {p}"
        data = json.loads(p.read_text(encoding="utf-8"))
        assert isinstance(data, dict)

    def test_required_keys_present(self):
        """必須キーが存在すること。"""
        data = _load_config()
        assert "core_pack_id_prefix" in data
        assert "permission_ids" in data
        assert "core_function_handlers" in data
        assert "docker_method_map" in data

    def test_permission_ids_are_strings(self):
        """permission_id 値が全て文字列であること（docker はリスト内が文字列）。"""
        data = _load_config()
        pids = data["permission_ids"]
        assert isinstance(pids["flow_run"], str)
        assert isinstance(pids["secret_get"], str)
        assert isinstance(pids["docker_run"], str)
        assert isinstance(pids["docker"], list)
        for item in pids["docker"]:
            assert isinstance(item, str), f"docker permission_id is not str: {item}"


class TestPermissionsConfigValues:
    """設定ファイルの値がフォールバック値と一致することのテスト"""

    def test_config_values_match_defaults(self):
        """設定ファイルの値がハードコードのデフォルト値と一致すること。"""
        data = _load_config()

        # core_pack_id_prefix
        assert data["core_pack_id_prefix"] == "core_"

        # permission_ids
        pids = data["permission_ids"]
        assert pids["flow_run"] == "flow.run"
        assert pids["secret_get"] == "secrets.get"
        assert pids["docker_run"] == "docker.run"
        assert set(pids["docker"]) == {
            "docker.run", "docker.exec", "docker.stop",
            "docker.logs", "docker.list",
        }

        # docker_method_map
        assert data["docker_method_map"] == {
            "docker.run": "handle_run",
            "docker.exec": "handle_exec",
            "docker.stop": "handle_stop",
            "docker.logs": "handle_logs",
            "docker.list": "handle_list",
        }

        # core_function_handlers
        assert data["core_function_handlers"] == {
            "core_docker_capability": "docker_capability_handler",
            "core_viewer_capability": "viewer_capability_handler",
            "core_desktop_capability": "desktop_capability_handler",
        }


class TestPermissionsConfigFallback:
    """設定ファイルがない場合のフォールバックテスト"""

    def test_fallback_without_config(self):
        """設定ファイルを一時退避して _load_permissions_config() が None を返すこと。"""
        config_path = _config_path()
        if not config_path.is_file():
            pytest.skip("permissions.json does not exist; cannot test fallback")

        backup_path = config_path.with_suffix(".json.bak")
        try:
            shutil.move(str(config_path), str(backup_path))

            # _load_permissions_config を再実行
            from core_runtime.capability_executor import _load_permissions_config
            result = _load_permissions_config()
            assert result is None, "Expected None when config file is missing"
        finally:
            # 必ず復元
            if backup_path.is_file():
                shutil.move(str(backup_path), str(config_path))

    def test_module_constants_have_correct_values(self):
        """モジュール定数が正しい値を持っていること（config 有無に関わらず）。"""
        from core_runtime.capability_executor import (
            FLOW_RUN_PERMISSION_ID,
            DOCKER_PERMISSION_IDS,
            DOCKER_RUN_PERMISSION_ID,
            DOCKER_METHOD_MAP,
            SECRET_GET_PERMISSION_ID,
        )
        assert FLOW_RUN_PERMISSION_ID == "flow.run"
        assert DOCKER_RUN_PERMISSION_ID == "docker.run"
        assert SECRET_GET_PERMISSION_ID == "secrets.get"
        assert isinstance(DOCKER_PERMISSION_IDS, frozenset)
        assert DOCKER_PERMISSION_IDS == frozenset({
            "docker.run", "docker.exec", "docker.stop",
            "docker.logs", "docker.list",
        })
        assert isinstance(DOCKER_METHOD_MAP, dict)
        assert DOCKER_METHOD_MAP["docker.run"] == "handle_run"
