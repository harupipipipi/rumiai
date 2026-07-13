"""Deprecated conversation-steer facade over the global turn runtime."""

from __future__ import annotations

import uuid
import warnings
from typing import Any, Mapping

from core_runtime.di_container import get_container
from core_runtime.global_contract_dispatch import invoke_global_contract
from core_runtime.resolved_profile_scope import active_resolved_profile

TURN_RESOURCE = "rumi.resource.turn.v1"
TURN_ACTION = "rumi.action.turn.lifecycle.v1"
CONVERSATION_RESOURCE = "rumi.resource.conversation.v1"
_TERMINAL = {"completed", "failed", "cancelled"}


class ConversationSteerStore:
    """Finite compatibility facade with no persistent queue or second owner."""

    def __init__(self, *_: Any, **__: Any) -> None:
        warnings.warn(
            "ConversationSteerStore is a Wave 7 turn-runtime facade",
            DeprecationWarning,
            stacklevel=2,
        )

    def enqueue(self, payload: Mapping[str, Any]) -> dict[str, Any]:
        """Attach user guidance to an active or newly queued turn."""
        prompt = str(payload.get("prompt") or payload.get("message") or "").strip()
        if not prompt:
            raise ValueError("prompt is required")
        conversation_id = str(payload.get("conversation_id") or "").strip()
        turn = self._resolve_turn(
            conversation_id,
            str(payload.get("turn_id") or payload.get("execution_id") or ""),
        )
        value = {
            "prompt": prompt,
            "target_type": str(payload.get("target_type") or "conversation"),
            "target_id": str(payload.get("target_id") or conversation_id),
            "conversation_id": conversation_id,
            "visible": payload.get("visible", True) is not False,
            "auto_send": payload.get("auto_send", True) is not False,
            "metadata": dict(payload.get("metadata") or {}),
        }
        updated = _invoke(
            TURN_ACTION,
            "steer",
            {
                "turn_id": turn["id"],
                "expected_revision": turn["revision"],
                "guidance": value,
            },
        )
        item = dict(updated["guidance"][-1])
        return _legacy_item(updated, item)

    def list(
        self, *, status: str | None = None, target_id: str | None = None
    ) -> list[dict[str, Any]]:
        """List bounded guidance projections from the turn runtime."""
        response = _invoke(
            TURN_RESOURCE,
            "list",
            {"conversation_id": target_id} if target_id else {},
        )
        result = []
        for turn in response.get("turns") or []:
            for item in turn.get("guidance") or []:
                projected = _legacy_item(turn, item)
                if status and projected.get("status") != status:
                    continue
                if target_id and target_id not in {
                    projected.get("target_id"),
                    projected.get("conversation_id"),
                    projected.get("turn_id"),
                }:
                    continue
                result.append(projected)
        return result

    def cancel(self, item_id: str) -> dict[str, Any] | None:
        """Cancel one queued guidance item at its current turn revision."""
        found = self._find(item_id)
        if found is None:
            return None
        turn, _ = found
        result = _invoke(
            TURN_ACTION,
            "cancel_guidance",
            {
                "turn_id": turn["id"],
                "guidance_id": item_id,
                "expected_revision": turn["revision"],
            },
        )
        return _legacy_item(result["turn"], result["item"])

    def mark(
        self, item_id: str, updates: Mapping[str, Any]
    ) -> dict[str, Any] | None:
        """Retain only the finite cancel compatibility mutation."""
        if updates.get("status") == "cancelled":
            return self.cancel(item_id)
        found = self._find(item_id)
        return _legacy_item(*found) if found is not None else None

    def process_for_agent_run(
        self,
        execution_id: str,
        *,
        conversation_id: str = "",
        context: Mapping[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Consume guidance for the exact turn or conversation."""
        del context
        return self._consume(conversation_id, execution_id)

    def process_for_conversation(
        self,
        conversation_id: str,
        *,
        context: Mapping[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Consume guidance for the latest active conversation turn."""
        del context
        return self._consume(conversation_id, "")

    def consume_for_conversation(self, conversation_id: str) -> list[dict[str, Any]]:
        """Atomically consume queued guidance for the active turn."""
        return self._consume(conversation_id, "")

    def process(
        self,
        *,
        target_type: str,
        target_id: str,
        conversation_id: str = "",
        context: Mapping[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Consume guidance through the same turn-runtime operation."""
        del target_type, context
        return self._consume(conversation_id, target_id)

    def _consume(self, conversation_id: str, turn_id: str) -> list[dict[str, Any]]:
        turn = self._resolve_existing_turn(conversation_id, turn_id)
        if turn is None:
            return []
        result = _invoke(
            TURN_ACTION,
            "consume_guidance",
            {"turn_id": turn["id"], "expected_revision": turn["revision"]},
        )
        return [_legacy_item(result["turn"], item) for item in result["items"]]

    def _resolve_turn(self, conversation_id: str, turn_id: str) -> dict[str, Any]:
        existing = self._resolve_existing_turn(conversation_id, turn_id)
        if existing is not None:
            return existing
        conversation = _invoke(
            CONVERSATION_RESOURCE,
            "get",
            {"conversation_id": conversation_id},
        )
        if not isinstance(conversation, Mapping):
            raise KeyError("conversation is unknown")
        return _invoke(
            TURN_ACTION,
            "begin",
            {
                "turn_id": turn_id or str(uuid.uuid4()),
                "request_id": str(uuid.uuid4()),
                "conversation_id": conversation_id,
                "conversation_revision": conversation["conversation_revision"],
            },
        )

    @staticmethod
    def _resolve_existing_turn(
        conversation_id: str, turn_id: str
    ) -> dict[str, Any] | None:
        if turn_id:
            turn = _invoke(TURN_RESOURCE, "get", {"turn_id": turn_id})
            if isinstance(turn, Mapping) and turn.get("status") not in _TERMINAL:
                return dict(turn)
        response = _invoke(
            TURN_RESOURCE,
            "list",
            {"conversation_id": conversation_id},
        )
        return next(
            (
                dict(turn)
                for turn in response.get("turns") or []
                if turn.get("status") not in _TERMINAL
            ),
            None,
        )

    def _find(
        self, guidance_id: str
    ) -> tuple[dict[str, Any], dict[str, Any]] | None:
        response = _invoke(TURN_RESOURCE, "list", {})
        for turn in response.get("turns") or []:
            for item in turn.get("guidance") or []:
                if item.get("id") == guidance_id:
                    return dict(turn), dict(item)
        return None


def _legacy_item(
    turn: Mapping[str, Any], item: Mapping[str, Any]
) -> dict[str, Any]:
    value = item.get("value") if isinstance(item.get("value"), Mapping) else {}
    return {
        "id": item["id"],
        "turn_id": turn["id"],
        "prompt": value.get("prompt") or "",
        "target_type": value.get("target_type") or "conversation",
        "target_id": value.get("target_id") or turn.get("conversation_id"),
        "conversation_id": value.get("conversation_id") or turn.get("conversation_id"),
        "status": item.get("status") or "queued",
        "visible": value.get("visible", True),
        "auto_send": value.get("auto_send", True),
        "metadata": dict(value.get("metadata") or {}),
        "created_at": turn.get("updated_at"),
        "updated_at": turn.get("updated_at"),
    }


def _invoke(contract_id: str, operation: str, payload: Mapping[str, Any]) -> Any:
    registry = get_container().get_or_none("interface_registry")
    plan = active_resolved_profile()
    if registry is None or plan is None:
        raise RuntimeError("global turn runtime is unavailable")
    return invoke_global_contract(
        registry,
        contract_id,
        operation,
        {"profile_id": plan.profile_id, **dict(payload)},
    )
