"""
desktop_app_manager.py — Pack デスクトップアプリのライフサイクル管理

Phase V-4: desktop_app:execute capability のバックエンド。
Pack のデスクトップアプリ（pack-shell 経由）の登録・起動・停止・ショートカット生成を管理する。
"""
from __future__ import annotations

import json
import logging
import os
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# pack-shell バイナリのパスを解決する環境変数
_PACK_SHELL_PATH_ENV = "RUMI_PACK_SHELL_PATH"

# 登録済みアプリのメタデータ保存先（REPO/user_data/apps/ 相当）
_APPS_SUBDIR = "user_data/apps"


def _resolve_pack_shell_path() -> Optional[str]:
    """pack-shell バイナリのパスを解決する。"""
    env_path = os.environ.get(_PACK_SHELL_PATH_ENV)
    if env_path and os.path.isfile(env_path):
        return env_path
    # フォールバック: PATH から検索
    import shutil
    found = shutil.which("pack-shell")
    return found


class DesktopAppManager:
    """Pack デスクトップアプリのライフサイクルマネージャ。"""

    def __init__(self, repo_dir: Optional[str] = None):
        self._repo_dir = repo_dir or os.environ.get("REPO", "")
        self._apps_dir = os.path.join(self._repo_dir, _APPS_SUBDIR) if self._repo_dir else ""
        self._running: Dict[str, subprocess.Popen] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def register_app(
        self,
        pack_id: str,
        desktop_app_config: Dict[str, Any],
        pack_dir: str,
    ) -> Dict[str, Any]:
        """Pack のデスクトップアプリを登録し、プラットフォーム別ショートカットを生成する。

        Args:
            pack_id: Pack ID
            desktop_app_config: ecosystem.json の desktop_app セクション
            pack_dir: Pack のインストールディレクトリ

        Returns:
            {"success": True, "shortcut_path": "..."} or {"success": False, "error": "..."}
        """
        command = desktop_app_config.get("command", "")
        if not command:
            return {"success": False, "error": "desktop_app.command is required"}

        pack_shell = _resolve_pack_shell_path()
        if not pack_shell:
            return {
                "success": False,
                "error": (
                    "pack-shell binary not found. "
                    f"Set {_PACK_SHELL_PATH_ENV} or add pack-shell to PATH."
                ),
            }

        # メタデータ保存
        if self._apps_dir:
            os.makedirs(self._apps_dir, exist_ok=True)
            meta_path = os.path.join(self._apps_dir, f"{pack_id}.json")
            meta = {
                "pack_id": pack_id,
                "command": command,
                "pack_dir": pack_dir,
                "pack_shell": pack_shell,
                "window": desktop_app_config.get("window", {}),
                "env": desktop_app_config.get("env", {}),
                "working_dir": desktop_app_config.get("working_dir", ""),
                "platforms": desktop_app_config.get("platforms", []),
            }
            with open(meta_path, "w", encoding="utf-8") as f:
                json.dump(meta, f, indent=2)

        # プラットフォーム別ショートカット生成
        shortcut_path = self._create_shortcut(pack_id, pack_shell, pack_dir, desktop_app_config)

        return {"success": True, "shortcut_path": shortcut_path}

    def unregister_app(self, pack_id: str) -> Dict[str, Any]:
        """登録済みアプリを解除し、ショートカットを削除する。"""
        # 実行中なら停止
        if pack_id in self._running:
            self.stop_app(pack_id)

        # メタデータ削除
        if self._apps_dir:
            meta_path = os.path.join(self._apps_dir, f"{pack_id}.json")
            if os.path.exists(meta_path):
                os.remove(meta_path)

        # ショートカット削除
        self._remove_shortcut(pack_id)

        return {"success": True}

    def launch_app(self, pack_id: str) -> Dict[str, Any]:
        """Pack のデスクトップアプリを起動する。"""
        if pack_id in self._running:
            proc = self._running[pack_id]
            if proc.poll() is None:
                return {"success": True, "status": "already_running", "pid": proc.pid}

        meta = self._load_meta(pack_id)
        if meta is None:
            return {"success": False, "error": f"App not registered: {pack_id}"}

        pack_shell = meta.get("pack_shell", "")
        if not pack_shell or not os.path.isfile(pack_shell):
            pack_shell = _resolve_pack_shell_path()
            if not pack_shell:
                return {"success": False, "error": "pack-shell binary not found"}

        command = meta.get("command", "")
        if not command:
            return {"success": False, "error": f"No command configured for app: {pack_id}"}

        env = dict(os.environ)
        env.update(meta.get("env", {}))
        env["RUMI_PACK_ID"] = pack_id
        api_token = os.environ.get("RUMI_API_TOKEN", "")
        if api_token:
            env["RUMI_API_TOKEN"] = api_token

        working_dir = meta.get("working_dir") or meta.get("pack_dir", "")

        try:
            proc = subprocess.Popen(
                [pack_shell, "run", pack_id, "--command", command],
                cwd=working_dir or None,
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            self._running[pack_id] = proc
            return {"success": True, "status": "launched", "pid": proc.pid}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def stop_app(self, pack_id: str) -> Dict[str, Any]:
        """起動中のデスクトップアプリを SIGTERM で停止する。"""
        if pack_id not in self._running:
            return {"success": False, "error": f"App not running: {pack_id}"}

        proc = self._running[pack_id]
        if proc.poll() is not None:
            del self._running[pack_id]
            return {"success": True, "status": "already_stopped"}

        try:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
            del self._running[pack_id]
            return {"success": True, "status": "stopped"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def list_registered_apps(self) -> List[Dict[str, Any]]:
        """登録済みアプリの一覧を返す。"""
        result = []
        if not self._apps_dir or not os.path.isdir(self._apps_dir):
            return result
        for fname in os.listdir(self._apps_dir):
            if fname.endswith(".json"):
                fpath = os.path.join(self._apps_dir, fname)
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        meta = json.load(f)
                    pack_id = meta.get("pack_id", fname[:-5])
                    running = (
                        pack_id in self._running
                        and self._running[pack_id].poll() is None
                    )
                    meta["running"] = running
                    result.append(meta)
                except Exception:
                    continue
        return result

    # ------------------------------------------------------------------
    # Private — ショートカット生成
    # ------------------------------------------------------------------

    def _create_shortcut(
        self,
        pack_id: str,
        pack_shell: str,
        pack_dir: str,
        config: Dict[str, Any],
    ) -> str:
        """プラットフォーム別ショートカットを生成する。"""
        platform = sys.platform
        if platform == "darwin":
            return self._create_macos_app(pack_id, pack_shell, pack_dir, config)
        elif platform == "win32":
            return self._create_windows_shortcut(pack_id, pack_shell, pack_dir, config)
        else:
            return self._create_linux_desktop(pack_id, pack_shell, pack_dir, config)

    def _create_macos_app(
        self,
        pack_id: str,
        pack_shell: str,
        pack_dir: str,
        config: Dict[str, Any],
    ) -> str:
        """macOS .app bundle を生成する。"""
        app_name = config.get("window", {}).get("title", pack_id)
        safe_name = app_name.replace("/", "_").replace(" ", "_")
        apps_base = os.path.expanduser("~/Applications")
        os.makedirs(apps_base, exist_ok=True)

        app_dir = os.path.join(apps_base, f"{safe_name}.app")
        contents_dir = os.path.join(app_dir, "Contents")
        macos_dir = os.path.join(contents_dir, "MacOS")
        os.makedirs(macos_dir, exist_ok=True)

        # Info.plist
        plist_path = os.path.join(contents_dir, "Info.plist")
        bundle_id = f"ai.rumi.pack.{pack_id}".replace("_", "-")
        plist_content = (
            '<?xml version="1.0" encoding="UTF-8"?>\n'
            '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"\n'
            '  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
            '<plist version="1.0">\n'
            '<dict>\n'
            '    <key>CFBundleExecutable</key>\n'
            '    <string>launch</string>\n'
            '    <key>CFBundleIdentifier</key>\n'
            f'    <string>{bundle_id}</string>\n'
            '    <key>CFBundleName</key>\n'
            f'    <string>{app_name}</string>\n'
            '    <key>CFBundleVersion</key>\n'
            '    <string>1.0.0</string>\n'
            '    <key>CFBundlePackageType</key>\n'
            '    <string>APPL</string>\n'
            '</dict>\n'
            '</plist>'
        )
        with open(plist_path, "w", encoding="utf-8") as f:
            f.write(plist_content)

        # 実行ファイル
        launch_path = os.path.join(macos_dir, "launch")
        command = config.get("command", "")
        launch_script = f'#!/bin/bash\nexec "{pack_shell}" run "{pack_id}" --command "{command}"\n'
        with open(launch_path, "w", encoding="utf-8") as f:
            f.write(launch_script)
        os.chmod(
            launch_path,
            os.stat(launch_path).st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH,
        )

        return app_dir

    def _create_windows_shortcut(
        self,
        pack_id: str,
        pack_shell: str,
        pack_dir: str,
        config: Dict[str, Any],
    ) -> str:
        """Windows .lnk ショートカットを PowerShell で生成する。"""
        app_name = config.get("window", {}).get("title", pack_id)
        safe_name = app_name.replace("/", "_").replace(" ", "_")
        command = config.get("command", "")

        if self._apps_dir:
            lnk_dir = self._apps_dir
        else:
            lnk_dir = os.path.expanduser("~")
        os.makedirs(lnk_dir, exist_ok=True)
        lnk_path = os.path.join(lnk_dir, f"{safe_name}.lnk")

        ps_script = (
            f'$ws = New-Object -ComObject WScript.Shell; '
            f'$s = $ws.CreateShortcut("{lnk_path}"); '
            f'$s.TargetPath = "{pack_shell}"; '
            f'$s.Arguments = "run {pack_id} --command ""{command}"""; '
            f'$s.WorkingDirectory = "{pack_dir}"; '
            f'$s.Save()'
        )

        try:
            subprocess.run(
                ["powershell", "-Command", ps_script],
                check=True,
                capture_output=True,
            )
        except Exception as e:
            logger.warning("Failed to create Windows shortcut for %s: %s", pack_id, e)

        return lnk_path

    def _create_linux_desktop(
        self,
        pack_id: str,
        pack_shell: str,
        pack_dir: str,
        config: Dict[str, Any],
    ) -> str:
        """Linux .desktop ファイルを生成する。"""
        app_name = config.get("window", {}).get("title", pack_id)
        safe_name = app_name.replace("/", "_").replace(" ", "_")
        command = config.get("command", "")

        desktop_dir = os.path.expanduser("~/.local/share/applications")
        os.makedirs(desktop_dir, exist_ok=True)

        desktop_path = os.path.join(desktop_dir, f"rumi-{safe_name}.desktop")
        desktop_content = (
            "[Desktop Entry]\n"
            "Type=Application\n"
            f"Name={app_name}\n"
            f'Exec="{pack_shell}" run "{pack_id}" --command "{command}"\n'
            f"Path={pack_dir}\n"
            "Terminal=false\n"
            "Categories=Utility;\n"
        )
        with open(desktop_path, "w", encoding="utf-8") as f:
            f.write(desktop_content)
        os.chmod(desktop_path, os.stat(desktop_path).st_mode | stat.S_IEXEC)

        return desktop_path

    def _remove_shortcut(self, pack_id: str) -> None:
        """プラットフォーム別ショートカットを削除する。"""
        meta = self._load_meta(pack_id)
        if meta is None:
            return

        platform = sys.platform
        app_name = meta.get("window", {}).get("title", pack_id)
        safe_name = app_name.replace("/", "_").replace(" ", "_")

        if platform == "darwin":
            import shutil as _shutil
            app_dir = os.path.join(os.path.expanduser("~/Applications"), f"{safe_name}.app")
            if os.path.isdir(app_dir):
                _shutil.rmtree(app_dir, ignore_errors=True)
        elif platform == "win32":
            lnk_dir = self._apps_dir or os.path.expanduser("~")
            lnk_path = os.path.join(lnk_dir, f"{safe_name}.lnk")
            if os.path.exists(lnk_path):
                os.remove(lnk_path)
        else:
            desktop_path = os.path.join(
                os.path.expanduser("~/.local/share/applications"),
                f"rumi-{safe_name}.desktop",
            )
            if os.path.exists(desktop_path):
                os.remove(desktop_path)

    def _load_meta(self, pack_id: str) -> Optional[Dict[str, Any]]:
        """登録済みアプリのメタデータを読み込む。"""
        if not self._apps_dir:
            return None
        meta_path = os.path.join(self._apps_dir, f"{pack_id}.json")
        if not os.path.isfile(meta_path):
            return None
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None
