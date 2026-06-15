"""HostIntent models for pack-to-host mediation."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any

from core_runtime.host_permissions import normalize_host_permission_id


HOST_INTENT_TYPES = frozenset({"host_intent", "host_stream_intent"})


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def args_hash(args: dict[str, Any], stream: dict[str, Any] | None = None) -> str:
    payload = {"args": dict(args or {}), "stream": dict(stream or {})}
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class HostIntent:
    type: str
    operation: str
    args: dict[str, Any] = field(default_factory=dict)
    stream: dict[str, Any] = field(default_factory=dict)
    reason: str = ""
    caller_pack_id: str = ""
    caller_function_id: str = ""
    conversation_id: str = ""
    host_function_id: str = ""

    @property
    def is_stream(self) -> bool:
        return self.type == "host_stream_intent" or bool(self.stream.get("enabled"))

    @property
    def args_hash(self) -> str:
        return args_hash(self.args, self.stream)

    @classmethod
    def from_payload(
        cls,
        payload: dict[str, Any],
        *,
        caller_pack_id: str = "",
        caller_function_id: str = "",
        conversation_id: str = "",
    ) -> "HostIntent":
        raw_args = payload.get("args")
        args = raw_args if isinstance(raw_args, dict) else {}
        raw_stream = payload.get("stream")
        stream = raw_stream if isinstance(raw_stream, dict) else {}
        raw_caller = payload.get("caller")
        caller = raw_caller if isinstance(raw_caller, dict) else {}
        return cls(
            type=str(payload.get("type") or "").strip(),
            operation=normalize_host_permission_id(str(payload.get("operation") or "").strip()),
            args=dict(args),
            stream=dict(stream),
            reason=str(payload.get("reason") or "").strip(),
            caller_pack_id=str(caller.get("pack_id") or caller_pack_id or "").strip(),
            caller_function_id=str(caller.get("function_id") or caller_function_id or "").strip(),
            conversation_id=str(payload.get("conversation_id") or conversation_id or "").strip(),
            host_function_id=str(payload.get("host_function_id") or "").strip(),
        )

    def resource(self) -> dict[str, Any]:
        return {
            "kind": "host_intent",
            "operation": self.operation,
            "host_action": self.operation,
            "caller_pack_id": self.caller_pack_id,
            "caller_function_id": self.caller_function_id,
            "host_function_id": self.host_function_id,
            "conversation_id": self.conversation_id,
            "args_hash": self.args_hash,
            "stream_config": dict(self.stream),
            "stream_enabled": self.is_stream,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "operation": self.operation,
            "args": dict(self.args),
            "stream": dict(self.stream),
            "reason": self.reason,
            "caller": {
                "pack_id": self.caller_pack_id,
                "function_id": self.caller_function_id,
            },
            "conversation_id": self.conversation_id,
            "host_function_id": self.host_function_id,
            "args_hash": self.args_hash,
        }


def is_host_intent_payload(value: Any) -> bool:
    return isinstance(value, dict) and str(value.get("type") or "").strip() in HOST_INTENT_TYPES
