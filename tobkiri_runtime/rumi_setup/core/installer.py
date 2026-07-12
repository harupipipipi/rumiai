"""
Pack インストーラー

Git リポジトリからの Pack インストール
"""

import subprocess
import shutil
from pathlib import Path
from typing import Dict, Any

from .state import get_state


class PackInstaller:
    """Pack インストーラー"""
    
    DEFAULT_PACK_REPO = "https://github.com/haru/rumi-default-pack.git"
    
    def __init__(self, base_dir: str = "."):
        self.base_dir = Path(base_dir)
        self.state = get_state()
    
    def install_from_git(
        self,
        repo_url: str,
        pack_name: str = None,
        branch: str = "main"
    ) -> Dict[str, Any]:
        self.state.start(f"Pack インストール: {repo_url}")
        
        if not pack_name:
            pack_name = repo_url.rstrip("/").split("/")[-1].replace(".git", "")
        
        target_path = self.base_dir / "ecosystem" / pack_name
        
        if target_path.exists():
            self.state.log_warn(f"{pack_name} は既に存在します")
            return {
                "success": False,
                "error": "already_exists",
                "path": str(target_path)
            }
        
        try:
            self.state.update_progress(30, "リポジトリをクローン中...")
            
            result = subprocess.run(
                ["git", "clone", "--branch", branch, "--depth", "1", repo_url, str(target_path)],
                capture_output=True,
                text=True,
                timeout=120
            )
            
            if result.returncode != 0:
                self.state.fail(f"Git clone 失敗: {result.stderr}")
                return {
                    "success": False,
                    "error": result.stderr
                }
            
            self.state.update_progress(80, "インストール完了を確認中...")
            
            ecosystem_json = target_path / "backend" / "ecosystem.json"
            if not ecosystem_json.exists():
                ecosystem_json = target_path / "ecosystem.json"
            
            if not ecosystem_json.exists():
                self.state.log_warn("ecosystem.json が見つかりません")
            
            self.state.log_success(f"インストール完了: {pack_name}")
            self.state.complete({
                "success": True,
                "pack_name": pack_name,
                "path": str(target_path)
            })
            
            return {
                "success": True,
                "pack_name": pack_name,
                "path": str(target_path)
            }
            
        except subprocess.TimeoutExpired:
            self.state.fail("タイムアウトしました")
            return {"success": False, "error": "timeout"}
        except Exception as e:
            self.state.fail(str(e))
            return {"success": False, "error": str(e)}
    
    def install_default(self) -> Dict[str, Any]:
        return self.install_from_git(
            self.DEFAULT_PACK_REPO,
            pack_name="default"
        )
    
    def uninstall(self, pack_name: str) -> Dict[str, Any]:
        self.state.start(f"Pack アンインストール: {pack_name}")
        
        target_path = self.base_dir / "ecosystem" / pack_name
        
        if not target_path.exists():
            self.state.fail("Pack が見つかりません")
            return {
                "success": False,
                "error": "not_found"
            }
        
        try:
            self.state.update_progress(50, "削除中...")
            shutil.rmtree(target_path)
            
            self.state.log_success(f"削除完了: {pack_name}")
            self.state.complete({"success": True, "pack_name": pack_name})
            
            return {
                "success": True,
                "pack_name": pack_name
            }
        except Exception as e:
            self.state.fail(str(e))
            return {"success": False, "error": str(e)}
    
    def list_packs(self) -> Dict[str, Any]:
        ecosystem = self.base_dir / "ecosystem"
        
        if not ecosystem.exists():
            return {"packs": []}
        
        packs = []
        for pack_dir in ecosystem.iterdir():
            if pack_dir.is_dir() and not pack_dir.name.startswith("."):
                pack_info = {
                    "name": pack_dir.name,
                    "path": str(pack_dir)
                }
                
                for json_path in [
                    pack_dir / "backend" / "ecosystem.json",
                    pack_dir / "ecosystem.json"
                ]:
                    if json_path.exists():
                        try:
                            import json
                            with open(json_path, "r", encoding="utf-8") as f:
                                data = json.load(f)
                            pack_info["pack_id"] = data.get("pack_id")
                            pack_info["version"] = data.get("version")
                            pack_info["pack_identity"] = data.get("pack_identity")
                        except Exception:
                            pass
                        break
                
                packs.append(pack_info)
        
        return {"packs": packs}
