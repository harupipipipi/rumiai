"""
環境チェッカー

Git, Docker, pip などの存在確認
"""

import subprocess
import shutil
import sys
from dataclasses import dataclass
from typing import Optional, List, Dict, Any

from .state import get_state


@dataclass
class CheckResult:
    """チェック結果"""
    name: str
    available: bool
    version: Optional[str] = None
    path: Optional[str] = None
    required: bool = True
    message: Optional[str] = None


class EnvironmentChecker:
    """環境チェッカー"""
    
    def __init__(self):
        self.state = get_state()
    
    def check_all(self) -> Dict[str, Any]:
        self.state.start("環境チェック")
        
        results: List[CheckResult] = []
        checks = [
            ("Python", self.check_python, True),
            ("pip", self.check_pip, True),
            ("Git", self.check_git, True),
            ("Docker", self.check_docker, False),
        ]
        
        total = len(checks)
        for i, (name, check_fn, required) in enumerate(checks):
            self.state.update_progress(
                int((i / total) * 100),
                f"{name} をチェック中..."
            )
            
            result = check_fn()
            result.required = required
            results.append(result)
            
            if result.available:
                self.state.log_success(
                    f"{name}: {result.version or 'OK'}",
                    result.path
                )
            elif required:
                self.state.log_error(
                    f"{name}: 見つかりません",
                    result.message
                )
            else:
                self.state.log_warn(
                    f"{name}: 見つかりません（推奨）",
                    result.message
                )
        
        required_ok = all(r.available for r in results if r.required)
        all_ok = all(r.available for r in results)
        
        summary = {
            "success": required_ok,
            "all_available": all_ok,
            "checks": [
                {
                    "name": r.name,
                    "available": r.available,
                    "version": r.version,
                    "path": r.path,
                    "required": r.required,
                    "message": r.message
                }
                for r in results
            ]
        }
        
        if required_ok:
            self.state.complete(summary)
        else:
            self.state.fail("必須の依存関係が不足しています")
            self.state.result = summary
        
        return summary
    
    def check_python(self) -> CheckResult:
        try:
            version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
            path = sys.executable
            
            if sys.version_info < (3, 9):
                return CheckResult(
                    name="Python",
                    available=False,
                    version=version,
                    path=path,
                    message="Python 3.9 以上が必要です"
                )
            
            return CheckResult(
                name="Python",
                available=True,
                version=version,
                path=path
            )
        except Exception as e:
            return CheckResult(
                name="Python",
                available=False,
                message=str(e)
            )
    
    def check_pip(self) -> CheckResult:
        try:
            result = subprocess.run(
                [sys.executable, "-m", "pip", "--version"],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0:
                output = result.stdout.strip()
                parts = output.split()
                version = parts[1] if len(parts) > 1 else "unknown"
                
                return CheckResult(
                    name="pip",
                    available=True,
                    version=version,
                    path=parts[3] if len(parts) > 3 else None
                )
            else:
                return CheckResult(
                    name="pip",
                    available=False,
                    message=result.stderr or "pip が見つかりません"
                )
        except Exception as e:
            return CheckResult(
                name="pip",
                available=False,
                message=str(e)
            )
    
    def check_git(self) -> CheckResult:
        try:
            path = shutil.which("git")
            if not path:
                return CheckResult(
                    name="Git",
                    available=False,
                    message="Git がインストールされていません"
                )
            
            result = subprocess.run(
                ["git", "--version"],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0:
                output = result.stdout.strip()
                version = output.replace("git version ", "")
                
                return CheckResult(
                    name="Git",
                    available=True,
                    version=version,
                    path=path
                )
            else:
                return CheckResult(
                    name="Git",
                    available=False,
                    message=result.stderr or "Git のバージョン取得に失敗"
                )
        except Exception as e:
            return CheckResult(
                name="Git",
                available=False,
                message=str(e)
            )
    
    def check_docker(self) -> CheckResult:
        try:
            path = shutil.which("docker")
            if not path:
                return CheckResult(
                    name="Docker",
                    available=False,
                    required=False,
                    message="Docker は将来のセキュリティ機能に推奨されます"
                )
            
            result = subprocess.run(
                ["docker", "--version"],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0:
                output = result.stdout.strip()
                parts = output.split(",")[0]
                version = parts.replace("Docker version ", "")
                
                return CheckResult(
                    name="Docker",
                    available=True,
                    version=version,
                    path=path,
                    required=False
                )
            else:
                return CheckResult(
                    name="Docker",
                    available=False,
                    required=False,
                    message=result.stderr or "Docker のバージョン取得に失敗"
                )
        except Exception as e:
            return CheckResult(
                name="Docker",
                available=False,
                required=False,
                message=str(e)
            )
