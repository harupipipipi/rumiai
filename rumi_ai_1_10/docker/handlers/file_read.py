"""
file_read ハンドラ

ファイル読み取り（許可ディレクトリのみ）
.env ファイルは除外（env_read を使用）
"""

from pathlib import Path
from typing import Any, Dict
import fnmatch

META = {
    "requires_scope": True,
    "supports_modes": ["sandbox"],
    "description": "ファイル読み取り（許可ディレクトリのみ、.env除外）",
    "version": "1.0"
}

FORBIDDEN_FILES = {
    ".env", ".env.local", ".env.production", ".env.development",
}

FORBIDDEN_PATTERNS = ["*.pem", "*.key", "id_rsa*", "*.secret"]


def execute(context: Dict[str, Any], args: Dict[str, Any]) -> Dict[str, Any]:
    """ファイルを読み取る"""
    path_str = args.get("path")
    if not path_str:
        return {"success": False, "error": "Path is required"}
    
    encoding = args.get("encoding", "utf-8")
    
    try:
        path = Path(path_str).resolve()
        
        # .env ファイルチェック
        if path.name in FORBIDDEN_FILES:
            return {"success": False, "error": f"Forbidden file: {path.name}. Use env_read handler."}
        
        # 禁止パターンチェック
        for pattern in FORBIDDEN_PATTERNS:
            if fnmatch.fnmatch(path.name, pattern):
                return {"success": False, "error": f"Forbidden file pattern: {path.name}"}
        
        if not path.exists():
            return {"success": False, "error": f"File not found: {path_str}"}
        
        if not path.is_file():
            return {"success": False, "error": f"Not a file: {path_str}"}
        
        content = path.read_text(encoding=encoding)
        
        return {
            "success": True,
            "content": content,
            "path": str(path),
            "size": len(content)
        }
    
    except UnicodeDecodeError as e:
        return {"success": False, "error": f"Encoding error: {e}"}
    except Exception as e:
        return {"success": False, "error": f"Read error: {e}"}
