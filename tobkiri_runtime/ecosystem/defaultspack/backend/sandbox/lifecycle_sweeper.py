from __future__ import annotations

import threading
from typing import Callable


class LifecycleSweeper:
    def __init__(
        self,
        sweep: Callable[[], object],
        *,
        interval_seconds: float = 30.0,
    ) -> None:
        self._sweep = sweep
        self._interval_seconds = max(0.05, float(interval_seconds))
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.RLock()

    def start(self) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop.clear()
            self._thread = threading.Thread(
                target=self._run,
                name="rumi-sandbox-lifecycle-sweeper",
                daemon=True,
            )
            self._thread.start()

    def stop(self, *, timeout: float = 2.0) -> None:
        with self._lock:
            thread = self._thread
            self._stop.set()
        if thread is not None:
            thread.join(timeout=timeout)

    def run_once(self) -> object:
        return self._sweep()

    def _run(self) -> None:
        while not self._stop.wait(self._interval_seconds):
            try:
                self._sweep()
            except Exception:
                # Lifecycle cleanup is best-effort; ordinary API calls still
                # enforce the same policies synchronously.
                continue
