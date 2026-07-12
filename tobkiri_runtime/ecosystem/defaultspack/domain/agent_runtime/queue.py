from __future__ import annotations

import threading
from collections import defaultdict, deque
from typing import Deque


class AgentRunQueue:
    """In-process queue with per-session lanes.

    The durable state lives in AgentRunStore; this class only chooses the next
    run while the process is alive.
    """

    def __init__(self, max_concurrency: int = 4) -> None:
        self.max_concurrency = max_concurrency
        self._lanes: dict[str, Deque[str]] = defaultdict(deque)
        self._active_sessions: set[str] = set()
        self._lock = threading.RLock()

    def enqueue(self, session_key: str, run_id: str) -> None:
        with self._lock:
            self._lanes[session_key].append(run_id)

    def next(self) -> tuple[str, str] | None:
        with self._lock:
            if len(self._active_sessions) >= self.max_concurrency:
                return None
            for session_key, lane in list(self._lanes.items()):
                if not lane or session_key in self._active_sessions:
                    continue
                run_id = lane.popleft()
                self._active_sessions.add(session_key)
                return session_key, run_id
            return None

    def complete(self, session_key: str) -> None:
        with self._lock:
            self._active_sessions.discard(session_key)

    def cancel(self, run_id: str) -> bool:
        with self._lock:
            for lane in self._lanes.values():
                try:
                    lane.remove(run_id)
                    return True
                except ValueError:
                    continue
        return False
