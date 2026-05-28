"""
event_bus.py - publish/subscribe(疎結合通信)

スレッドセーフ版
ワイルドカード対応:
  - `*` は1セグメントに一致 (例: `agent.*` → `agent.created`)
  - `#` は1以上のセグメントに一致 (例: `agent.#` → `agent.created`, `agent.x.y`)
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple
from threading import RLock


Handler = Callable[[Dict[str, Any]], None]


def _topic_matches(pattern: str, topic: str) -> bool:
    """Return True if *pattern* (may contain ``*``/``#``) matches *topic*.

    Matching rules (AMQP-style):
    - ``*`` matches exactly one segment  (``agent.*`` → ``agent.created``)
    - ``#`` matches zero or more segments (``#.status`` → ``status``, ``agent.status``)
    """
    parts = pattern.split(".")
    regex_parts: list[str] = []
    for p in parts:
        if p == "#":
            regex_parts.append(r"(?:[^.]+\.)*[^.]+")
        elif p == "*":
            regex_parts.append(r"[^.]+")
        else:
            regex_parts.append(re.escape(p))
    regex = r"^" + r"\.".join(regex_parts) + r"$"
    return bool(re.match(regex, topic))


@dataclass
class EventBus:
    """
    シンプルなEvent Bus（スレッドセーフ）
    ワイルドカード購読対応 (`*`, `#`)
    """

    _subs: Dict[str, List[Tuple[str, Handler]]] = field(default_factory=dict)
    _lock: RLock = field(default_factory=RLock)
    _id_counter: int = field(default=0)

    def subscribe(self, topic: str, handler: Handler, handler_id: Optional[str] = None) -> str:
        """Subscribe handler to topic（スレッドセーフ、カウンタベースID）

        *topic* may contain wildcards:
        - ``*`` matches exactly one segment  (e.g. ``agent.*``)
        - ``#`` matches zero or more segments (e.g. ``#.status``)
        """
        with self._lock:
            if handler_id is None:
                self._id_counter += 1
                handler_id = f"h{self._id_counter}"
            self._subs.setdefault(topic, []).append((handler_id, handler))
            return handler_id

    def _matching_handlers(self, topic: str) -> List[Tuple[str, Handler]]:
        """Return all handlers whose subscription pattern matches *topic*."""
        matched: List[Tuple[str, Handler]] = []
        for pattern, handlers in self._subs.items():
            if _topic_matches(pattern, topic):
                matched.extend(handlers)
        return matched

    def publish(self, topic: str, payload: Dict[str, Any]) -> None:
        """Publish event to topic（スレッドセーフ、ワイルドカード購読にも配信）"""
        with self._lock:
            seen_ids: set[str] = set()
            handlers: List[Tuple[str, Handler]] = []
            for hid, h in self._matching_handlers(topic):
                if hid not in seen_ids:
                    seen_ids.add(hid)
                    handlers.append((hid, h))

        for handler_id, handler in handlers:
            try:
                handler(payload)
            except Exception as e:
                print(f"[EventBus] Handler '{handler_id}' error on topic '{topic}': {e}", file=sys.stderr)
                continue

    def unsubscribe(self, topic: str, handler_id: str) -> bool:
        """Remove a handler by id（スレッドセーフ）"""
        with self._lock:
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
        """Return topic -> [handler_id...]（スレッドセーフ）"""
        with self._lock:
            return {topic: [hid for hid, _ in handlers] for topic, handlers in self._subs.items()}

    def clear(self, topic: Optional[str] = None) -> int:
        """購読を解除"""
        with self._lock:
            if topic is None:
                count = sum(len(handlers) for handlers in self._subs.values())
                self._subs.clear()
                return count

            if topic in self._subs:
                count = len(self._subs[topic])
                del self._subs[topic]
                return count

            return 0
