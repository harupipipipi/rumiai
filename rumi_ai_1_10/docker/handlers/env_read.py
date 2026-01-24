"""
env_read ハンドラ

環境変数読み取り（キー単位でアクセス制御）
"""

import os
from pathlib import Path
from typing import Any, Dict

META = {
    "requires_scope": True,
    "supports_modes": ["sandbox"],
    "description": "環境変数の読み取り（許可キーのみ）",
    "version": "1.0"
}


def execute(context: Dict[str, Any], args: Dict[str, Any]) -> Dict[str, Any]:
    """環境変数を読み取る"""
    allowed_keys = set(context.get("allowed_keys", []))
    requested_keys = args.get("keys")
    env_file = args.get("env_file", ".env")
    
    allow_all = "*" in allowed_keys
    
    if requested_keys is None:
        target_keys = None if allow_all else allowed_keys
    else:
        if allow_all:
            target_keys = set(requested_keys)
        else:
            target_keys = set(requested_keys) & allowed_keys
    
    if target_keys is not None and not target_keys:
        return {"success": False, "error": "No allowed keys requested"}
    
    values = {}
    
    # コンテナ内の環境変数から取得
    if target_keys is None:
        env_vars = _parse_env_file(Path(env_file))
        values = env_vars
    else:
        for key in target_keys:
            value = os.environ.get(key)
            if value is not None:
                values[key] = value
    
    return {
        "success": True,
        "values": values,
        "keys_found": list(values.keys())
    }


def _parse_env_file(path: Path) -> Dict[str, str]:
    """シンプルな.envパーサー"""
    result = {}
    if not path.exists():
        return result
    
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, _, value = line.partition("=")
                    key = key.strip()
                    value = value.strip().strip('"').strip("'")
                    result[key] = value
    except Exception:
        pass
    
    return result
