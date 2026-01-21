"""
リカバリー処理

壊れた ecosystem を検出・修復
"""

import json
from pathlib import Path
from typing import Dict, Any, List

from .state import get_state
from .initializer import Initializer


class Recovery:
    """リカバリー処理"""
    
    def __init__(self, base_dir: str = "."):
        self.base_dir = Path(base_dir)
        self.state = get_state()
    
    def diagnose(self) -> Dict[str, Any]:
        self.state.start("診断")
        
        issues: List[Dict[str, Any]] = []
        
        self.state.update_progress(20, "user_data を確認中...")
        issues.extend(self._check_user_data())
        
        self.state.update_progress(40, "ecosystem を確認中...")
        issues.extend(self._check_ecosystem())
        
        self.state.update_progress(60, "flow を確認中...")
        issues.extend(self._check_flow())
        
        self.state.update_progress(80, "設定ファイルを確認中...")
        issues.extend(self._check_config_files())
        
        summary = {
            "healthy": len([i for i in issues if i["severity"] == "error"]) == 0,
            "issues": issues,
            "issue_count": {
                "error": len([i for i in issues if i["severity"] == "error"]),
                "warn": len([i for i in issues if i["severity"] == "warn"]),
                "info": len([i for i in issues if i["severity"] == "info"]),
            }
        }
        
        if summary["healthy"]:
            self.state.log_success("問題は見つかりませんでした")
            self.state.complete(summary)
        else:
            error_count = summary["issue_count"]["error"]
            self.state.log_warn(f"{error_count} 件の問題が見つかりました")
            self.state.complete(summary)
        
        return summary
    
    def recover(self, auto_fix: bool = True) -> Dict[str, Any]:
        self.state.start("リカバリー")
        
        self.state.update_progress(10, "診断中...")
        diagnosis = self._diagnose_internal()
        
        if diagnosis["healthy"]:
            self.state.log_success("システムは正常です")
            self.state.complete({"recovered": [], "diagnosis": diagnosis})
            return {"success": True, "recovered": [], "diagnosis": diagnosis}
        
        recovered = []
        errors = []
        
        if auto_fix:
            self.state.update_progress(30, "修復中...")
            
            for issue in diagnosis["issues"]:
                if issue["severity"] == "error" and issue.get("auto_fix"):
                    self.state.log_info(f"修復: {issue['message']}")
                    
                    try:
                        fix_result = self._apply_fix(issue)
                        if fix_result["success"]:
                            recovered.append(issue["id"])
                            self.state.log_success(f"修復完了: {issue['id']}")
                        else:
                            errors.append(fix_result.get("error", "unknown"))
                            self.state.log_error(f"修復失敗: {issue['id']}")
                    except Exception as e:
                        errors.append(str(e))
                        self.state.log_error(f"修復エラー: {e}")
        
        summary = {
            "success": len(errors) == 0,
            "recovered": recovered,
            "errors": errors,
            "diagnosis": diagnosis
        }
        
        if summary["success"]:
            self.state.complete(summary)
        else:
            self.state.fail(f"{len(errors)} 件の修復に失敗しました")
            self.state.result = summary
        
        return summary
    
    def _diagnose_internal(self) -> Dict[str, Any]:
        issues = []
        issues.extend(self._check_user_data())
        issues.extend(self._check_ecosystem())
        issues.extend(self._check_flow())
        issues.extend(self._check_config_files())
        
        return {
            "healthy": len([i for i in issues if i["severity"] == "error"]) == 0,
            "issues": issues
        }
    
    def _check_user_data(self) -> List[Dict[str, Any]]:
        issues = []
        
        user_data = self.base_dir / "user_data"
        if not user_data.exists():
            issues.append({
                "id": "user_data_missing",
                "severity": "error",
                "message": "user_data ディレクトリが存在しません",
                "auto_fix": True,
                "fix_action": "create_user_data"
            })
            self.state.log_error("user_data/ が見つかりません")
        else:
            self.state.log_success("user_data/ OK")
            
            for subdir in ["chats", "settings", "cache"]:
                subpath = user_data / subdir
                if not subpath.exists():
                    issues.append({
                        "id": f"user_data_{subdir}_missing",
                        "severity": "warn",
                        "message": f"user_data/{subdir} が存在しません",
                        "auto_fix": True,
                        "fix_action": "create_directory",
                        "fix_args": {"path": str(subpath)}
                    })
        
        return issues
    
    def _check_ecosystem(self) -> List[Dict[str, Any]]:
        issues = []
        
        ecosystem = self.base_dir / "ecosystem"
        if not ecosystem.exists():
            issues.append({
                "id": "ecosystem_missing",
                "severity": "error",
                "message": "ecosystem ディレクトリが存在しません",
                "auto_fix": True,
                "fix_action": "create_directory",
                "fix_args": {"path": str(ecosystem)}
            })
            self.state.log_error("ecosystem/ が見つかりません")
        else:
            packs = [d for d in ecosystem.iterdir() if d.is_dir() and not d.name.startswith(".")]
            if not packs:
                issues.append({
                    "id": "no_packs",
                    "severity": "warn",
                    "message": "ecosystem に Pack がありません",
                    "auto_fix": False
                })
                self.state.log_warn("Pack が見つかりません")
            else:
                self.state.log_success(f"ecosystem/ に {len(packs)} Pack")
        
        return issues
    
    def _check_flow(self) -> List[Dict[str, Any]]:
        issues = []
        
        flow = self.base_dir / "flow"
        if not flow.exists():
            issues.append({
                "id": "flow_missing",
                "severity": "error",
                "message": "flow ディレクトリが存在しません",
                "auto_fix": False
            })
            self.state.log_error("flow/ が見つかりません")
        else:
            yaml_files = list(flow.glob("*.flow.yaml"))
            if not yaml_files:
                issues.append({
                    "id": "no_flow_files",
                    "severity": "error",
                    "message": "flow に YAML ファイルがありません",
                    "auto_fix": False
                })
                self.state.log_error("Flow ファイルが見つかりません")
            else:
                self.state.log_success(f"flow/ に {len(yaml_files)} ファイル")
        
        return issues
    
    def _check_config_files(self) -> List[Dict[str, Any]]:
        issues = []
        
        mounts_path = self.base_dir / "user_data" / "mounts.json"
        if mounts_path.exists():
            try:
                with open(mounts_path, "r", encoding="utf-8") as f:
                    json.load(f)
                self.state.log_success("mounts.json OK")
            except json.JSONDecodeError as e:
                issues.append({
                    "id": "mounts_json_invalid",
                    "severity": "error",
                    "message": f"mounts.json が不正: {e}",
                    "auto_fix": True,
                    "fix_action": "recreate_mounts_json"
                })
                self.state.log_error("mounts.json が破損しています")
        
        active_path = self.base_dir / "user_data" / "active_ecosystem.json"
        if active_path.exists():
            try:
                with open(active_path, "r", encoding="utf-8") as f:
                    json.load(f)
                self.state.log_success("active_ecosystem.json OK")
            except json.JSONDecodeError as e:
                issues.append({
                    "id": "active_ecosystem_json_invalid",
                    "severity": "error",
                    "message": f"active_ecosystem.json が不正: {e}",
                    "auto_fix": True,
                    "fix_action": "recreate_active_ecosystem_json"
                })
                self.state.log_error("active_ecosystem.json が破損しています")
        
        return issues
    
    def _apply_fix(self, issue: Dict[str, Any]) -> Dict[str, Any]:
        action = issue.get("fix_action")
        args = issue.get("fix_args", {})
        
        if action == "create_user_data":
            initializer = Initializer(str(self.base_dir))
            initializer._create_user_data()
            return {"success": True}
        
        elif action == "create_directory":
            path = Path(args["path"])
            path.mkdir(parents=True, exist_ok=True)
            return {"success": True}
        
        elif action == "recreate_mounts_json":
            initializer = Initializer(str(self.base_dir))
            mounts_path = self.base_dir / "user_data" / "mounts.json"
            if mounts_path.exists():
                mounts_path.unlink()
            initializer._create_mounts_json()
            return {"success": True}
        
        elif action == "recreate_active_ecosystem_json":
            initializer = Initializer(str(self.base_dir))
            active_path = self.base_dir / "user_data" / "active_ecosystem.json"
            if active_path.exists():
                active_path.unlink()
            initializer._create_active_ecosystem_json()
            return {"success": True}
        
        return {"success": False, "error": f"Unknown fix action: {action}"}
