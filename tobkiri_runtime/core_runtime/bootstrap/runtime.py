"""Canonical bootstrap for the packaged Tobkiri runtime.

This module deliberately does not reconstruct the retired registry-driven
runtime.  It owns only the Host HTTP surface required to expose a
Launcher-captured Pack v4 activation.
"""

from __future__ import annotations

import logging
import os
from threading import RLock
from typing import Any

from ..app_lifecycle_manager import (
    AppLifecycleManager,
    mark_panel_ready,
    mark_runtime_ready,
    reset_runtime_readiness,
)
from ..pack_api_server import PackAPIServer, initialize_pack_api_server
from ..pack_control_v4 import capture_pack_control_session
from tobkiri_host.runtime import install_dispatch_session
from .profile_capture import capture_default_profile


logger = logging.getLogger(__name__)


class Kernel:
    """Start and stop the canonical packaged Pack v4 Host surface.

    The public name is the Launcher bootstrap contract.  Unlike the retired
    Kernel implementation, this class performs no Pack discovery, legacy
    manifest projection, interface registration, or authority reconstruction.
    """

    API_INIT_STEP = "api_init"
    owns_host_http_surface = True

    def __init__(self) -> None:
        self._lock = RLock()
        self._server: PackAPIServer | None = None
        self._lifecycle = AppLifecycleManager()

    def run_startup_until(self, step_id: str) -> dict[str, Any]:
        """Start the authenticated Host HTTP surface through ``step_id``."""
        if step_id != self.API_INIT_STEP:
            raise ValueError(f"unsupported Pack v4 bootstrap step: {step_id}")
        with self._lock:
            if self._server is not None and self._server.is_running():
                return {"status": "already_running", "step_id": step_id}
            reset_runtime_readiness()
            from ..di_container import get_container

            capture_default_profile()
            install_dispatch_session(
                get_container(),
                capture_pack_control_session(),
            )
            port = int(os.environ.get("RUMI_PORT", "8765"))
            self._server = initialize_pack_api_server(
                host="127.0.0.1",
                port=port,
                kernel=None,
                app_lifecycle_manager=self._lifecycle,
            )
            mark_panel_ready()
            return {"status": "ok", "step_id": step_id, "port": port}

    def run_startup_remaining(self) -> dict[str, Any]:
        """Publish readiness after the v4 Host surface is live."""
        with self._lock:
            if self._server is None or not self._server.is_running():
                raise RuntimeError("Pack v4 Host surface is not running")
            mark_runtime_ready()
            return {"status": "ok", "runtime_ready": True}

    def run_startup(self) -> dict[str, Any]:
        """Run the complete packaged bootstrap for headless callers."""
        result = self.run_startup_until(self.API_INIT_STEP)
        result.update(self.run_startup_remaining())
        return result

    def shutdown(self) -> None:
        """Stop the Host HTTP surface if this bootstrap started it."""
        with self._lock:
            if self._server is not None:
                self._server.stop()
                self._server = None


__all__ = ["Kernel"]
