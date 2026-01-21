"""
初期化処理

user_data, ecosystem の初期構造を作成
"""

import json
import shutil
from pathlib import Path
from typing import Dict, Any, Optional, Callable

from .state import get_state


class Initializer:
    """初期化処理"""
    
    def __init__(self, base_dir: str = "."):
        self.base_dir = Path(base_dir)
        self.state = get_state()
    
    def initialize(
        self,
        install_default: bool = True,
        confirm_callback: Callable[[str], bool] = None
    ) -> Dict[str, Any]:
        self.state.start("初期セットアップ")
        
        created = []
        errors = []
        
        try:
            self.state.update_progress(10, "user_data を作成中...")
            created.extend(self._create_user_data())
            
            self.state.update_progress(30, "mounts.json を作成中...")
            result = self._create_mounts_json()
            if result:
                created.append(result)
            
            self.state.update_progress(50, "active_ecosystem.json を作成中...")
            result = self._create_active_ecosystem_json()
            if result:
                created.append(result)
            
            self.state.update_progress(60, "ecosystem を確認中...")
            result = self._ensure_ecosystem_dir()
            if result:
                created.append(result)
            
            self.state.update_progress(70, "flow を確認中...")
            self._check_flow_dir()
            
            if install_default:
                self.state.update_progress(80, "default pack を確認中...")
                default_result = self._install_default_pack(confirm_callback)
                if default_result.get("created"):
                    created.extend(default_result["created"])
                if default_result.get("errors"):
                    errors.extend(default_result["errors"])
                if default_result.get("skipped"):
                    self.state.log_info("default pack のインストールをスキップしました")
            
            summary = {
                "success": len(errors) == 0,
                "created": created,
                "errors": errors
            }
            
            if summary["success"]:
                self.state.complete(summary)
            else:
                self.state.fail(f"{len(errors)} 件のエラーが発生しました")
                self.state.result = summary
            
            return summary
            
        except Exception as e:
            self.state.fail(str(e))
            return {
                "success": False,
                "created": created,
                "errors": [str(e)]
            }
    
    def _create_user_data(self) -> list:
        created = []
        
        dirs = [
            "user_data",
            "user_data/chats",
            "user_data/settings",
            "user_data/cache",
            "user_data/shared",
        ]
        
        for dir_path in dirs:
            full_path = self.base_dir / dir_path
            if not full_path.exists():
                full_path.mkdir(parents=True, exist_ok=True)
                created.append(str(dir_path))
                self.state.log_info(f"作成: {dir_path}")
        
        return created
    
    def _create_mounts_json(self) -> Optional[str]:
        mounts_path = self.base_dir / "user_data" / "mounts.json"
        
        if mounts_path.exists():
            self.state.log_info("mounts.json は既に存在します")
            return None
        
        mounts_data = {
            "version": "1.0",
            "mounts": {
                "data.user": "./user_data",
                "data.cache": "./user_data/cache",
            }
        }
        
        mounts_path.parent.mkdir(parents=True, exist_ok=True)
        with open(mounts_path, "w", encoding="utf-8") as f:
            json.dump(mounts_data, f, ensure_ascii=False, indent=2)
        
        self.state.log_success("作成: user_data/mounts.json")
        return "user_data/mounts.json"
    
    def _create_active_ecosystem_json(self) -> Optional[str]:
        active_path = self.base_dir / "user_data" / "active_ecosystem.json"
        
        if active_path.exists():
            self.state.log_info("active_ecosystem.json は既に存在します")
            return None
        
        active_data = {
            "active_pack_identity": None,
            "overrides": {},
            "disabled_components": [],
            "disabled_addons": [],
            "metadata": {}
        }
        
        active_path.parent.mkdir(parents=True, exist_ok=True)
        with open(active_path, "w", encoding="utf-8") as f:
            json.dump(active_data, f, ensure_ascii=False, indent=2)
        
        self.state.log_success("作成: user_data/active_ecosystem.json")
        return "user_data/active_ecosystem.json"
    
    def _ensure_ecosystem_dir(self) -> Optional[str]:
        ecosystem_path = self.base_dir / "ecosystem"
        
        if ecosystem_path.exists():
            self.state.log_info("ecosystem/ は既に存在します")
            return None
        
        ecosystem_path.mkdir(parents=True, exist_ok=True)
        self.state.log_success("作成: ecosystem/")
        return "ecosystem"
    
    def _check_flow_dir(self) -> None:
        flow_path = self.base_dir / "flow"
        
        if flow_path.exists():
            yaml_files = list(flow_path.glob("*.flow.yaml"))
            if yaml_files:
                self.state.log_info(f"flow/ に {len(yaml_files)} 個のファイルがあります")
            else:
                self.state.log_warn("flow/ にファイルがありません")
        else:
            self.state.log_warn("flow/ が存在しません")
    
    def _install_default_pack(
        self,
        confirm_callback: Callable[[str], bool] = None
    ) -> Dict[str, Any]:
        default_dest = self.base_dir / "ecosystem" / "default"
        
        try:
            from ..defaults import get_default_pack_path
            default_src = get_default_pack_path()
        except ImportError:
            default_src = Path(__file__).parent.parent / "defaults" / "default"
        
        if not default_src.exists():
            self.state.log_warn(
                "default pack のテンプレートが見つかりません",
                f"パス: {default_src}"
            )
            return {"created": [], "errors": [], "skipped": True}
        
        if default_dest.exists():
            if confirm_callback:
                if not confirm_callback("ecosystem/default は既に存在します。上書きしますか？"):
                    return {"created": [], "errors": [], "skipped": True}
                shutil.rmtree(default_dest)
            else:
                self.state.log_info("ecosystem/default は既に存在します")
                return {"created": [], "errors": [], "skipped": True}
        else:
            if confirm_callback:
                if not confirm_callback("default pack をインストールしますか？"):
                    return {"created": [], "errors": [], "skipped": True}
        
        try:
            shutil.copytree(default_src, default_dest)
            self.state.log_success("インストール: ecosystem/default")
            return {"created": ["ecosystem/default"], "errors": [], "skipped": False}
        except Exception as e:
            self.state.log_error(f"default pack のインストールに失敗: {e}")
            return {"created": [], "errors": [str(e)], "skipped": False}
