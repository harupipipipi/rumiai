"""Revision-guarded provider-neutral tool definition registry."""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any, Callable, Mapping

from core_runtime.paths import USER_DATA_DIR
from core_runtime.profile_workspace import validate_profile_id
from core_runtime.runtime_locks import NamedLock

STORE_VERSION = "rumi.tool-definition-registry.v1"
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}$")


class ToolDefinitionRegistry:
    """Own tool definitions and finite aliases, but never execute tools."""

    def __init__(self, profile_id: str) -> None:
        self.profile_id = validate_profile_id(profile_id)
        self.root = (
            Path(USER_DATA_DIR)
            / "packs"
            / "rumi_tool_registry_pack"
            / "profiles"
            / self.profile_id
        )
        self.path = self.root / "tool-definitions.json"
        self.lock_root = self.root / "locks"

    def snapshot(self) -> dict[str, Any]:
        """Return definitions and aliases in deterministic order."""
        state = self._read()
        return {
            "version": STORE_VERSION,
            "profile_id": self.profile_id,
            "revision": state["revision"],
            "definitions": [
                dict(state["definitions"][key])
                for key in sorted(state["definitions"])
            ],
            "aliases": dict(sorted(state["aliases"].items())),
        }

    def resolve(self, tool_id: str) -> dict[str, Any] | None:
        """Resolve an exact definition or explicit finite alias."""
        requested = _identifier(tool_id)
        state = self._read()
        resolved = state["aliases"].get(requested, requested)
        definition = state["definitions"].get(resolved)
        if not isinstance(definition, dict):
            return None
        return {
            "requested_tool_id": requested,
            "resolved_tool_id": resolved,
            "aliased": requested != resolved,
            "definition": dict(definition),
            "registry_revision": state["revision"],
        }

    def save(self, record: Mapping[str, Any], expected_revision: int) -> dict[str, Any]:
        """Save one normalized definition at an exact revision."""
        normalized = _definition(record)
        with NamedLock(self.lock_root, "tool-definitions"):
            state = self._read()
            _assert_revision(state, expected_revision)
            state["definitions"][normalized["tool_id"]] = normalized
            state["revision"] += 1
            self._write(state)
        return {
            "action": "saved",
            "definition": normalized,
            "registry_revision": state["revision"],
        }

    def delete(self, tool_id: str, expected_revision: int) -> dict[str, Any]:
        """Delete one definition and aliases pointing to it."""
        tool_id = _identifier(tool_id)
        with NamedLock(self.lock_root, "tool-definitions"):
            state = self._read()
            _assert_revision(state, expected_revision)
            if tool_id not in state["definitions"]:
                raise KeyError("tool definition is unknown")
            del state["definitions"][tool_id]
            state["aliases"] = {
                alias: target
                for alias, target in state["aliases"].items()
                if target != tool_id
            }
            state["revision"] += 1
            self._write(state)
        return {
            "action": "deleted",
            "tool_id": tool_id,
            "registry_revision": state["revision"],
        }

    def alias(
        self, alias: str, target_tool_id: str, expected_revision: int
    ) -> dict[str, Any]:
        """Bind an explicit compatibility alias to an existing definition."""
        alias = _identifier(alias)
        target_tool_id = _identifier(target_tool_id)
        with NamedLock(self.lock_root, "tool-definitions"):
            state = self._read()
            _assert_revision(state, expected_revision)
            if target_tool_id not in state["definitions"]:
                raise KeyError("tool alias target is unknown")
            if alias in state["definitions"] and alias != target_tool_id:
                raise ValueError("tool alias collides with a definition")
            state["aliases"][alias] = target_tool_id
            state["revision"] += 1
            self._write(state)
        return {
            "action": "alias_saved",
            "alias": alias,
            "target_tool_id": target_tool_id,
            "registry_revision": state["revision"],
        }

    def _read(self) -> dict[str, Any]:
        if not self.path.is_file():
            return {
                "version": STORE_VERSION,
                "profile_id": self.profile_id,
                "revision": 0,
                "definitions": {},
                "aliases": {},
            }
        value = json.loads(self.path.read_text(encoding="utf-8"))
        if (
            not isinstance(value, dict)
            or value.get("version") != STORE_VERSION
            or value.get("profile_id") != self.profile_id
            or not isinstance(value.get("definitions"), dict)
            or not isinstance(value.get("aliases"), dict)
        ):
            raise ValueError("tool definition registry is invalid")
        return value

    def _write(self, state: Mapping[str, Any]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        os.chmod(self.root, 0o700)
        fd, temporary = tempfile.mkstemp(dir=self.root, prefix=".tools-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(state, handle, ensure_ascii=False, sort_keys=True)
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(temporary, 0o600)
            os.replace(temporary, self.path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)


def create_resource_operation(client: Any) -> Callable[[str, Mapping[str, Any]], Any]:
    """Create the read-only definition resource operation."""
    del client

    def operation(name: str, payload: Mapping[str, Any]) -> Any:
        registry = ToolDefinitionRegistry(_profile_id(payload))
        if name in {"list", "catalog"}:
            return registry.snapshot()
        if name in {"get", "resolve"}:
            return registry.resolve(str(payload.get("tool_id") or ""))
        raise ValueError(f"unknown tool definition operation: {name}")

    return operation


def create_manage_operation(client: Any) -> Callable[[str, Mapping[str, Any]], Any]:
    """Create revision-guarded definition management operations."""
    del client

    def operation(name: str, payload: Mapping[str, Any]) -> Any:
        registry = ToolDefinitionRegistry(_profile_id(payload))
        expected = int(payload.get("expected_revision") or 0)
        if name == "save":
            record = payload.get("definition")
            if not isinstance(record, Mapping):
                raise ValueError("tool definition is required")
            return registry.save(record, expected)
        if name == "delete":
            return registry.delete(str(payload.get("tool_id") or ""), expected)
        if name in {"alias", "set_alias"}:
            return registry.alias(
                str(payload.get("alias") or ""),
                str(payload.get("target_tool_id") or ""),
                expected,
            )
        raise ValueError(f"unknown tool definition management operation: {name}")

    return operation


def _definition(value: Mapping[str, Any]) -> dict[str, Any]:
    tool_id = _identifier(value.get("tool_id") or value.get("name"))
    schema = value.get("input_schema") or value.get("parameters") or {}
    if not isinstance(schema, Mapping):
        raise ValueError("tool input schema must be an object")
    execution = value.get("execution")
    execution = execution if isinstance(execution, Mapping) else {}
    kind = _identifier(execution.get("kind") or value.get("execution_kind") or "local")
    contract_id = str(
        execution.get("contract_id") or value.get("execution_contract_id") or ""
    ).strip()
    if not contract_id:
        raise ValueError("tool execution contract_id is required")
    authority = str(value.get("authority") or "").strip()
    if not authority:
        raise ValueError("tool authority operation is required")
    aliases = value.get("aliases") if isinstance(value.get("aliases"), list) else []
    normalized = {
        "tool_id": tool_id,
        "display_name": str(value.get("display_name") or tool_id)[:200],
        "description": str(value.get("description") or "")[:4000],
        "input_schema": _json_object(schema),
        "result_schema": _json_object(value.get("result_schema") or {}),
        "execution": {"kind": kind, "contract_id": contract_id},
        "authority": _identifier(authority),
        "risk": str(value.get("risk") or "unknown"),
        "policy_tags": sorted({str(item) for item in value.get("policy_tags") or []}),
        "aliases": sorted({_identifier(item) for item in aliases}),
        "widget": _json_object(value.get("widget") or {}),
        "source_adapter_id": str(value.get("source_adapter_id") or ""),
    }
    normalized["definition_hash"] = hashlib.sha256(
        json.dumps(normalized, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return normalized


def _json_object(value: Any) -> dict[str, Any]:
    encoded = json.dumps(value, ensure_ascii=False)
    decoded = json.loads(encoded)
    if not isinstance(decoded, dict):
        raise ValueError("value must be a JSON object")
    return decoded


def _identifier(value: Any) -> str:
    identifier = str(value or "").strip()
    if not _SAFE_ID.fullmatch(identifier):
        raise ValueError("identifier is invalid")
    return identifier


def _profile_id(payload: Mapping[str, Any]) -> str:
    return str(payload.get("profile_id") or "default")


def _assert_revision(state: Mapping[str, Any], expected: int) -> None:
    if int(state.get("revision") or 0) != expected:
        raise RuntimeError("tool definition registry revision is stale")
