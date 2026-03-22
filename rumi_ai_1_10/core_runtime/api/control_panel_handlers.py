"""Control Panel ハンドラ Mixin — Phase C

/api/panel/ 配下の全 API を提供する。
既存の Mixin パターン (FlowHandlersMixin 等) に準拠。

API 一覧:
  GET  /api/panel/dashboard          — ダッシュボード集約
  GET  /api/panel/packs              — Pack 一覧（有効/無効含む）
  POST /api/panel/packs/{id}/enable  — Pack 有効化
  POST /api/panel/packs/{id}/disable — Pack 無効化
  GET  /api/panel/flows              — Flow 一覧（本文なし）
  GET  /api/panel/flows/{id}         — Flow 詳細（YAML 本文付き）
  POST /api/panel/flows              — Flow 新規作成
  PUT  /api/panel/flows/{id}         — Flow 更新
  DELETE /api/panel/flows/{id}       — Flow 削除
  GET  /api/panel/settings/profile   — プロフィール取得
  PUT  /api/panel/settings/profile   — プロフィール更新
  GET  /api/panel/version            — バージョン情報
  POST /api/panel/kernel/restart     — Kernel 再起動（exit code 42）
"""
from __future__ import annotations

import json
import logging
import os
import re
import sys
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from ._helpers import _log_internal_error, _SAFE_ERROR_MSG

logger = logging.getLogger(__name__)

# Flow ID バリデーション: 英数字・アンダースコア・ドット・ハイフン、1〜128文字
_RE_FLOW_ID = re.compile(r'^[a-zA-Z0-9_.\-]{1,128}$')

# YAML ファイル名バリデーション
_RE_YAML_FILENAME = re.compile(r'^[a-zA-Z0-9_.\-]{1,128}\.ya?ml$')

# Kernel バージョン（ハードコード。Phase U でバージョンファイルから読むように変更予定）
_KERNEL_VERSION = "1.10.0"


class ControlPanelHandlersMixin:
    """Control Panel API のハンドラ"""

    # ------------------------------------------------------------------
    # Dashboard
    # ------------------------------------------------------------------

    def _panel_get_dashboard(self) -> Dict[str, Any]:
        """GET /api/panel/dashboard — ダッシュボード情報を集約して返す"""
        result: Dict[str, Any] = {
            "packs": {"total": 0, "enabled": 0, "disabled": 0},
            "flows": {"total": 0},
            "kernel": {"status": "running", "uptime": None},
            "profile": None,
        }

        # --- Pack 情報 ---
        try:
            pack_list = self._panel_list_packs_internal()
            total = len(pack_list)
            enabled = sum(1 for p in pack_list if p.get("enabled", True))
            result["packs"] = {
                "total": total,
                "enabled": enabled,
                "disabled": total - enabled,
            }
        except Exception as e:
            _log_internal_error("panel_dashboard.packs", e)

        # --- Flow 情報 ---
        try:
            flow_list = self._panel_list_flows_internal()
            result["flows"] = {"total": len(flow_list)}
        except Exception as e:
            _log_internal_error("panel_dashboard.flows", e)

        # --- Kernel 情報 ---
        try:
            boot_ts = os.environ.get("RUMI_BOOT_TIMESTAMP")
            if boot_ts:
                uptime = int(time.time() - float(boot_ts))
                result["kernel"]["uptime"] = uptime
        except Exception:
            pass

        # --- プロフィール要約 ---
        try:
            profile = self._panel_read_profile()
            if profile:
                result["profile"] = {
                    "username": profile.get("username"),
                    "language": profile.get("language"),
                    "icon": profile.get("icon"),
                }
        except Exception as e:
            _log_internal_error("panel_dashboard.profile", e)

        return result

    # ------------------------------------------------------------------
    # Pack Management
    # ------------------------------------------------------------------

    def _panel_list_packs_internal(self) -> List[Dict[str, Any]]:
        """Pack 一覧を内部的に取得する（dashboard からも呼ばれる）"""
        packs: List[Dict[str, Any]] = []

        # core_pack
        core_pack_dir = Path(__file__).resolve().parent.parent / "core_pack"
        if core_pack_dir.is_dir():
            for d in sorted(core_pack_dir.iterdir()):
                if not d.is_dir():
                    continue
                eco_path = d / "ecosystem.json"
                if not eco_path.is_file():
                    continue
                try:
                    with open(eco_path, "r", encoding="utf-8") as f:
                        eco = json.load(f)
                    packs.append({
                        "pack_id": eco.get("pack_id", d.name),
                        "name": eco.get("metadata", {}).get("name", d.name),
                        "version": eco.get("version", "0.0.0"),
                        "description": eco.get("metadata", {}).get("description", ""),
                        "is_core": True,
                        "enabled": True,
                    })
                except Exception:
                    pass

        # ecosystem packs
        try:
            from ..paths import discover_pack_locations
            for loc in discover_pack_locations():
                try:
                    with open(loc.ecosystem_json_path, "r", encoding="utf-8") as f:
                        eco = json.load(f)
                    enabled = eco.get("enabled", True)
                    packs.append({
                        "pack_id": loc.pack_id,
                        "name": eco.get("metadata", {}).get("name", loc.pack_id),
                        "version": eco.get("version", "0.0.0"),
                        "description": eco.get("metadata", {}).get("description", ""),
                        "is_core": False,
                        "enabled": enabled,
                    })
                except Exception:
                    pass
        except Exception as e:
            _log_internal_error("panel_list_packs.ecosystem", e)

        return packs

    def _panel_get_packs(self) -> Dict[str, Any]:
        """GET /api/panel/packs — Pack 一覧"""
        packs = self._panel_list_packs_internal()
        return {"packs": packs, "count": len(packs)}

    def _panel_enable_pack(self, pack_id: str) -> Dict[str, Any]:
        """POST /api/panel/packs/{id}/enable — Pack 有効化"""
        return self._panel_set_pack_enabled(pack_id, True)

    def _panel_disable_pack(self, pack_id: str) -> Dict[str, Any]:
        """POST /api/panel/packs/{id}/disable — Pack 無効化"""
        return self._panel_set_pack_enabled(pack_id, False)

    def _panel_set_pack_enabled(self, pack_id: str, enabled: bool) -> Dict[str, Any]:
        """Pack の enabled フラグを変更する"""
        try:
            from ..paths import discover_pack_locations
            for loc in discover_pack_locations():
                if loc.pack_id == pack_id:
                    eco_path = loc.ecosystem_json_path
                    with open(eco_path, "r", encoding="utf-8") as f:
                        eco = json.load(f)
                    eco["enabled"] = enabled
                    with open(eco_path, "w", encoding="utf-8") as f:
                        json.dump(eco, f, ensure_ascii=False, indent=2)
                        f.write("\n")
                    return {
                        "pack_id": pack_id,
                        "enabled": enabled,
                    }
            return {"error": f"Pack '{pack_id}' not found", "status_code": 404}
        except Exception as e:
            _log_internal_error("panel_set_pack_enabled", e)
            return {"error": _SAFE_ERROR_MSG, "status_code": 500}

    # ------------------------------------------------------------------
    # Flow Management
    # ------------------------------------------------------------------

    def _panel_list_flows_internal(self) -> List[Dict[str, Any]]:
        """Flow 一覧を内部的に取得する（本文なし）"""
        flows: List[Dict[str, Any]] = []

        kernel = getattr(self.__class__, "kernel", None) or getattr(self, "kernel", None)
        if kernel is None:
            return flows
        ir = getattr(kernel, "interface_registry", None)
        if ir is None:
            return flows

        all_keys = ir.list(include_meta=True) or {}
        for key, info in all_keys.items():
            if not key.startswith("flow."):
                continue
            if key.startswith("flow.hooks") or key.startswith("flow.construct"):
                continue
            flow_id = key[5:]
            meta = info.get("last_meta") or {}
            flows.append({
                "flow_id": flow_id,
                "name": meta.get("name", flow_id),
                "pack_id": meta.get("owner_pack") or meta.get("pack_id") or meta.get("source", ""),
                "filename": meta.get("filename", ""),
            })

        return sorted(flows, key=lambda f: f["flow_id"])

    def _panel_get_flows(self) -> Dict[str, Any]:
        """GET /api/panel/flows — Flow 一覧（本文なし）"""
        flows = self._panel_list_flows_internal()
        return {"flows": flows, "count": len(flows)}

    def _panel_get_flow_detail(self, flow_id: str) -> Dict[str, Any]:
        """GET /api/panel/flows/{id} — Flow 詳細（YAML 本文付き）"""
        kernel = getattr(self.__class__, "kernel", None) or getattr(self, "kernel", None)
        if kernel is None:
            return {"error": "Kernel not initialized", "status_code": 503}

        ir = getattr(kernel, "interface_registry", None)
        if ir is None:
            return {"error": "InterfaceRegistry not available", "status_code": 503}

        flow_key = f"flow.{flow_id}"
        all_keys = ir.list(include_meta=True) or {}
        if flow_key not in all_keys:
            return {"error": f"Flow '{flow_id}' not found", "status_code": 404}

        info = all_keys[flow_key]
        meta = info.get("last_meta") or {}
        filename = meta.get("filename", "")

        yaml_content = ""
        if filename:
            yaml_path = self._panel_resolve_flow_path(filename, meta)
            if yaml_path and yaml_path.is_file():
                try:
                    yaml_content = yaml_path.read_text(encoding="utf-8")
                except OSError as e:
                    _log_internal_error("panel_get_flow_detail.read", e)
                    yaml_content = f"# Error reading file: {e}"

        return {
            "flow_id": flow_id,
            "name": meta.get("name", flow_id),
            "pack_id": meta.get("owner_pack") or meta.get("pack_id") or meta.get("source", ""),
            "filename": filename,
            "yaml_content": yaml_content,
        }

    def _panel_create_flow(self, body: Dict[str, Any]) -> Dict[str, Any]:
        """POST /api/panel/flows — Flow 新規作成"""
        flow_id = body.get("flow_id", "").strip()
        yaml_content = body.get("yaml_content", "")
        filename = body.get("filename", "").strip()

        if not flow_id or not _RE_FLOW_ID.match(flow_id):
            return {"error": "Invalid or missing flow_id", "status_code": 400}
        if not yaml_content:
            return {"error": "yaml_content is required", "status_code": 400}
        if not filename:
            filename = f"{flow_id}.flow.yaml"
        if not _RE_YAML_FILENAME.match(filename):
            return {"error": "Invalid filename", "status_code": 400}

        from ..paths import USER_SHARED_FLOWS_DIR
        flows_dir = Path(USER_SHARED_FLOWS_DIR)
        flows_dir.mkdir(parents=True, exist_ok=True)
        target = flows_dir / filename

        if target.exists():
            return {"error": f"Flow file '{filename}' already exists", "status_code": 409}

        try:
            target.write_text(yaml_content, encoding="utf-8")
        except OSError as e:
            _log_internal_error("panel_create_flow.write", e)
            return {"error": _SAFE_ERROR_MSG, "status_code": 500}

        self._panel_reload_flows()

        return {
            "flow_id": flow_id,
            "filename": filename,
            "created": True,
        }

    def _panel_update_flow(self, flow_id: str, body: Dict[str, Any]) -> Dict[str, Any]:
        """PUT /api/panel/flows/{id} — Flow 更新"""
        yaml_content = body.get("yaml_content", "")
        if not yaml_content:
            return {"error": "yaml_content is required", "status_code": 400}

        kernel = getattr(self.__class__, "kernel", None) or getattr(self, "kernel", None)
        if kernel is None:
            return {"error": "Kernel not initialized", "status_code": 503}
        ir = getattr(kernel, "interface_registry", None)
        if ir is None:
            return {"error": "InterfaceRegistry not available", "status_code": 503}

        flow_key = f"flow.{flow_id}"
        all_keys = ir.list(include_meta=True) or {}
        if flow_key not in all_keys:
            return {"error": f"Flow '{flow_id}' not found", "status_code": 404}

        info = all_keys[flow_key]
        meta = info.get("last_meta") or {}
        filename = meta.get("filename", "")

        if not filename:
            return {"error": "Cannot determine flow file path", "status_code": 500}

        yaml_path = self._panel_resolve_flow_path(filename, meta)
        if yaml_path is None or not yaml_path.is_file():
            return {"error": f"Flow file not found: {filename}", "status_code": 404}

        try:
            yaml_path.write_text(yaml_content, encoding="utf-8")
        except OSError as e:
            _log_internal_error("panel_update_flow.write", e)
            return {"error": _SAFE_ERROR_MSG, "status_code": 500}

        self._panel_reload_flows()

        return {
            "flow_id": flow_id,
            "filename": filename,
            "updated": True,
        }

    def _panel_delete_flow(self, flow_id: str) -> Dict[str, Any]:
        """DELETE /api/panel/flows/{id} — Flow 削除"""
        kernel = getattr(self.__class__, "kernel", None) or getattr(self, "kernel", None)
        if kernel is None:
            return {"error": "Kernel not initialized", "status_code": 503}
        ir = getattr(kernel, "interface_registry", None)
        if ir is None:
            return {"error": "InterfaceRegistry not available", "status_code": 503}

        flow_key = f"flow.{flow_id}"
        all_keys = ir.list(include_meta=True) or {}
        if flow_key not in all_keys:
            return {"error": f"Flow '{flow_id}' not found", "status_code": 404}

        info = all_keys[flow_key]
        meta = info.get("last_meta") or {}
        filename = meta.get("filename", "")

        if not filename:
            return {"error": "Cannot determine flow file path", "status_code": 500}

        yaml_path = self._panel_resolve_flow_path(filename, meta)
        if yaml_path is None or not yaml_path.is_file():
            return {"error": f"Flow file not found: {filename}", "status_code": 404}

        from ..paths import USER_SHARED_FLOWS_DIR
        shared_dir = Path(USER_SHARED_FLOWS_DIR).resolve()
        try:
            yaml_path.resolve().relative_to(shared_dir)
        except ValueError:
            return {
                "error": "Cannot delete non-user flows (core/official flows are protected)",
                "status_code": 403,
            }

        try:
            yaml_path.unlink()
        except OSError as e:
            _log_internal_error("panel_delete_flow.unlink", e)
            return {"error": _SAFE_ERROR_MSG, "status_code": 500}

        try:
            ir.unregister(flow_key)
        except Exception:
            pass

        return {
            "flow_id": flow_id,
            "deleted": True,
        }

    def _panel_resolve_flow_path(self, filename: str, meta: Dict[str, Any]) -> Optional[Path]:
        """Flow のファイルパスを解決する"""
        source_path = meta.get("source_path") or meta.get("_source_path")
        if source_path:
            p = Path(source_path)
            if p.is_file():
                return p

        from ..paths import (
            USER_SHARED_FLOWS_DIR,
            OFFICIAL_FLOWS_DIR,
            CORE_PACK_DIR,
            discover_pack_locations,
            get_pack_flow_dirs,
        )

        candidates: List[Path] = [
            Path(USER_SHARED_FLOWS_DIR) / filename,
            Path(OFFICIAL_FLOWS_DIR) / filename,
        ]

        core_pack_path = Path(CORE_PACK_DIR)
        if core_pack_path.is_dir():
            for d in core_pack_path.iterdir():
                if d.is_dir():
                    candidates.append(d / "flows" / filename)

        try:
            for loc in discover_pack_locations():
                for flow_dir in get_pack_flow_dirs(loc.pack_subdir):
                    candidates.append(flow_dir / filename)
        except Exception:
            pass

        for c in candidates:
            if c.is_file():
                return c

        return None

    def _panel_reload_flows(self) -> None:
        """Flow を再ロードする（ベストエフォート）"""
        try:
            from ..flow_loader import get_flow_loader
            loader = get_flow_loader()
            if hasattr(loader, "reload_all"):
                loader.reload_all()
            elif hasattr(loader, "load_all"):
                loader.load_all()
        except Exception as e:
            _log_internal_error("panel_reload_flows", e)

    # ------------------------------------------------------------------
    # Settings — Profile
    # ------------------------------------------------------------------

    def _panel_read_profile(self) -> Optional[Dict[str, Any]]:
        """profile.json を読み取る"""
        base_dir = Path(__file__).resolve().parent.parent.parent
        profile_path = base_dir / "user_data" / "settings" / "profile.json"
        if not profile_path.is_file():
            return None
        try:
            with open(profile_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return None

    def _panel_get_profile(self) -> Dict[str, Any]:
        """GET /api/panel/settings/profile — プロフィール取得"""
        profile = self._panel_read_profile()
        if profile is None:
            return {"error": "Profile not found", "status_code": 404}
        return {"profile": profile}

    def _panel_update_profile(self, body: Dict[str, Any]) -> Dict[str, Any]:
        """PUT /api/panel/settings/profile — プロフィール更新"""
        try:
            from ..core_pack.core_setup.save_profile import save_profile
            base_dir = Path(__file__).resolve().parent.parent.parent
            result = save_profile(body, base_dir=base_dir)
            if result.get("success"):
                return {"profile": self._panel_read_profile(), "updated": True}
            return {
                "error": "; ".join(result.get("errors", ["Update failed"])),
                "status_code": 400,
            }
        except ImportError:
            return {"error": "save_profile module not available", "status_code": 500}
        except Exception as e:
            _log_internal_error("panel_update_profile", e)
            return {"error": _SAFE_ERROR_MSG, "status_code": 500}

    # ------------------------------------------------------------------
    # Version
    # ------------------------------------------------------------------

    def _panel_get_version(self) -> Dict[str, Any]:
        """GET /api/panel/version — バージョン情報"""
        import platform
        return {
            "kernel_version": _KERNEL_VERSION,
            "python_version": platform.python_version(),
            "platform": platform.system(),
            "platform_release": platform.release(),
        }

    # ------------------------------------------------------------------
    # Kernel Restart
    # ------------------------------------------------------------------

    def _panel_restart_kernel(self) -> Dict[str, Any]:
        """POST /api/panel/kernel/restart — Kernel 再起動

        exit code 42 を返し、Rust ランチャーが再起動する。
        daemon スレッドで 1 秒遅延させてからプロセスを終了する。
        """
        def _delayed_exit():
            time.sleep(1.0)
            logger.info("Kernel restart requested via API — exiting with code 42")
            os._exit(42)

        timer = threading.Thread(target=_delayed_exit, daemon=True)
        timer.start()

        return {"restarting": True, "message": "Kernel will restart in ~1 second"}
