from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional


BACKEND_ROOT = Path(__file__).resolve().parent


def discover_backend_modules() -> List[str]:
    found: List[str] = []
    for child in sorted(BACKEND_ROOT.iterdir()):
        if child.is_dir() and (child / "module.json").is_file():
            found.append(child.name)
    return found


def load_backend_module(module_id: str, manager: Any = None) -> Dict[str, Any]:
    module_json = BACKEND_ROOT / module_id / "module.json"
    if not module_json.is_file():
        return {"loaded": False, "module_id": module_id, "error": "module.json not found"}
    try:
        spec = json.loads(module_json.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"loaded": False, "module_id": module_id, "error": str(exc)}
    return {"loaded": True, "module_id": module_id, "spec": spec, "manager": bool(manager)}


def load_all_backend_modules(manager: Any = None) -> Dict[str, Any]:
    return {mid: load_backend_module(mid, manager=manager) for mid in discover_backend_modules()}
