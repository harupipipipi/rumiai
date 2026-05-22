"""Open the launched startup profile's user-facing surface after restart."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from .surface_launch_target import (
    normalize_surface_launch_target,
    resolve_surface_mode,
    surface_env,
)
from .runtime_port import resolve_runtime_port

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
    launch_target = normalize_surface_launch_target(
        active.get_metadata("startup_surface_launch_target", {}) or {},
        fallback_pack_id=base_pack,
        surfaces=surfaces,
    )
    mode = (launch_target or {}).get("surface") or resolve_surface_mode(surfaces)
    target_pack = str((launch_target or {}).get("pack_id") or "").strip()
    principal_id = str((launch_target or {}).get("principal_id") or target_pack).strip()

    result: Dict[str, Any] = {
        "launched": False,
        "profile_id": profile_id,
        "pack_id": target_pack or base_pack,
        "surface": mode,
    }

    try:
        if not launch_target or not target_pack:
            result["reason"] = "missing_launch_target"
            return result

        handler = desktop_handler or _get_desktop_capability_handler()
        if handler is None:
            result["reason"] = "desktop_capability_unavailable"
            return result

        env = surface_env(mode)
        env.update(dict(launch_target.get("env") or {}))
        launch = handler.handle_execute(
            principal_id=principal_id,
            args={
                "pack_id": target_pack,
                "action": "launch",
                "env": env,
            },
            grant_config={
                "allowed_packs": [target_pack],
                "port": resolve_runtime_port(),
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
    return resolve_surface_mode(surfaces)


def _surface_env(mode: str) -> Dict[str, str]:
    return surface_env(mode)
