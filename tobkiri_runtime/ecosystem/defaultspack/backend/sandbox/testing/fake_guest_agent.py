from __future__ import annotations

from typing import Any, Mapping

from ..control_lease import ControlLeaseManager
from ..frame_cache import FrameCache
from ..guest.protocol import DesktopInputRequest, GuestExecRequest


class FakeGuestAgent:
    def __init__(
        self,
        *,
        lease_manager: ControlLeaseManager | None = None,
        frame_cache: FrameCache | None = None,
        width: int = 1440,
        height: int = 900,
    ) -> None:
        self.lease_manager = lease_manager or ControlLeaseManager()
        self.frame_cache = frame_cache or FrameCache()
        self.width = width
        self.height = height
        self.exec_requests: list[GuestExecRequest] = []
        self.desktop_inputs: list[DesktopInputRequest] = []
        self.audit_events: list[dict[str, Any]] = []

    def exec(self, sandbox_id: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        request = GuestExecRequest.from_payload(payload)
        self.exec_requests.append(request)
        return {
            "ok": True,
            "sandbox_id": sandbox_id,
            "argv": list(request.argv),
            "cwd": request.cwd,
            "exit_code": 0,
            "stdout": "",
            "stderr": "",
        }

    def desktop_input(
        self,
        sandbox_id: str,
        seat_id: str,
        payload: Mapping[str, Any],
        *,
        actor: str = "human",
    ) -> dict[str, Any]:
        if actor == "ai":
            self.lease_manager.validate_ai_input(seat_id)
            request = DesktopInputRequest.from_payload(
                payload,
                width=self.width,
                height=self.height,
                require_lease=False,
            )
        else:
            request = DesktopInputRequest.from_payload(payload, width=self.width, height=self.height)
            self.lease_manager.validate_human_input(seat_id, request.lease_token)
        self.desktop_inputs.append(request)
        audit = request.audit_fields()
        audit.update({"sandbox_id": sandbox_id, "seat_id": seat_id, "actor": actor})
        self.audit_events.append(audit)
        return {"ok": True, "sandbox_id": sandbox_id, "seat_id": seat_id, "action": request.action}

    def put_frame(self, seat_id: str, data: bytes = b"fake-frame", *, width: int | None = None, height: int | None = None):
        return self.frame_cache.put_frame(
            seat_id,
            data,
            content_type="image/png",
            width=width or self.width,
            height=height or self.height,
            source="fake_guest_agent",
        )

    def get_frame(self, seat_id: str, *, after_seq: int | None = None):
        return self.frame_cache.get_frame(seat_id, after_seq=after_seq)
