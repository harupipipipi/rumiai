"""
初期化処理

user_data, ecosystem の初期構造を作成
"""

import json
from pathlib import Path
from typing import Dict, Any, Optional, Callable

from core_runtime.setup_pack import get_setup_pack_manager
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
                self.state.update_progress(80, "setup pack を確認中...")
                default_result = self._prepare_setup_pack_targets(confirm_callback)
                if default_result.get("created"):
                    created.extend(default_result["created"])
                if default_result.get("errors"):
                    errors.extend(default_result["errors"])
                if default_result.get("skipped"):
                    self.state.log_info("setup pack の準備をスキップしました")
                else:
                    selected_setup_pack_ids = list(default_result.get("selected_setup_pack_ids") or [])
                    if selected_setup_pack_ids:
                        install_result = get_setup_pack_manager().install(selected_setup_pack_ids)
                        default_result["install_result"] = install_result
                        if install_result.get("error") or not install_result.get("installed"):
                            errors.append({
                                "stage": "setup_pack_install",
                                "selected_setup_pack_ids": selected_setup_pack_ids,
                                "result": install_result,
                            })
                        else:
                            self.state.log_success(
                                "setup pack をインストールしました",
                                f"対象: {', '.join(selected_setup_pack_ids)}"
                            )
                    else:
                        self.state.log_info("選択された setup pack がないため install をスキップしました")
            
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
        """
        user_dataディレクトリを作成
        
        Note: 公式は汎用ディレクトリのみ作成。
              chats, shared などのドメイン固有ディレクトリは
              ecosystem側のコンポーネント(setup.py)で作成させる。
        """
        created = []
        
        # 公式は汎用ディレクトリのみ定義
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
                # 公式は汎用マウントのみ定義
                # 具体的なマウントはコンポーネントが自己登録する
                "data.user": "./user_data",
                "data.chats": "./user_data/chats",
                "data.cache": "./user_data/cache",
                "data.settings": "./user_data/settings",
                "data.shared": "./user_data/shared",
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
    
    def _prepare_setup_pack_targets(
        self,
        confirm_callback: Callable[[str], bool] = None
    ) -> Dict[str, Any]:
        setup_pack_root = self.base_dir / "ecosystem" / "setup_pack"
        if not setup_pack_root.exists():
            self.state.log_warn(
                "setup_pack/ が見つかりません",
                f"パス: {setup_pack_root}"
            )
            return {
                "created": [],
                "errors": [],
                "skipped": True,
                "available": [],
                "available_setup_pack_ids": [],
                "selected_setup_pack_ids": [],
                "missing": [],
            }

        available = []
        available_setup_pack_ids = []
        missing = []
        for pack_json in sorted(setup_pack_root.glob("*/pack.json")):
            try:
                data = json.loads(pack_json.read_text(encoding="utf-8"))
            except Exception as e:
                self.state.log_warn(
                    "setup pack 定義を読み込めません",
                    f"パス: {pack_json} / {e}"
                )
                continue

            setup_pack_id = str(data.get("pack_id") or pack_json.parent.name).strip()
            target_pack_id = str(
                data.get("target_pack_id") or data.get("pack_id") or pack_json.parent.name
            ).strip()
            if not target_pack_id:
                continue

            target_path = self.base_dir / "ecosystem" / target_pack_id
            target_rel = f"ecosystem/{target_pack_id}"
            if target_path.exists():
                available.append(target_rel)
                if setup_pack_id:
                    available_setup_pack_ids.append(setup_pack_id)
                self.state.log_info(f"setup pack target を確認: {target_rel}")
            else:
                missing.append(target_rel)
                self.state.log_warn(
                    "setup pack target が見つかりません",
                    f"パス: {target_path}"
                )

        if not available:
            return {
                "created": [],
                "errors": [],
                "skipped": True,
                "available": [],
                "available_setup_pack_ids": [],
                "selected_setup_pack_ids": [],
                "missing": missing,
            }

        seen_setup_pack_ids = set()
        normalized_setup_pack_ids = []
        for setup_pack_id in available_setup_pack_ids:
            if setup_pack_id in seen_setup_pack_ids:
                continue
            normalized_setup_pack_ids.append(setup_pack_id)
            seen_setup_pack_ids.add(setup_pack_id)

        selected_setup_pack_ids = list(normalized_setup_pack_ids)
        if confirm_callback is not None:
            selected_setup_pack_ids = []
            for setup_pack_id in normalized_setup_pack_ids:
                should_include = confirm_callback(
                    f"setup pack ({setup_pack_id}) を初期セットアップに含めますか？"
                )
                if should_include:
                    selected_setup_pack_ids.append(setup_pack_id)
                else:
                    self.state.log_info(f"setup pack をスキップ: {setup_pack_id}")

        return {
            "created": [],
            "errors": [],
            "skipped": len(selected_setup_pack_ids) == 0,
            "available": available,
            "available_setup_pack_ids": normalized_setup_pack_ids,
            "selected_setup_pack_ids": selected_setup_pack_ids,
            "missing": missing,
        }
