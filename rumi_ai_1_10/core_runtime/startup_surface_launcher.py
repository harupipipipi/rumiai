"""Open the launched startup profile's user-facing surface after restart."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def launch_pending_startup_profile_surface(
    *,
    active_manager: Optional[Any] = None,
    desktop_handler: Optional[Any] = None,
) -> Dict[str, Any]:
    """Consume a pending startup-profile surface launch request."""
    active = active_manager
    if active is None:
        try:
            from backend_core.ecosystem.active_ecosystem import get_active_ecosystem_manager

            active = get_active_ecosystem_manager()
        except Exception as exc:
            logger.debug("active ecosystem manager is unavailable", exc_info=True)
            return {"launched": False, "reason": "active_ecosystem_unavailable", "error": str(exc)}

    if not active.get_metadata("startup_surface_open_pending", False):
        return {"launched": False, "reason": "not_pending"}

    base_pack = str(active.get_metadata("startup_base_pack", "") or "").strip()
    profile_id = str(active.get_metadata("startup_profile_id", "") or "").strip()
    surfaces = active.get_metadata("startup_profile_surfaces", {}) or {}
    mode = _resolve_surface_mode(surfaces)

    result: Dict[str, Any] = {
        "launched": False,
        "profile_id": profile_id,
        "pack_id": base_pack,
        "surface": mode,
    }

    try:
        if not base_pack:
            result["reason"] = "missing_base_pack"
            return result

        handler = desktop_handler or _get_desktop_capability_handler()
        if handler is None:
            result["reason"] = "desktop_capability_unavailable"
            return result

        launch = handler.handle_execute(
            principal_id=base_pack,
            args={
                "pack_id": base_pack,
                "action": "launch",
                "env": _surface_env(mode),
            },
            grant_config={
                "allowed_packs": [base_pack],
                "port": 8765,
            },
        )
        result["launch"] = launch
        app = launch.get("app") if isinstance(launch, dict) else None
        result["launched"] = bool(isinstance(app, dict) and app.get("success"))
        if not result["launched"]:
            result["reason"] = "launch_failed"
        return result
    except Exception as exc:
        logger.warning("Failed to open startup profile surface", exc_info=True)
        result["reason"] = "exception"
        result["error"] = str(exc)
        return result
    finally:
        try:
            active.set_metadata("startup_surface_open_pending", False)
            active.set_metadata("startup_surface_open_result", result)
        except Exception:
            logger.debug("failed to record startup surface launch result", exc_info=True)


def _get_desktop_capability_handler() -> Optional[Any]:
    try:
        from .di_container import get_container

        return get_container().get_or_none("desktop_capability_handler")
    except Exception:
        logger.debug("desktop capability handler is unavailable", exc_info=True)
        return None


def _resolve_surface_mode(surfaces: Any) -> str:
    if not isinstance(surfaces, dict):
        return "browser"
    preferred = str(surfaces.get("preferred") or "").strip().lower()
    enabled = {
        str(surface).strip().lower()
        for surface in surfaces.get("enabled", [])
        if isinstance(surface, str)
    }
    if preferred in {"desktop", "webview", "native"}:
        return "desktop"
    if preferred in {"browser", "web"}:
        return "browser"
    if "desktop" in enabled and "browser" not in enabled and "web" not in enabled:
        return "desktop"
    return "browser"


def _surface_env(mode: str) -> Dict[str, str]:
    env = {
        "RUMI_PROFILE_SURFACE": mode,
        "RUMI_DEFAULTSPACK_OPEN_BROWSER": "1",
    }
    if mode == "desktop":
        env["RUMI_DEFAULTSPACK_SURFACE"] = "webview"
    else:
        env["RUMI_DEFAULTSPACK_SURFACE"] = "browser"
    return env
