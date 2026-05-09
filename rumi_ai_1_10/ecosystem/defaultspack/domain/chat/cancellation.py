from __future__ import annotations

import threading
from typing import Callable


class ChatCancellationRegistry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._cancelled: set[str] = set()
        self._callbacks: dict[str, list[Callable[[], None]]] = {}

    def register(self, conversation_id: str, callback: Callable[[], None] | None = None) -> None:
        conversation_id = str(conversation_id or "").strip()
        if not conversation_id:
            return
        with self._lock:
            self._cancelled.discard(conversation_id)
            if callback is not None:
                self._callbacks.setdefault(conversation_id, []).append(callback)

    def unregister(self, conversation_id: str, callback: Callable[[], None] | None = None) -> None:
        conversation_id = str(conversation_id or "").strip()
        if not conversation_id:
            return
        with self._lock:
            if callback is not None:
                callbacks = self._callbacks.get(conversation_id, [])
                self._callbacks[conversation_id] = [item for item in callbacks if item is not callback]
                if not self._callbacks[conversation_id]:
                    self._callbacks.pop(conversation_id, None)
            else:
                self._callbacks.pop(conversation_id, None)
            if conversation_id not in self._callbacks:
                self._cancelled.discard(conversation_id)

    def request_cancel(self, conversation_id: str) -> bool:
        conversation_id = str(conversation_id or "").strip()
        if not conversation_id:
            return False
        with self._lock:
            self._cancelled.add(conversation_id)
            callbacks = list(self._callbacks.get(conversation_id, []))
        for callback in callbacks:
            try:
                callback()
            except Exception:
                pass
        return True

    def is_cancelled(self, conversation_id: str) -> bool:
        conversation_id = str(conversation_id or "").strip()
        if not conversation_id:
            return False
        with self._lock:
            return conversation_id in self._cancelled


_REGISTRY = ChatCancellationRegistry()


def get_chat_cancellation_registry() -> ChatCancellationRegistry:
    return _REGISTRY
