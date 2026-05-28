"""Tests for EventBus wildcard topic matching."""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_RUMI_PKG = str(_ROOT / "rumi_ai_1_10")
if _RUMI_PKG not in sys.path:
    sys.path.insert(0, _RUMI_PKG)
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

import pytest
from rumi_ai_1_10.core_runtime.event_bus import EventBus, _topic_matches


# ---------------------------------------------------------------------------
# _topic_matches unit tests
# ---------------------------------------------------------------------------

class TestTopicMatches:
    """Low-level pattern matcher tests."""

    def test_exact_match(self):
        assert _topic_matches("agent.created", "agent.created") is True

    def test_exact_mismatch(self):
        assert _topic_matches("agent.created", "agent.destroyed") is False

    def test_star_one_segment(self):
        assert _topic_matches("agent.*", "agent.created") is True
        assert _topic_matches("agent.*", "agent.destroyed") is True

    def test_star_rejects_multi_segment(self):
        assert _topic_matches("agent.*", "agent.x.created") is False

    def test_star_no_segment(self):
        assert _topic_matches("agent.*", "agent") is False

    def test_hash_multi_segment(self):
        assert _topic_matches("agent.#", "agent.created") is True
        assert _topic_matches("agent.#", "agent.x.y.z") is True

    def test_hash_no_extra(self):
        """`#` matches zero or more segments, so `agent.#` also matches `agent`."""
        assert _topic_matches("agent.#", "agent") is True

    def test_hash_as_first_segment(self):
        assert _topic_matches("#.status", "agent.status") is True
        assert _topic_matches("#.status", "status") is True

    def test_combined_star_and_hash(self):
        assert _topic_matches("agent.*.event.#", "agent.worker.event.done") is True
        assert _topic_matches("agent.*.event.#", "agent.worker.event.x.y") is True
        assert _topic_matches("agent.*.event.#", "agent.worker.status") is False


# ---------------------------------------------------------------------------
# EventBus integration tests
# ---------------------------------------------------------------------------

class TestEventBusWildcard:
    """Integration tests for wildcard subscriptions on the EventBus."""

    def test_exact_subscribe_and_publish(self):
        bus = EventBus()
        received: list[dict] = []
        bus.subscribe("chat.msg", lambda p: received.append(p))
        bus.publish("chat.msg", {"text": "hello"})
        assert received == [{"text": "hello"}]

    def test_wildcard_star_subscription(self):
        bus = EventBus()
        received: list[dict] = []
        bus.subscribe("agent.*", lambda p: received.append(p))
        bus.publish("agent.created", {"id": 1})
        bus.publish("agent.destroyed", {"id": 2})
        bus.publish("status.ping", {"ts": 0})
        assert len(received) == 2
        assert received[0] == {"id": 1}
        assert received[1] == {"id": 2}

    def test_wildcard_hash_subscription(self):
        bus = EventBus()
        received: list[dict] = []
        bus.subscribe("agent.#", lambda p: received.append(p))
        bus.publish("agent.created", {"id": 1})
        bus.publish("agent.worker.event.done", {"id": 2})
        bus.publish("chat.msg", {"text": "no"})
        assert len(received) == 2

    def test_no_duplicate_delivery(self):
        """A handler subscribed via both exact and wildcard is invoked once per matching subscription."""
        bus = EventBus()
        count = 0

        def counter(_p: dict):
            nonlocal count
            count += 1

        bus.subscribe("agent.created", counter, handler_id="exact")
        bus.subscribe("agent.*", counter, handler_id="wildcard")
        bus.publish("agent.created", {})
        assert count == 2

    def test_unsubscribe_exact(self):
        bus = EventBus()
        received: list[dict] = []
        hid = bus.subscribe("agent.created", lambda p: received.append(p))
        bus.publish("agent.created", {"a": 1})
        assert len(received) == 1
        bus.unsubscribe("agent.created", hid)
        bus.publish("agent.created", {"a": 2})
        assert len(received) == 1  # no new delivery

    def test_clear_all(self):
        bus = EventBus()
        bus.subscribe("a", lambda _: None)
        bus.subscribe("b", lambda _: None)
        assert bus.clear() == 2
        assert bus.list_subscribers() == {}
