from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

UI_ROOTS = [Path(__file__).parent / "ui", Path(__file__).parent / "ui_shell"]


def _iter_ui_roots() -> List[Path]:
    return [root for root in UI_ROOTS if root.is_dir()]


def _module_specs() -> Dict[str, Path]:
    specs: Dict[str, Path] = {}
    for root in _iter_ui_roots():
        root_spec = root / "module.json"
        if root_spec.is_file():
            specs[root.name] = root_spec
        for child in sorted(root.iterdir()):
            child_spec = child / "module.json"
            if child.is_dir() and child_spec.is_file():
                specs[child.name] = child_spec
    return specs


def discover_frontend_modules() -> List[str]:
    return sorted(_module_specs().keys())


def load_frontend_module(module_id: str) -> Dict[str, Any]:
    module_json = _module_specs().get(module_id)
    if module_json is None:
        return {"loaded": False, "module_id": module_id, "error": "module.json not found"}
    try:
        spec = json.loads(module_json.read_text(encoding="utf-8"))
        return {"loaded": True, "module_id": module_id, "spec": spec}
    except Exception as exc:
        logger.warning("Failed to load frontend module %s: %s", module_id, exc)
        return {"loaded": False, "module_id": module_id, "error": str(exc)}


def load_all_frontend_modules() -> Dict[str, Any]:
    return {mid: load_frontend_module(mid) for mid in discover_frontend_modules()}
