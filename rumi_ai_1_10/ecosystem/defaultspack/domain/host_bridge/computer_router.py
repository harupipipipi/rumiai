from __future__ import annotations

import os
import platform
from pathlib import Path
from typing import Any

from .viewer_broker_client import ViewerBrokerClient


def should_route_to_viewer(action: str) -> bool:
    if os.environ.get("RUMI_COMPUTER_HOST_INTERNAL") == "1":
        return False
    if platform.system() != "Darwin":
        return False
    return str(action or "").startswith("computer.")


def run_computer_action(
    action: str,
    payload: dict[str, Any] | None = None,
    context: dict[str, Any] | None = None,
    *,
    artifact_root: Path | None = None,
    yolo_mode: bool = False,
) -> dict[str, Any]:
    from ecosystem.rumi_default_tools_pack.domain.tool.browser_computer import BrowserComputerController

    payload = dict(payload or {})
    if should_route_to_viewer(action):
        client = ViewerBrokerClient.from_environment()
        if client.available():
            try:
                return client.run_computer(action, payload, context=context, artifact_root=artifact_root)
            except Exception as exc:
                return {
                    "action": action,
                    "is_error": True,
                    "reason": f"Rumi Viewer host broker is unavailable: {exc}",
                    "recovery": {
                        "kind": "open_rumi_viewer",
                        "note": "Open Rumi Viewer and grant macOS permissions there.",
                    },
                    "permission_subject": "Rumi Viewer",
                }
        return {
            "action": action,
            "is_error": True,
            "reason": "Rumi Viewer is required for computer control on macOS.",
            "recovery": {
                "kind": "open_rumi_viewer",
                "note": "Open Rumi Viewer and grant macOS permissions there.",
            },
            "permission_subject": "Rumi Viewer",
        }
    return BrowserComputerController(artifact_root=artifact_root).run(
        action,
        payload,
        yolo_mode=yolo_mode,
    )
