from __future__ import annotations

import uuid
from typing import Any

from .context import AdaptiveError, coerce_int, now_iso, now_seconds, redact


class EventServiceMixin:
    def events_append(self, args: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        del ctx
        event_type = str(args.get("event_type") or args.get("type") or "").strip()
        if not event_type:
            raise AdaptiveError("INVALID_INPUT", "event_type is required")
        idempotency_key = str(args.get("idempotency_key") or "").strip()
        if idempotency_key:
            event = self._event_record(
                event_type,
                args.get("payload") if isinstance(args.get("payload"), dict) else {},
                continuation=args.get("continuation") if isinstance(args.get("continuation"), dict) else None,
                idempotency_key=idempotency_key,
            )
            stored, duplicate = self.store.append_jsonl_once(
                "events/events.jsonl",
                event,
                key="idempotency_key",
                value=idempotency_key,
            )
            return {"profile_id": self.profile_id, "event": stored, "duplicate": duplicate}
        event = self._append_event(
            event_type,
            args.get("payload") if isinstance(args.get("payload"), dict) else {},
            continuation=args.get("continuation") if isinstance(args.get("continuation"), dict) else None,
            idempotency_key=None,
        )
        return {"profile_id": self.profile_id, "event": event}

    def events_list(self, args: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        del ctx
        limit = coerce_int(args.get("limit"), 50, minimum=1, maximum=500)
        event_type = str(args.get("event_type") or args.get("type") or "").strip()
        events = self.store.read_jsonl("events/events.jsonl", limit=limit if not event_type else None)
        if event_type:
            events = [event for event in events if event.get("event_type") == event_type][-limit:]
        events = self._overlay_events(events)
        return {"profile_id": self.profile_id, "events": events}

    def events_replay(self, args: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        del ctx
        limit = coerce_int(args.get("limit"), 100, minimum=1, maximum=500)
        after_event_id = str(args.get("after_event_id") or args.get("cursor") or "").strip()
        events = self.store.read_jsonl("events/events.jsonl")
        if after_event_id:
            for index, event in enumerate(events):
                if event.get("event_id") == after_event_id:
                    events = events[index + 1 :]
                    break
        events = events[:limit]
        events = self._overlay_events(events)
        return {
            "profile_id": self.profile_id,
            "events": events,
            "replayed": len(events),
            "cursor": events[-1]["event_id"] if events else after_event_id or None,
            "next_cursor": events[-1]["event_id"] if events else after_event_id or None,
            "continuations": [
                event.get("continuation")
                for event in events
                if isinstance(event.get("continuation"), dict)
            ],
        }

    def events_ack(self, args: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        del ctx
        event_id = self._event_id_from(args)
        event = self._find_event(event_id)
        subscriber_id = str(args.get("subscriber_id") or args.get("consumer_id") or args.get("subscriber") or "").strip()
        if subscriber_id:
            self._require_matching_subscription(subscriber_id, str(event.get("event_type") or ""))
        acknowledged_at = now_iso()

        def update(state: Any) -> dict[str, Any]:
            deliveries = self._deliveries_from_state(state)
            current = dict(deliveries.get(event_id) or {})
            current.update(
                {
                    "ack_state": "acked",
                    "delivery_status": "delivered",
                    "acked_at": acknowledged_at,
                    "updated_at": acknowledged_at,
                }
            )
            if subscriber_id:
                current["acknowledged_by"] = subscriber_id
            deliveries[event_id] = current
            return {"version": 1, "deliveries": deliveries}

        self.store.update_json("events/state.json", {"version": 1, "deliveries": {}}, update)
        self._append_event("adaptive.events.ack", {"event_id": event_id, "subscriber_id": subscriber_id})
        return {"profile_id": self.profile_id, "acked": True, "event": self._overlay_event(event)}

    def events_retry(self, args: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        del ctx
        event_id = str(args.get("event_id") or args.get("id") or "").strip()
        outbox_id = str(args.get("outbox_id") or "").strip()
        if not event_id and outbox_id:
            matched = self._event_for_outbox(outbox_id)
            event_id = str(matched.get("event_id") or "") if matched else ""
        if not event_id and not outbox_id:
            raise AdaptiveError("INVALID_INPUT", "event_id or outbox_id is required")

        event = self._find_event(event_id) if event_id else None
        delay = coerce_int(args.get("delay_seconds"), 0, minimum=0, maximum=86400)
        retried_at = now_iso()
        next_attempt_at = now_seconds() + delay if delay else None
        delivery_state: dict[str, Any] = {}

        if event_id:
            def update_event(state: Any) -> dict[str, Any]:
                nonlocal delivery_state
                deliveries = self._deliveries_from_state(state)
                current = dict(deliveries.get(event_id) or {})
                retry_count = int(current.get("retry_count") or 0) + 1
                current.update(
                    {
                        "ack_state": "pending",
                        "delivery_status": "retry_pending",
                        "retry_count": retry_count,
                        "last_retry_at": retried_at,
                        "updated_at": retried_at,
                    }
                )
                if next_attempt_at is not None:
                    current["next_attempt_at"] = next_attempt_at
                current.pop("dlq_reason", None)
                deliveries[event_id] = current
                delivery_state = current
                return {"version": 1, "deliveries": deliveries}

            self.store.update_json("events/state.json", {"version": 1, "deliveries": {}}, update_event)

        outbox_item = self._retry_outbox(outbox_id) if outbox_id else None
        self._append_event(
            "adaptive.events.retry",
            {"event_id": event_id or None, "outbox_id": outbox_id or None, "delay_seconds": delay},
        )
        return {
            "profile_id": self.profile_id,
            "retry_scheduled": True,
            "event": self._overlay_event(event) if event else None,
            "delivery": delivery_state,
            "outbox_item": outbox_item,
        }

    def events_dlq(self, args: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        del ctx
        event_id = self._event_id_from(args)
        event = self._find_event(event_id)
        outbox_id = str(args.get("outbox_id") or "").strip()
        reason = str(args.get("reason") or args.get("dlq_reason") or "delivery failed").strip() or "delivery failed"
        dead_lettered_at = now_iso()

        def update_event(state: Any) -> dict[str, Any]:
            deliveries = self._deliveries_from_state(state)
            current = dict(deliveries.get(event_id) or {})
            current.update(
                {
                    "ack_state": "failed",
                    "delivery_status": "dead_letter",
                    "dlq_reason": reason,
                    "dead_lettered_at": dead_lettered_at,
                    "updated_at": dead_lettered_at,
                }
            )
            deliveries[event_id] = current
            return {"version": 1, "deliveries": deliveries}

        self.store.update_json("events/state.json", {"version": 1, "deliveries": {}}, update_event)

        dlq_entry = {
            "dlq_id": str(uuid.uuid4()),
            "profile_id": self.profile_id,
            "event_id": event_id,
            "event": self._overlay_event(event),
            "reason": reason,
            "created_at": dead_lettered_at,
        }

        def update_dlq(state: Any) -> dict[str, Any]:
            entries = state.get("entries") if isinstance(state, dict) and isinstance(state.get("entries"), list) else []
            if not any(item.get("event_id") == event_id for item in entries):
                entries.append(dlq_entry)
            return {"version": 1, "entries": entries[-1000:]}

        self.store.update_json("events/dlq.json", {"version": 1, "entries": []}, update_dlq)
        outbox_item = self._dead_letter_outbox(outbox_id, reason) if outbox_id else None
        self._append_event("adaptive.events.dlq", {"event_id": event_id, "outbox_id": outbox_id or None, "reason": reason})
        return {
            "profile_id": self.profile_id,
            "dead_lettered": True,
            "event": self._overlay_event(event),
            "dlq_entry": dlq_entry,
            "outbox_item": outbox_item,
        }

    def events_subscribe(self, args: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        del ctx
        subscriber_id = str(args.get("subscriber_id") or args.get("consumer_id") or args.get("subscriber") or "").strip()
        if not subscriber_id:
            raise AdaptiveError("INVALID_INPUT", "subscriber_id is required")
        event_type = str(args.get("event_type") or args.get("type") or "*").strip() or "*"
        subscription_id = str(args.get("subscription_id") or args.get("id") or "").strip()
        cursor = str(args.get("cursor") or args.get("after_event_id") or "").strip() or None
        ack_required = bool(args.get("ack_required", True))
        now = now_iso()
        response: dict[str, Any] = {}

        def update(state: Any) -> dict[str, Any]:
            nonlocal response
            subscriptions = (
                state.get("subscriptions")
                if isinstance(state, dict) and isinstance(state.get("subscriptions"), list)
                else []
            )
            subscription = next(
                (
                    item
                    for item in subscriptions
                    if (subscription_id and item.get("subscription_id") == subscription_id)
                    or (
                        item.get("subscriber_id") == subscriber_id
                        and item.get("event_type") == event_type
                    )
                ),
                None,
            )
            if subscription is None:
                subscription = {
                    "subscription_id": subscription_id or str(uuid.uuid4()),
                    "profile_id": self.profile_id,
                    "subscriber_id": subscriber_id,
                    "event_type": event_type,
                    "created_at": now,
                }
                subscriptions.append(subscription)
            subscription.update(
                {
                    "cursor": cursor,
                    "ack_required": ack_required,
                    "status": str(args.get("status") or subscription.get("status") or "active"),
                    "updated_at": now,
                }
            )
            response = dict(subscription)
            return {"version": 1, "subscriptions": subscriptions[-500:]}

        self.store.update_json("events/subscriptions.json", {"version": 1, "subscriptions": []}, update)
        self._append_event(
            "adaptive.events.subscribe",
            {"subscription_id": response.get("subscription_id"), "subscriber_id": subscriber_id, "event_type": event_type},
        )
        return {"profile_id": self.profile_id, "subscription": response}

    def events_subscription_list(self, args: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        del ctx
        subscriber_id = str(args.get("subscriber_id") or args.get("consumer_id") or "").strip()
        event_type = str(args.get("event_type") or args.get("type") or "").strip()
        subscriptions = self._event_subscriptions()
        if subscriber_id:
            subscriptions = [item for item in subscriptions if item.get("subscriber_id") == subscriber_id]
        if event_type:
            subscriptions = [item for item in subscriptions if item.get("event_type") == event_type]
        return {"profile_id": self.profile_id, "subscriptions": subscriptions}

    def events_outbox(self, args: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        del ctx
        limit = coerce_int(args.get("limit"), 100, minimum=1, maximum=500)
        status = str(args.get("status") or "").strip()
        items = self._outbox_items(limit=limit, status=status or None)
        return {"profile_id": self.profile_id, "outbox": items}

    def continuation_resume(self, args: dict[str, Any], ctx: dict[str, Any]) -> dict[str, Any]:
        del ctx
        self._ensure_not_frozen("continuation.resume")
        continuation = args.get("continuation") if isinstance(args.get("continuation"), dict) else {}
        event_id = str(args.get("event_id") or args.get("id") or "").strip()
        if not event_id:
            raise AdaptiveError("INVALID_INPUT", "event_id is required for continuation resume")
        event = self._find_event(event_id)
        event_continuation = event.get("continuation") if isinstance(event.get("continuation"), dict) else {}
        if not event_continuation:
            raise AdaptiveError("INVALID_INPUT", "event does not contain a resumable continuation")
        if continuation and continuation != event_continuation:
            raise AdaptiveError("INVALID_INPUT", "continuation payload does not match event")
        continuation = event_continuation
        outbox_id = str(continuation.get("outbox_id") or "").strip()
        requested_outbox_id = str(args.get("outbox_id") or "").strip()
        if requested_outbox_id and requested_outbox_id != outbox_id:
            raise AdaptiveError("INVALID_INPUT", "outbox_id does not match event continuation")
        resume_key = str(
            args.get("idempotency_key")
            or args.get("resume_key")
            or continuation.get("resume_key")
            or event_id
            or ""
        ).strip()

        result = {
            "resumed": True,
            "resume_mode": "state_only",
            "event_id": event_id,
            "outbox_id": outbox_id or None,
            "continuation": redact(continuation),
        }
        response: dict[str, Any] = {}

        def update(state: Any) -> dict[str, Any]:
            nonlocal response
            resumes = state.get("resumes") if isinstance(state, dict) and isinstance(state.get("resumes"), list) else []
            existing = next((item for item in resumes if item.get("resume_key") == resume_key), None)
            if existing is not None:
                response = {"entry": dict(existing), "duplicate": True}
                return {"version": 1, "resumes": resumes[-1000:]}
            entry = {
                "resume_id": str(uuid.uuid4()),
                "profile_id": self.profile_id,
                "resume_key": resume_key,
                "status": "completed",
                "result": result,
                "created_at": now_iso(),
                "updated_at": now_iso(),
            }
            resumes.append(entry)
            response = {"entry": entry, "duplicate": False}
            return {"version": 1, "resumes": resumes[-1000:]}

        self.store.update_json("events/continuations.json", {"version": 1, "resumes": []}, update)
        duplicate = bool(response.get("duplicate"))
        outbox_item = None
        if not duplicate:
            if outbox_id:
                outbox_item = self._complete_outbox(outbox_id)
            self._mark_event_resumed(event_id)
            self._append_event("adaptive.continuation.resume", {"resume_key": resume_key, "event_id": event_id, "outbox_id": outbox_id or None})
        elif outbox_id:
            outbox_item = self._outbox_item(outbox_id)
        return {
            "profile_id": self.profile_id,
            "resumed": True,
            "resume_mode": "state_only",
            "duplicate": duplicate,
            "resume": response.get("entry"),
            "outbox_item": outbox_item,
        }

    def _append_outbox(self, kind: str, payload: dict[str, Any]) -> dict[str, Any]:
        item = {
            "outbox_id": str(uuid.uuid4()),
            "profile_id": self.profile_id,
            "kind": kind,
            "payload": redact(payload),
            "status": "pending",
            "attempts": 0,
            "created_at": now_iso(),
            "updated_at": now_iso(),
        }

        def update(state: Any) -> dict[str, Any]:
            items = state.get("items") if isinstance(state, dict) and isinstance(state.get("items"), list) else []
            items.append(item)
            return {"version": 1, "items": items[-1000:]}

        self.store.update_json("events/outbox.json", {"version": 1, "items": []}, update)
        return item

    def _outbox_items(self, *, limit: int = 100, status: str | None = None) -> list[dict[str, Any]]:
        state = self.store.read_json("events/outbox.json", {"version": 1, "items": []})
        items = state.get("items") if isinstance(state, dict) else []
        if not isinstance(items, list):
            return []
        if status:
            items = [item for item in items if isinstance(item, dict) and item.get("status") == status]
        return [item for item in items if isinstance(item, dict)][-limit:]

    def _outbox_item(self, outbox_id: str) -> dict[str, Any] | None:
        for item in self._outbox_items(limit=1000):
            if item.get("outbox_id") == outbox_id:
                return item
        return None

    def _update_outbox_item(self, outbox_id: str, updates: dict[str, Any]) -> dict[str, Any]:
        if not outbox_id:
            raise AdaptiveError("INVALID_INPUT", "outbox_id is required")
        result: dict[str, Any] = {}

        def update(state: Any) -> dict[str, Any]:
            nonlocal result
            items = state.get("items") if isinstance(state, dict) and isinstance(state.get("items"), list) else []
            for item in items:
                if item.get("outbox_id") != outbox_id:
                    continue
                item.update(redact(updates))
                item["updated_at"] = now_iso()
                result = dict(item)
                return {"version": 1, "items": items[-1000:]}
            raise AdaptiveError("NOT_FOUND", "outbox item not found")

        self.store.update_json("events/outbox.json", {"version": 1, "items": []}, update)
        return result

    def _retry_outbox(self, outbox_id: str) -> dict[str, Any]:
        existing = self._outbox_item(outbox_id)
        attempts = int((existing or {}).get("attempts") or 0) + 1
        return self._update_outbox_item(
            outbox_id,
            {
                "status": "pending",
                "attempts": attempts,
                "last_error": None,
                "dead_letter_reason": None,
            },
        )

    def _dead_letter_outbox(self, outbox_id: str, reason: str) -> dict[str, Any]:
        return self._update_outbox_item(
            outbox_id,
            {
                "status": "dead_letter",
                "dead_letter_reason": reason,
                "last_error": reason,
            },
        )

    def _complete_outbox(self, outbox_id: str) -> dict[str, Any]:
        return self._update_outbox_item(
            outbox_id,
            {
                "status": "completed",
                "completed_at": now_iso(),
            },
        )

    def _deliveries_from_state(self, state: Any) -> dict[str, dict[str, Any]]:
        raw = state.get("deliveries") if isinstance(state, dict) and isinstance(state.get("deliveries"), dict) else {}
        return {str(key): dict(value) for key, value in raw.items() if isinstance(value, dict)}

    def _delivery_state(self) -> dict[str, dict[str, Any]]:
        state = self.store.read_json("events/state.json", {"version": 1, "deliveries": {}})
        return self._deliveries_from_state(state)

    def _overlay_events(self, events: list[dict[str, Any]]) -> list[dict[str, Any]]:
        deliveries = self._delivery_state()
        return [self._overlay_event(event, deliveries=deliveries) for event in events]

    def _overlay_event(
        self,
        event: dict[str, Any] | None,
        *,
        deliveries: dict[str, dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        if not isinstance(event, dict):
            return {}
        result = dict(event)
        delivery = (deliveries or self._delivery_state()).get(str(result.get("event_id") or ""))
        if delivery:
            result.update(delivery)
        return result

    def _event_id_from(self, args: dict[str, Any]) -> str:
        event_id = str(args.get("event_id") or args.get("id") or "").strip()
        if not event_id:
            raise AdaptiveError("INVALID_INPUT", "event_id is required")
        return event_id

    def _find_event(self, event_id: str) -> dict[str, Any]:
        if not event_id:
            raise AdaptiveError("INVALID_INPUT", "event_id is required")
        for event in reversed(self.store.read_jsonl("events/events.jsonl")):
            if event.get("event_id") == event_id or event.get("id") == event_id:
                return event
        raise AdaptiveError("NOT_FOUND", "event not found")

    def _event_for_outbox(self, outbox_id: str) -> dict[str, Any] | None:
        if not outbox_id:
            return None
        for event in reversed(self.store.read_jsonl("events/events.jsonl")):
            continuation = event.get("continuation")
            if isinstance(continuation, dict) and continuation.get("outbox_id") == outbox_id:
                return event
        return None

    def _mark_event_resumed(self, event_id: str) -> None:
        resumed_at = now_iso()

        def update(state: Any) -> dict[str, Any]:
            deliveries = self._deliveries_from_state(state)
            current = dict(deliveries.get(event_id) or {})
            current.update(
                {
                    "ack_state": "acked",
                    "delivery_status": "resumed",
                    "resumed_at": resumed_at,
                    "updated_at": resumed_at,
                }
            )
            deliveries[event_id] = current
            return {"version": 1, "deliveries": deliveries}

        self.store.update_json("events/state.json", {"version": 1, "deliveries": {}}, update)

    def _event_subscriptions(self) -> list[dict[str, Any]]:
        state = self.store.read_json("events/subscriptions.json", {"version": 1, "subscriptions": []})
        subscriptions = state.get("subscriptions") if isinstance(state, dict) else []
        return [item for item in subscriptions if isinstance(item, dict)] if isinstance(subscriptions, list) else []

    def _require_matching_subscription(self, subscriber_id: str, event_type: str) -> None:
        for subscription in self._event_subscriptions():
            if subscription.get("status") != "active":
                continue
            if str(subscription.get("subscriber_id") or "") != subscriber_id:
                continue
            configured_type = str(subscription.get("event_type") or "*").strip() or "*"
            if configured_type in {"*", event_type}:
                return
        raise AdaptiveError("SUBSCRIPTION_REQUIRED", "active matching subscription is required to acknowledge event")

    def _event_delivery_summary(self, events: list[dict[str, Any]]) -> dict[str, int]:
        summary = {"pending": 0, "acked": 0, "retry_pending": 0, "dead_letter": 0, "resumed": 0}
        for event in events:
            ack_state = str(event.get("ack_state") or "pending")
            delivery_status = str(event.get("delivery_status") or "recorded")
            if delivery_status == "resumed":
                summary["resumed"] += 1
            elif ack_state == "acked":
                summary["acked"] += 1
            elif delivery_status == "retry_pending":
                summary["retry_pending"] += 1
            elif delivery_status == "dead_letter":
                summary["dead_letter"] += 1
            else:
                summary["pending"] += 1
        return summary

    def _event_by_id(self, event_id: str) -> dict[str, Any] | None:
        for event in reversed(self.store.read_jsonl("events/events.jsonl")):
            if event.get("event_id") == event_id or event.get("id") == event_id:
                return event
        return None


def event_payload(event: dict[str, Any]) -> dict[str, Any]:
    payload = event.get("payload")
    return payload if isinstance(payload, dict) else {}


def event_payload_bool(event: dict[str, Any], key: str) -> bool:
    return event_payload(event).get(key) is True


def event_status(event: dict[str, Any]) -> str:
    payload = event_payload(event)
    return str(payload.get("status") or event.get("status") or event.get("event_type") or "").strip().lower()


def event_indicates_failure(event: dict[str, Any]) -> bool:
    status = event_status(event)
    return any(token in status for token in ("fail", "error", "exception", "regression"))


def event_indicates_verified_success(event: dict[str, Any]) -> bool:
    payload = event_payload(event)
    status = event_status(event)
    success_status = any(token in status for token in ("success", "succeed", "passed", "verified"))
    return bool(payload.get("verified") is True and success_status)
