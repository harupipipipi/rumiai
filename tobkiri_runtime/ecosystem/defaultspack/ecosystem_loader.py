from __future__ import annotations

from typing import Any, Dict


def load_defaultspack(manager: Any = None, event_bus: Any = None) -> Dict[str, Any]:
    from .backend.backend_loader import load_all_backend_modules
    from .frontend.frontend_loader import load_all_frontend_modules

    backend_results = load_all_backend_modules(manager)
    frontend_results = load_all_frontend_modules()
    merged = {**backend_results, **frontend_results}
    loaded_count = sum(1 for v in merged.values() if v.get("loaded"))
    error_count = sum(1 for v in merged.values() if not v.get("loaded"))
    return {
        "loaded": True,
        "backend": backend_results,
        "frontend": frontend_results,
        "loaded_count": loaded_count,
        "error_count": error_count,
        "event_bus": bool(event_bus),
    }
