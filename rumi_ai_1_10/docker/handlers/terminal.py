"""
terminal ハンドラ

ターミナルコマンド実行（許可ディレクトリ内のみ）
"""

import subprocess
import shlex
from pathlib import Path
from typing import Any, Dict, List

META = {
    "requires_scope": True,
    "supports_modes": ["sandbox"],
    "description": "ターミナルコマンド実行（許可ディレクトリ内のみ）",
    "version": "1.0"
}

FORBIDDEN_COMMANDS = {"rm -rf /", "rm -rf ~", "mkfs", "dd if=/dev/zero"}
FORBIDDEN_PATTERNS = ["sudo ", "su ", "chmod 777", "curl | sh", "wget | sh"]


def execute(context: Dict[str, Any], args: Dict[str, Any]) -> Dict[str, Any]:
    """ターミナルコマンドを実行"""
    command = args.get("command")
    if not command:
        return {"success": False, "error": "Command is required"}
    
    cwd = args.get("cwd", "/sandbox")
    timeout = args.get("timeout", 30)
    
    # 禁止コマンドチェック
    if command in FORBIDDEN_COMMANDS:
        return {"success": False, "error": "Forbidden command"}
    
    for pattern in FORBIDDEN_PATTERNS:
        if pattern in command:
            return {"success": False, "error": f"Forbidden command pattern: {pattern}"}
    
    # cd .. によるエスケープを検出
    if "cd .." in command or "cd /" in command:
        return {"success": False, "error": "Directory escape not allowed"}
    
    try:
        result = subprocess.run(
            command,
            shell=True,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout
        )
        
        return {
            "success": True,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode
        }
    
    except subprocess.TimeoutExpired:
        return {"success": False, "error": f"Command timed out after {timeout}s"}
    except Exception as e:
        return {"success": False, "error": f"Execution error: {e}"}
