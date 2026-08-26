from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class ComputerHost(Protocol):
    """Model-agnostic host boundary for computer execution.

    Model-facing tools own schemas, normalized actions, approval policy, and
    recovery behavior. Host implementations own only the native transport used
    to observe or mutate the selected computer surface.
    """

    host_id: str
    permission_subject: str

    def available(self) -> bool:
        """Return whether this host can currently accept requests."""
        ...

    def run(
        self,
        action: str,
        payload: dict[str, Any],
        *,
        context: dict[str, Any] | None = None,
        artifact_root: Path | None = None,
        yolo_mode: bool = False,
    ) -> dict[str, Any]:
        """Execute one normalized computer action through this host."""
        ...


class LocalControllerComputerHost:
    """Compatibility host for the existing in-process computer controller.

    This adapter keeps current Windows/Linux/internal-host behavior intact while
    giving tools a stable host seam that can later be backed by native platform
    services without changing the public tool contract.
    """

    host_id = "local_controller"
    permission_subject = "Local computer host"

    def __init__(self, controller_cls: type[Any]) -> None:
        self._controller_cls = controller_cls

    def available(self) -> bool:
        return True

    def run(
        self,
        action: str,
        payload: dict[str, Any],
        *,
        context: dict[str, Any] | None = None,
        artifact_root: Path | None = None,
        yolo_mode: bool = False,
    ) -> dict[str, Any]:
        del context
        controller = self._controller_cls(artifact_root=artifact_root)
        result = controller.run(action, payload, yolo_mode=yolo_mode)
        return _normalize_result(action, result)


class ViewerBrokerComputerHost:
    """Native host backed by the Rumi Viewer host broker."""

    host_id = "viewer_native"
    permission_subject = "Rumi Viewer"

    def __init__(self, client: Any) -> None:
        self._client = client

    def available(self) -> bool:
        try:
            return bool(self._client.available())
        except Exception:
            return False

    def run(
        self,
        action: str,
        payload: dict[str, Any],
        *,
        context: dict[str, Any] | None = None,
        artifact_root: Path | None = None,
        yolo_mode: bool = False,
    ) -> dict[str, Any]:
        del yolo_mode
        if not self.available():
            return {
                "action": action,
                "is_error": True,
                "reason": "Rumi Viewer is required for computer control on macOS.",
                "recovery": {
                    "kind": "open_rumi_viewer",
                    "note": "Open Rumi Viewer and grant macOS permissions there.",
                },
                "permission_subject": self.permission_subject,
            }
        try:
            result = self._client.run_computer(
                action,
                payload,
                context=context,
                artifact_root=artifact_root,
            )
        except Exception as exc:
            return {
                "action": action,
                "is_error": True,
                "reason": f"Rumi Viewer host broker is unavailable: {exc}",
                "recovery": {
                    "kind": "open_rumi_viewer",
                    "note": "Open Rumi Viewer and grant macOS permissions there.",
                },
                "permission_subject": self.permission_subject,
            }
        return _normalize_result(action, result)


def _normalize_result(action: str, result: Any) -> dict[str, Any]:
    if isinstance(result, dict):
        return dict(result)
    return {"action": action, "result": result}
