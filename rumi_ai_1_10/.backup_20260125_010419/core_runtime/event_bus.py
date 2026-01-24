"""
event_bus.py - publish/subscribe(疎結合通信)

Step1では同期・インメモリの最小実装。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple


Handler = Callable[[Dict[str, Any]], None]


@dataclass
class EventBus:
    """
    シンプルなEvent Bus。

    Note:
    - 最初は同期で十分(非同期は後で差し替え可能)。
    - KernelやComponentが疎結合に通信する土台。
    """

    # topic -> [(handler_id, handler), ...]
    _subs: Dict[str, List[Tuple[str, Handler]]] = field(default_factory=dict)

    def subscribe(self, topic: str, handler: Handler, handler_id: Optional[str] = None) -> str:
        """
        Subscribe handler to topic.
        Returns: handler_id
        """
        if handler_id is None:
            handler_id = f"h{len(self._subs.get(topic, [])) + 1}"
        self._subs.setdefault(topic, []).append((handler_id, handler))
        return handler_id

    def publish(self, topic: str, payload: Dict[str, Any]) -> None:
        """
        Publish event to topic.
        fail-soft: individual handler exceptions must not crash the bus.
        """
        for _, handler in list(self._subs.get(topic, [])):
            try:
                handler(payload)
            except Exception:
                # fail-soft: swallow exceptions (diagnostics integration is handled elsewhere)
                continue

    def unsubscribe(self, topic: str, handler_id: str) -> bool:
        """Remove a handler by id. Returns True if removed."""
        items = self._subs.get(topic, [])
        if not items:
            return False
        kept: List[Tuple[str, Handler]] = []
        removed = False
        for hid, h in items:
            if hid == handler_id:
                removed = True
            else:
                kept.append((hid, h))
        if kept:
            self._subs[topic] = kept
        else:
            self._subs.pop(topic, None)
        return removed

    def list_subscribers(self) -> Dict[str, List[str]]:
        """Return topic -> [handler_id...]"""
        return {topic: [hid for hid, _ in handlers] for topic, handlers in self._subs.items()}
