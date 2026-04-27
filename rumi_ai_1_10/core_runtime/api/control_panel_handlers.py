"""Control Panel ハンドラ Mixin — Phase C

/api/panel/ 配下の全 API を提供する。
既存の Mixin パターン (FlowHandlersMixin 等) に準拠。

API 一覧:
  GET  /api/panel/dashboard          — ダッシュボード集約
  GET  /api/panel/packs              — Pack 一覧（有効/無効含む）
  POST /api/panel/packs/{id}/enable  — Pack 有効化
  POST /api/panel/packs/{id}/disable — Pack 無効化
  GET  /api/panel/startup/profiles   — 起動プロファイル一覧と slot catalog
  POST /api/panel/startup/profiles   — 起動プロファイル新規作成
  PUT  /api/panel/startup/profiles/{id} — 起動プロファイル更新
  DELETE /api/panel/startup/profiles/{id} — 起動プロファイル削除
  POST /api/panel/startup/profiles/{id}/duplicate — 起動プロファイル複製
  POST /api/panel/startup/profiles/{id}/activate  — 起動プロファイル切り替え
  POST /api/panel/startup/profiles/{id}/launch    — 起動プロファイル起動
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
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from ._helpers import _log_internal_error, _SAFE_ERROR_MSG

try:
    from rumi_ai import __version__ as _KERNEL_VERSION
except ImportError:
    _KERNEL_VERSION = "1.10.0"

logger = logging.getLogger(__name__)

# Flow ID バリデーション: 英数字・アンダースコア・ドット・ハイフン、1〜128文字
_RE_FLOW_ID = re.compile(r'^[a-zA-Z0-9_.\-]{1,128}$')

# YAML ファイル名バリデーション
_RE_YAML_FILENAME = re.compile(r'^[a-zA-Z0-9_.\-]{1,128}\.ya?ml$')

# レート制限: 最後の restart 要求タイムスタンプ（epoch秒）
_last_restart_time: float = 0.0
_RESTART_EXIT_CODE = 42
_restart_requested = False


def request_kernel_restart() -> None:
    global _restart_requested
    _restart_requested = True


def is_kernel_restart_requested() -> bool:
    return _restart_requested


def clear_kernel_restart_request() -> None:
    global _restart_requested
    _restart_requested = False


class ControlPanelHandlersMixin:
    """Control Panel API のハンドラ"""

    def _panel_startup_profile_manager(self):
        from ..startup_profiles import StartupProfileManager

        return StartupProfileManager(
            interface_registry=getattr(self, "interface_registry", None),
            approval_manager=getattr(self, "approval_manager", None),
        )

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
            overrides = self._panel_read_pack_overrides()
            for loc in discover_pack_locations():
                try:
                    with open(loc.ecosystem_json_path, "r", encoding="utf-8") as f:
                        eco = json.load(f)
                    enabled = overrides.get(loc.pack_id, eco.get("enabled", True))
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

    def _panel_pack_overrides_path(self) -> Path:
        """Pack の有効/無効オーバーレイ設定ファイルのパスを返す。"""
        base_dir = Path(__file__).resolve().parent.parent.parent
        settings_dir = base_dir / "user_data" / "settings"
        settings_dir.mkdir(parents=True, exist_ok=True)
        return settings_dir / "pack_enabled_overrides.json"

    def _panel_read_pack_overrides(self) -> Dict[str, bool]:
        """Pack の enabled オーバーレイ設定を読む。"""
        path = self._panel_pack_overrides_path()
        if not path.is_file():
            return {}
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, dict):
                return {}
            return {str(k): bool(v) for k, v in data.items()}
        except Exception:
            return {}

    def _panel_write_pack_overrides(self, overrides: Dict[str, bool]) -> None:
        """Pack の enabled オーバーレイ設定を atomic に保存する。"""
        path = self._panel_pack_overrides_path()
        tmp_path = path.with_suffix(".tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(overrides, f, ensure_ascii=False, indent=2)
            f.write("\n")
        os.replace(tmp_path, path)

    def _panel_set_pack_enabled(self, pack_id: str, enabled: bool) -> Dict[str, Any]:
        """Pack の enabled フラグを変更する"""
        try:
            from ..paths import discover_pack_locations
            for loc in discover_pack_locations():
                if loc.pack_id == pack_id:
                    eco_path = loc.ecosystem_json_path
                    with open(eco_path, "r", encoding="utf-8") as f:
                        eco = json.load(f)
                    default_enabled = bool(eco.get("enabled", True))
                    overrides = self._panel_read_pack_overrides()
                    if enabled == default_enabled:
                        overrides.pop(pack_id, None)
                    else:
                        overrides[pack_id] = enabled
                    self._panel_write_pack_overrides(overrides)
                    return {
                        "pack_id": pack_id,
                        "enabled": enabled,
                    }
            return {"error": f"Pack '{pack_id}' not found", "status_code": 404}
        except Exception as e:
            _log_internal_error("panel_set_pack_enabled", e)
            return {"error": _SAFE_ERROR_MSG, "status_code": 500}

    # ------------------------------------------------------------------
    # Startup Profiles
    # ------------------------------------------------------------------

    def _panel_get_startup_profiles(self) -> Dict[str, Any]:
        try:
            return self._panel_startup_profile_manager().list_profiles_payload()
        except Exception as e:
            _log_internal_error("panel_get_startup_profiles", e)
            return {"error": _SAFE_ERROR_MSG, "status_code": 500}

    def _panel_create_startup_profile(self, body: Dict[str, Any]) -> Dict[str, Any]:
        try:
            return self._panel_startup_profile_manager().create_profile(body)
        except Exception as e:
            _log_internal_error("panel_create_startup_profile", e)
            return {"error": _SAFE_ERROR_MSG, "status_code": 500}

    def _panel_update_startup_profile(self, profile_id: str, body: Dict[str, Any]) -> Dict[str, Any]:
        try:
            return self._panel_startup_profile_manager().update_profile(profile_id, body)
        except Exception as e:
            _log_internal_error("panel_update_startup_profile", e)
            return {"error": _SAFE_ERROR_MSG, "status_code": 500}

    def _panel_delete_startup_profile(self, profile_id: str) -> Dict[str, Any]:
        try:
            return self._panel_startup_profile_manager().delete_profile(profile_id)
        except Exception as e:
            _log_internal_error("panel_delete_startup_profile", e)
            return {"error": _SAFE_ERROR_MSG, "status_code": 500}

    def _panel_duplicate_startup_profile(self, profile_id: str) -> Dict[str, Any]:
        try:
            return self._panel_startup_profile_manager().duplicate_profile(profile_id)
        except Exception as e:
            _log_internal_error("panel_duplicate_startup_profile", e)
            return {"error": _SAFE_ERROR_MSG, "status_code": 500}

    def _panel_activate_startup_profile(self, profile_id: str) -> Dict[str, Any]:
        try:
            return self._panel_startup_profile_manager().activate_profile(profile_id)
        except Exception as e:
            _log_internal_error("panel_activate_startup_profile", e)
            return {"error": _SAFE_ERROR_MSG, "status_code": 500}

    def _panel_launch_startup_profile(self, profile_id: str) -> Dict[str, Any]:
        try:
            return self._panel_startup_profile_manager().launch_profile(profile_id)
        except Exception as e:
            _log_internal_error("panel_launch_startup_profile", e)
            return {"error": _SAFE_ERROR_MSG, "status_code": 500}

    # ------------------------------------------------------------------
    # Capability Graph Node Manager
    # ------------------------------------------------------------------

    def _panel_node_registry(self):
        from ..ecosystem_nodes import EcosystemNodeRegistry

        kernel = getattr(self.__class__, "kernel", None) or getattr(self, "kernel", None)
        interface_registry = getattr(kernel, "interface_registry", None) if kernel is not None else None
        registry = getattr(getattr(kernel, "lifecycle", None), "registry", None) if kernel is not None else None
        return EcosystemNodeRegistry(
            registry=registry,
            interface_registry=interface_registry,
        )

    def _panel_profile_loader(self):
        from ..profile_loader import CapabilityProfileLoader

        kernel = getattr(self.__class__, "kernel", None) or getattr(self, "kernel", None)
        interface_registry = getattr(kernel, "interface_registry", None) if kernel is not None else None
        registry = getattr(getattr(kernel, "lifecycle", None), "registry", None) if kernel is not None else None
        return CapabilityProfileLoader(
            registry=registry,
            interface_registry=interface_registry,
        )

    def _panel_profile_node_overrides_path(self) -> Path:
        base_dir = Path(__file__).resolve().parent.parent.parent
        settings_dir = base_dir / "user_data" / "settings"
        settings_dir.mkdir(parents=True, exist_ok=True)
        return settings_dir / "profile_node_overrides.json"

    def _panel_read_profile_node_overrides(self) -> Dict[str, Any]:
        path = self._panel_profile_node_overrides_path()
        if not path.is_file():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
        return data if isinstance(data, dict) else {}

    def _panel_write_profile_node_overrides(self, overrides: Dict[str, Any]) -> None:
        path = self._panel_profile_node_overrides_path()
        tmp_path = path.with_suffix(".tmp")
        tmp_path.write_text(json.dumps(overrides, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp_path, path)

    def _panel_profile_with_node_overrides(self, profile_id: str):
        from ..profile_models import load_profile_document

        profile = self._panel_profile_loader().get_profile(profile_id)
        if profile is None:
            return None

        data = profile.to_dict()
        overrides = self._panel_read_profile_node_overrides().get(profile_id, {})
        if isinstance(overrides, dict):
            enabled_add = set(str(item) for item in overrides.get("enabled_nodes", []) if item)
            disabled_add = set(str(item) for item in overrides.get("disabled_nodes", []) if item)
            enabled_nodes = set(data.get("enabled_nodes") or [])
            disabled_nodes = set(data.get("disabled_nodes") or [])
            enabled_nodes.update(enabled_add)
            disabled_nodes.update(disabled_add)
            enabled_nodes.difference_update(disabled_add)
            disabled_nodes.difference_update(enabled_add)
            data["enabled_nodes"] = sorted(enabled_nodes)
            data["disabled_nodes"] = sorted(disabled_nodes)

        return load_profile_document(
            {"version": "rumi.profile.v1", **data},
            source_path=str(profile.metadata.get("source_path") or ""),
            pack_id=profile.metadata.get("pack_id"),
            source_type=str(profile.metadata.get("source_type") or "user"),
        )

    def _panel_get_nodes(self) -> Dict[str, Any]:
        """GET /api/panel/nodes — Capability Graph node catalog."""
        try:
            registry = self._panel_node_registry()
            nodes = registry.load_all_nodes(register=True)
            return {
                "nodes": [node.to_dict() for node in nodes.values()],
                "count": len(nodes),
                "diagnostics": list(registry.diagnostics),
            }
        except Exception as e:
            _log_internal_error("panel_get_nodes", e)
            return {"error": _SAFE_ERROR_MSG, "status_code": 500}

    def _panel_get_node_detail(self, node_id: str) -> Dict[str, Any]:
        """GET /api/panel/nodes/{node_id} — Capability Graph node detail."""
        try:
            registry = self._panel_node_registry()
            node = registry.get_node(node_id)
            if node is None:
                return {"error": f"Node '{node_id}' not found", "status_code": 404}
            return {"node": node.to_dict()}
        except Exception as e:
            _log_internal_error("panel_get_node_detail", e)
            return {"error": _SAFE_ERROR_MSG, "status_code": 500}

    def _panel_get_profile_nodes(self, profile_id: str) -> Dict[str, Any]:
        """GET /api/panel/profiles/{profile_id}/nodes — profile-aware node catalog."""
        try:
            from ..profile_node_registry import ProfileNodeRegistry

            profile = self._panel_profile_with_node_overrides(profile_id)
            if profile is None:
                return {"error": f"Profile '{profile_id}' not found", "status_code": 404}
            profile_nodes = ProfileNodeRegistry(
                node_registry=self._panel_node_registry(),
                profile=profile,
            )
            nodes = [node.to_dict() for node in profile_nodes.list_enabled_nodes()]
            return {
                "profile_id": profile_id,
                "nodes": nodes,
                "count": len(nodes),
            }
        except Exception as e:
            _log_internal_error("panel_get_profile_nodes", e)
            return {"error": _SAFE_ERROR_MSG, "status_code": 500}

    def _panel_get_profile_node_state(self, profile_id: str) -> Dict[str, Any]:
        """GET /api/panel/profiles/{profile_id}/node-state — profile-scoped node state."""
        try:
            from ..profile_node_registry import ProfileNodeRegistry

            profile = self._panel_profile_with_node_overrides(profile_id)
            if profile is None:
                return {"error": f"Profile '{profile_id}' not found", "status_code": 404}
            profile_nodes = ProfileNodeRegistry(
                node_registry=self._panel_node_registry(),
                profile=profile,
            )
            state = profile_nodes.node_state()
            return {
                "profile_id": profile_id,
                "node_state": state,
                "count": len(state) if isinstance(state, list) else 1,
            }
        except Exception as e:
            _log_internal_error("panel_get_profile_node_state", e)
            return {"error": _SAFE_ERROR_MSG, "status_code": 500}

    def _panel_enable_profile_node(self, profile_id: str, node_id: str) -> Dict[str, Any]:
        return self._panel_set_profile_node_enabled(profile_id, node_id, True)

    def _panel_disable_profile_node(self, profile_id: str, node_id: str) -> Dict[str, Any]:
        return self._panel_set_profile_node_enabled(profile_id, node_id, False)

    def _panel_set_profile_node_enabled(self, profile_id: str, node_id: str, enabled: bool) -> Dict[str, Any]:
        try:
            if self._panel_profile_loader().get_profile(profile_id) is None:
                return {"error": f"Profile '{profile_id}' not found", "status_code": 404}
            if self._panel_node_registry().get_node(node_id) is None:
                return {"error": f"Node '{node_id}' not found", "status_code": 404}

            overrides = self._panel_read_profile_node_overrides()
            profile_overrides = overrides.setdefault(profile_id, {})
            if not isinstance(profile_overrides, dict):
                profile_overrides = {}
                overrides[profile_id] = profile_overrides
            enabled_nodes = set(str(item) for item in profile_overrides.get("enabled_nodes", []) if item)
            disabled_nodes = set(str(item) for item in profile_overrides.get("disabled_nodes", []) if item)
            if enabled:
                enabled_nodes.add(node_id)
                disabled_nodes.discard(node_id)
            else:
                disabled_nodes.add(node_id)
                enabled_nodes.discard(node_id)
            profile_overrides["enabled_nodes"] = sorted(enabled_nodes)
            profile_overrides["disabled_nodes"] = sorted(disabled_nodes)
            self._panel_write_profile_node_overrides(overrides)
            state = self._panel_get_profile_node_state(profile_id)
            return {
                "profile_id": profile_id,
                "node_id": node_id,
                "enabled": enabled,
                "node_state": state.get("node_state"),
            }
        except Exception as e:
            _log_internal_error("panel_set_profile_node_enabled", e)
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
        API では再起動要求フラグのみを立て、メインプロセス側で
        atexit を通るグレースフル終了を行う。
        レート制限: 前回の再起動から 60 秒以内のリクエストは拒否する。
        """
        global _last_restart_time
        now = time.time()
        elapsed = now - _last_restart_time
        if elapsed < 60.0:
            remaining = int(60.0 - elapsed) + 1
            return {
                "error": f"Restart rate limited. Try again in {remaining}s.",
                "status_code": 429,
            }
        _last_restart_time = now
        request_kernel_restart()
        logger.info("Kernel restart requested via API — flag set for graceful shutdown")
        return {"restarting": True, "message": "Kernel restart requested"}
