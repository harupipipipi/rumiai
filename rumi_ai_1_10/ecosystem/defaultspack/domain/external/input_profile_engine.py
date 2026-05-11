from __future__ import annotations

import re
from typing import Any

from domain.external.event import ExternalEvent
from domain.external.input_profile import InputProfile
from domain.input.envelope import RumiInputEnvelope


_INTERPOLATION_RE = re.compile(r"\$\{([^}]+)\}")


class InputProfileEngine:
    def __init__(self, profile: InputProfile | dict[str, Any]) -> None:
        self.profile = profile if isinstance(profile, InputProfile) else InputProfile.from_dict(profile)

    def matches(self, event: ExternalEvent) -> bool:
        if self.profile.provider and self.profile.provider != event.provider:
            return False
        match = self.profile.spec.get("match") if isinstance(self.profile.spec.get("match"), dict) else {}
        event_type = str(match.get("event_type") or "").strip()
        if event_type and event_type != str(event.event.get("type") or ""):
            return False
        return True

    def to_envelope(self, event: ExternalEvent) -> RumiInputEnvelope:
        spec = self.profile.spec
        input_spec = spec.get("input") if isinstance(spec.get("input"), dict) else {}
        role = str(self._resolve(input_spec.get("role", "user"), event.payload) or "user")
        content = str(self._resolve(input_spec.get("content", ""), event.payload) or "")
        metadata_spec = spec.get("metadata") if isinstance(spec.get("metadata"), dict) else {}
        metadata = self._resolve(metadata_spec, event.payload)
        if not isinstance(metadata, dict):
            metadata = {}
        source = dict(metadata.get("source") if isinstance(metadata.get("source"), dict) else {})
        source.setdefault("kind", "integration")
        source.setdefault("provider", event.provider)
        source.setdefault("event_id", event.event.get("id"))
        chat_spec = spec.get("chat") if isinstance(spec.get("chat"), dict) else {}
        chat = {
            "conversation_id": chat_spec.get("conversation_id"),
            "external_key": self._resolve(chat_spec.get("external_key"), event.payload) if chat_spec.get("external_key") else event.conversation.id,
            "title": self._resolve(chat_spec.get("title"), event.payload) if chat_spec.get("title") else f"{event.provider} {event.scope.id}",
            "model": self._resolve(chat_spec.get("model"), event.payload) if chat_spec.get("model") else event.metadata.get("model"),
        }
        return RumiInputEnvelope(
            role=role,
            input=content,
            chat=chat,
            source=source,
            metadata={
                **metadata,
                "external_event": event.as_dict(),
                "input_profile_id": self.profile.id,
            },
            params=dict(spec.get("params") if isinstance(spec.get("params"), dict) else {}),
            tools=list(spec.get("tools") if isinstance(spec.get("tools"), list) else []),
        )

    def _resolve(self, value: Any, payload: dict[str, Any]) -> Any:
        if isinstance(value, dict):
            if "when" in value and isinstance(value["when"], list):
                for branch in value["when"]:
                    if not isinstance(branch, dict):
                        continue
                    if "if" in branch and self._eval_condition(str(branch.get("if") or ""), payload):
                        return self._resolve(branch.get("value"), payload)
                    if "else" in branch:
                        return self._resolve(branch.get("value"), payload)
                return None
            return {key: self._resolve(item, payload) for key, item in value.items()}
        if isinstance(value, list):
            return [self._resolve(item, payload) for item in value]
        if isinstance(value, str):
            stripped = value.strip()
            if stripped == "$":
                return payload
            if stripped.startswith("$.") and "${" not in stripped and " " not in stripped:
                return self._json_path(stripped, payload)
            if stripped.startswith("coalesce(") and stripped.endswith(")"):
                for arg in self._split_args(stripped[len("coalesce("):-1]):
                    resolved = self._resolve_token(arg, payload)
                    if resolved not in (None, ""):
                        return resolved
                return ""
            return _INTERPOLATION_RE.sub(lambda match: str(self._resolve_token(match.group(1), payload) or ""), value)
        return value

    def _eval_condition(self, condition: str, payload: dict[str, Any]) -> bool:
        condition = condition.strip()
        if condition.startswith("exists(") and condition.endswith(")"):
            return self._resolve_token(condition[len("exists("):-1], payload) is not None
        if condition.startswith("equals(") and condition.endswith(")"):
            args = self._split_args(condition[len("equals("):-1])
            return len(args) >= 2 and self._resolve_token(args[0], payload) == self._resolve_token(args[1], payload)
        if condition.startswith("contains(") and condition.endswith(")"):
            args = self._split_args(condition[len("contains("):-1])
            return len(args) >= 2 and str(self._resolve_token(args[1], payload)) in str(self._resolve_token(args[0], payload))
        if "==" in condition:
            left, right = condition.split("==", 1)
            return self._resolve_token(left, payload) == self._resolve_token(right, payload)
        return bool(self._resolve_token(condition, payload))

    def _resolve_token(self, token: str, payload: dict[str, Any]) -> Any:
        token = str(token or "").strip()
        if token.startswith("$."):
            return self._json_path(token, payload)
        if token == "$":
            return payload
        if (token.startswith("'") and token.endswith("'")) or (token.startswith('"') and token.endswith('"')):
            return token[1:-1]
        if token.lower() == "true":
            return True
        if token.lower() == "false":
            return False
        return token

    @staticmethod
    def _json_path(expr: str, payload: dict[str, Any]) -> Any:
        current: Any = payload
        path = expr[2:].split(".") if expr.startswith("$.") else expr.split(".")
        for raw_part in path:
            if current is None:
                return None
            part = raw_part.strip()
            if not part:
                continue
            if isinstance(current, dict):
                current = current.get(part)
            elif isinstance(current, list) and part.isdigit():
                index = int(part)
                current = current[index] if 0 <= index < len(current) else None
            else:
                return None
        return current

    @staticmethod
    def _split_args(value: str) -> list[str]:
        args: list[str] = []
        current = ""
        quote = ""
        for char in value:
            if char in {"'", '"'}:
                quote = "" if quote == char else (char if not quote else quote)
            if char == "," and not quote:
                args.append(current.strip())
                current = ""
            else:
                current += char
        if current.strip():
            args.append(current.strip())
        return args
