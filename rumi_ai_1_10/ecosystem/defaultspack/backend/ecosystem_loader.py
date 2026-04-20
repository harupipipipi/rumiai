from __future__ import annotations

from typing import Any, Dict

from .backend_loader import load_all_backend_modules


def load_ecosystem(manager: Any = None, event_bus: Any = None) -> Dict[str, Any]:
    return {
        "loaded": True,
        "backend": load_all_backend_modules(manager),
        "event_bus": bool(event_bus),
    }
