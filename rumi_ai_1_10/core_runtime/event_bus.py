"""
event_bus.py - publish/subscribe(疎結合通信)

スレッドセーフ版
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple
from threading import RLock


Handler = Callable[[Dict[str, Any]], None]


@dataclass
class EventBus:
    """
    シンプルなEvent Bus（スレッドセーフ）
    """

    _subs: Dict[str, List[Tuple[str, Handler]]] = field(default_factory=dict)
    _lock: RLock = field(default_factory=RLock)
    _id_counter: int = field(default=0)

    def subscribe(self, topic: str, handler: Handler, handler_id: Optional[str] = None) -> str:
        """Subscribe handler to topic（スレッドセーフ、カウンタベースID）"""
        with self._lock:
            if handler_id is None:
                self._id_counter += 1
                handler_id = f"h{self._id_counter}"
            self._subs.setdefault(topic, []).append((handler_id, handler))
            return handler_id

    def publish(self, topic: str, payload: Dict[str, Any]) -> None:
        """Publish event to topic（スレッドセーフ）"""
        with self._lock:
            handlers = list(self._subs.get(topic, []))
        
        for handler_id, handler in handlers:
            try:
                handler(payload)
            except Exception as e:
                # エラーを可視化するが、publishは継続
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
