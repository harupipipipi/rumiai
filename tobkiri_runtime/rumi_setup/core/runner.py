"""
アプリケーション実行

app.py を venv 環境で実行
"""

import subprocess
import sys
import os
from pathlib import Path
from typing import Dict, Any, Optional

from .state import get_state


class AppRunner:
    """app.py 実行管理"""
    
    def __init__(self, base_dir: str = "."):
        self.base_dir = Path(base_dir)
        self.state = get_state()
        self._process: Optional[subprocess.Popen] = None
    
    def get_venv_python(self) -> Path:
        if sys.platform == "win32":
            return self.base_dir / ".venv" / "Scripts" / "python.exe"
        else:
            return self.base_dir / ".venv" / "bin" / "python"
    
    def get_app_path(self) -> Path:
        return self.base_dir / "app.py"
    
    def is_ready(self) -> Dict[str, Any]:
        venv_python = self.get_venv_python()
        app_path = self.get_app_path()
        
        issues = []
        
        if not venv_python.exists():
            issues.append(f".venv が見つかりません: {venv_python}")
        
        if not app_path.exists():
            issues.append(f"app.py が見つかりません: {app_path}")
        
        return {
            "ready": len(issues) == 0,
            "venv_python": str(venv_python),
            "app_path": str(app_path),
            "issues": issues
        }
    
    def run(self, port: int = 5000, background: bool = True) -> Dict[str, Any]:
        self.state.start("アプリケーション起動")
        
        check = self.is_ready()
        if not check["ready"]:
            for issue in check["issues"]:
                self.state.log_error(issue)
            self.state.fail("実行準備ができていません")
            return {"success": False, "issues": check["issues"]}
        
        venv_python = self.get_venv_python()
        app_path = self.get_app_path()
        
        env = os.environ.copy()
        env["FLASK_RUN_PORT"] = str(port)
        
        try:
            self.state.log_info(f"起動中: {venv_python} {app_path}")
            
            if background:
                self._process = subprocess.Popen(
                    [str(venv_python), str(app_path)],
                    cwd=str(self.base_dir),
                    env=env,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE
                )
                
                self.state.log_success(f"起動しました (PID: {self._process.pid})")
                self.state.log_info(f"URL: http://localhost:{port}")
                self.state.complete({
                    "success": True,
                    "pid": self._process.pid,
                    "url": f"http://localhost:{port}"
                })
                
                return {
                    "success": True,
                    "pid": self._process.pid,
                    "url": f"http://localhost:{port}"
                }
            else:
                result = subprocess.run(
                    [str(venv_python), str(app_path)],
                    cwd=str(self.base_dir),
                    env=env
                )
                return {"success": result.returncode == 0}
                
        except Exception as e:
            self.state.fail(str(e))
            return {"success": False, "error": str(e)}
    
    def stop(self) -> Dict[str, Any]:
        if self._process is None:
            return {"success": False, "error": "実行中のプロセスがありません"}
        
        try:
            self._process.terminate()
            self._process.wait(timeout=5)
            self._process = None
            return {"success": True}
        except Exception as e:
            return {"success": False, "error": str(e)}
    
    def get_run_command(self, port: int = 5000) -> str:
        venv_python = self.get_venv_python()
        app_path = self.get_app_path()
        return f'"{venv_python}" "{app_path}"'
