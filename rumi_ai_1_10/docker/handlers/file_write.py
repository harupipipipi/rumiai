"""
file_write ハンドラ

ファイル書き込み（許可ディレクトリのみ）
"""

from pathlib import Path
from typing import Any, Dict

META = {
    "requires_scope": True,
    "supports_modes": ["sandbox"],
    "description": "ファイル書き込み（許可ディレクトリのみ）",
    "version": "1.0"
}

FORBIDDEN_FILES = {
    ".env", ".env.local", ".env.production", ".env.development",
    ".bashrc", ".zshrc", ".profile",
}


def execute(context: Dict[str, Any], args: Dict[str, Any]) -> Dict[str, Any]:
    """ファイルを書き込む"""
    path_str = args.get("path")
    content = args.get("content")
    
    if not path_str:
        return {"success": False, "error": "Path is required"}
    
    if content is None:
        return {"success": False, "error": "Content is required"}
    
    encoding = args.get("encoding", "utf-8")
    create_parents = args.get("create_parents", True)
    
    try:
        path = Path(path_str).resolve()
        
        if path.name in FORBIDDEN_FILES:
            return {"success": False, "error": f"Forbidden file: {path.name}"}
        
        if create_parents:
            path.parent.mkdir(parents=True, exist_ok=True)
        
        path.write_text(content, encoding=encoding)
        
        return {
            "success": True,
            "path": str(path),
            "size": len(content)
        }
    
    except Exception as e:
        return {"success": False, "error": f"Write error: {e}"}
