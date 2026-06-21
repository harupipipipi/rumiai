from __future__ import annotations

import time
from dataclasses import dataclass
import threading
from typing import Callable

from .errors import FRAME_NOT_FOUND, SandboxContractError
from .policy import require_canonical_id


@dataclass(frozen=True)
class DesktopFrame:
    seat_id: str
    frame_seq: int
    data: bytes
    content_type: str
    width: int
    height: int
    captured_at: float
    source: str = "snapshot"

    @property
    def size_bytes(self) -> int:
        return len(self.data)

    def metadata(self) -> dict[str, object]:
        return {
            "seat_id": self.seat_id,
            "frame_seq": self.frame_seq,
            "content_type": self.content_type,
            "width": self.width,
            "height": self.height,
            "captured_at": self.captured_at,
            "size_bytes": self.size_bytes,
            "source": self.source,
        }


@dataclass(frozen=True)
class FrameFetchResult:
    status_code: int
    frame_seq: int
    frame: DesktopFrame | None = None

    @property
    def not_modified(self) -> bool:
        return self.status_code == 204


@dataclass(frozen=True)
class CaptureReservation:
    seat_id: str
    reserved_at: float


class FrameCache:
    def __init__(
        self,
        *,
        min_capture_interval_seconds: float = 0.25,
        max_frame_bytes: int = 10 * 1024 * 1024,
        time_fn: Callable[[], float] | None = None,
    ) -> None:
        self.min_capture_interval_seconds = float(min_capture_interval_seconds)
        self.max_frame_bytes = int(max_frame_bytes)
        self._time_fn = time_fn or time.time
        self._frames: dict[str, DesktopFrame] = {}
        self._last_capture_at: dict[str, float] = {}
        self._captures_in_flight: set[str] = set()
        self._lock = threading.RLock()

    def reserve_capture(self, seat_id: str) -> CaptureReservation | None:
        seat_id = require_canonical_id(seat_id, field="seat_id")
        with self._lock:
            if seat_id in self._captures_in_flight:
                return None
            now = self._time_fn()
            last = self._last_capture_at.get(seat_id)
            if last is not None and (now - last) < self.min_capture_interval_seconds:
                return None
            self._captures_in_flight.add(seat_id)
            self._last_capture_at[seat_id] = now
            return CaptureReservation(seat_id=seat_id, reserved_at=now)

    def release_capture(self, seat_id: str) -> None:
        with self._lock:
            self._captures_in_flight.discard(require_canonical_id(seat_id, field="seat_id"))

    def put_frame(
        self,
        seat_id: str,
        data: bytes,
        *,
        content_type: str = "image/png",
        width: int,
        height: int,
        captured_at: float | None = None,
        source: str = "snapshot",
    ) -> DesktopFrame:
        seat_id = require_canonical_id(seat_id, field="seat_id")
        if not isinstance(data, bytes) or not data:
            raise ValueError("frame data must be non-empty bytes")
        if len(data) > self.max_frame_bytes:
            raise ValueError("frame data exceeds cache limit")
        if width < 1 or height < 1:
            raise ValueError("frame dimensions must be positive")
        with self._lock:
            previous = self._frames.get(seat_id)
            frame = DesktopFrame(
                seat_id=seat_id,
                frame_seq=1 if previous is None else previous.frame_seq + 1,
                data=data,
                content_type=content_type,
                width=width,
                height=height,
                captured_at=self._time_fn() if captured_at is None else captured_at,
                source=source,
            )
            self._frames[seat_id] = frame
            self._last_capture_at[seat_id] = frame.captured_at
            self._captures_in_flight.discard(seat_id)
            return frame

    def get_frame(self, seat_id: str, *, after_seq: int | None = None) -> FrameFetchResult:
        seat_id = require_canonical_id(seat_id, field="seat_id")
        with self._lock:
            frame = self._frames.get(seat_id)
            if frame is None:
                raise SandboxContractError(FRAME_NOT_FOUND, "No desktop frame has been captured", status_code=404)
            if after_seq is not None and int(after_seq) >= frame.frame_seq:
                return FrameFetchResult(status_code=204, frame_seq=frame.frame_seq, frame=None)
            return FrameFetchResult(status_code=200, frame_seq=frame.frame_seq, frame=frame)

    def last_metadata(self, seat_id: str) -> dict[str, object] | None:
        with self._lock:
            frame = self._frames.get(require_canonical_id(seat_id, field="seat_id"))
            return None if frame is None else frame.metadata()

    def discard(self, seat_id: str) -> None:
        seat_id = require_canonical_id(seat_id, field="seat_id")
        with self._lock:
            self._frames.pop(seat_id, None)
            self._last_capture_at.pop(seat_id, None)
            self._captures_in_flight.discard(seat_id)
