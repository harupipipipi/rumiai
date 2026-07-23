from __future__ import annotations

import hashlib
import json
import re
import threading
import time
import unicodedata
import uuid
from copy import deepcopy
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from domain.frontend.command_registry import SlashCommandRegistry
from domain.frontend_settings_store import FrontendSettingsStore, defaultspack_frontend_settings_path

API_VERSION = "tobkiri.commands/v1"
PACK_ID = "defaultspack"
SCHEMA_PATH = Path(__file__).resolve().parents[2] / "schemas" / "command-protocol-v1.schema.json"
LEGACY_HOST_STATE_REFS = {
    "toggle_yolo": "host:approval.full_access",
    "toggle_ultra_yolo": "host:approval.full_access",
    "set_fast_mode": "host:model.fast_mode",
}

# This is a legacy compatibility registry, not the future host-operation
# registry. Keeping it explicit prevents a manifest typo from becoming a
# silent frontend no-op while the v1 broker is introduced.
LEGACY_FRONTEND_HANDLERS = {
    "clear_composer_state",
    "new_conversation",
    "open_branch_picker",
    "open_command_help",
    "open_context_viewer",
    "open_diff_preview",
    "open_file_search",
    "open_keymap_settings",
    "open_permissions",
    "open_settings",
    "open_theme_settings",
    "open_tool_picker",
    "prepare_lint_run",
    "prepare_test_run",
    "set_fast_mode",
    "set_home_title",
    "set_mode_agent",
    "set_mode_chat",
    "set_mode_coding",
    "set_price_mode",
    "show_status",
    "show_usage",
    "start_review",
    "toggle_ultra_yolo",
    "toggle_yolo",
}


class CommandProtocolSchemaError(ValueError):
    pass


def validate_protocol_document(document: dict[str, Any]) -> None:
    """Validate a v1 manifest/catalog with strict Draft 2020-12 semantics."""

    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    errors = sorted(
        Draft202012Validator(schema).iter_errors(document),
        key=lambda item: tuple(str(part) for part in item.absolute_path),
    )
    if not errors:
        return
    first = errors[0]
    path = ".".join(str(part) for part in first.absolute_path) or "$"
    raise CommandProtocolSchemaError(f"{path}: {first.message}")


class CommandProtocolRegistry:
    """Resolved Command Protocol v1 view over the legacy command registry.

    Pack manifests remain authoritative and separate. This class only derives
    a validated, read-only catalog and a dual-stack invocation envelope.
    """

    _datasource_cache_lock = threading.Lock()
    _datasource_cache: dict[str, tuple[float, list[dict[str, Any]]]] = {}
    _datasource_cache_ttl_seconds = 15.0

    def __init__(self, pack_root: Path | None = None) -> None:
        self.pack_root = pack_root or Path(__file__).resolve().parents[2]
        self.legacy = SlashCommandRegistry(self.pack_root)

    def catalog(self) -> dict[str, Any]:
        legacy_commands = [*self.legacy.list_commands(), *self._registered_settings_commands()]
        diagnostics = [deepcopy(item) for item in self.legacy.manifest_errors()]
        collisions = self._identity_collisions(legacy_commands)
        diagnostics.extend(collisions)
        commands = [self._resolve_command(command, diagnostics) for command in legacy_commands]
        serialized = json.dumps(commands, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        revision = hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:16]
        catalog = {
            "api_version": API_VERSION,
            "kind": "ResolvedCommandCatalog",
            "catalog_revision": revision,
            "pack_generations": {PACK_ID: 1},
            "commands": commands,
            "states": [
                {
                    "state_ref": "defaultspack:models.deepthink_enabled",
                    "schema_version": "1.0.0",
                    "value_type": "boolean",
                    "authority": "backend_runtime",
                }
            ],
            "datasources": [
                {
                    "datasource_ref": "tobkiri:model_catalog",
                    "schema_version": "1.0.0",
                    "item_contract": "OptionItem",
                    "capabilities": ["search", "cursor_paging", "selected_item_retention"],
                },
                {
                    "datasource_ref": "tobkiri:provider_catalog",
                    "schema_version": "1.0.0",
                    "item_contract": "OptionItem",
                    "capabilities": ["search", "cursor_paging", "selected_item_retention"],
                },
            ],
            "state_snapshots": self.query_states(
                ["defaultspack:models.deepthink_enabled"]
            )["states"],
            "diagnostics": diagnostics,
        }
        validate_protocol_document(catalog)
        return catalog

    def invoke(self, payload: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
        command_ref = str(payload.get("command_ref") or payload.get("command") or "").strip()
        short_name = command_ref.split(":", 1)[-1] if ":" in command_ref else command_ref
        command = self.legacy.find_command(short_name)
        operation_id = str(
            payload.get("invocation_id")
            or payload.get("operation_id")
            or uuid.uuid4()
        )
        if command is None:
            command = next(
                (
                    item
                    for item in self._registered_settings_commands()
                    if short_name in {
                        str(item.get("id") or ""),
                        str(item.get("name") or ""),
                        *(str(alias or "") for alias in item.get("aliases") or []),
                    }
                ),
                None,
            )
        if command is None:
            return {
                "api_version": API_VERSION,
                "operation_id": operation_id,
                "status": "failed",
                "command_ref": command_ref,
                "error": {"code": "COMMAND_NOT_FOUND", "message": "command not found"},
                "state_changes": [],
            }

        resolved = self._resolve_command(command, [])
        availability = resolved.get("availability", {})
        if availability.get("status") == "unavailable":
            return {
                "api_version": API_VERSION,
                "operation_id": operation_id,
                "status": "failed",
                "command_ref": resolved["canonical_id"],
                "error": {
                    "code": "COMMAND_UNAVAILABLE",
                    "message": availability.get("reason") or "command is unavailable",
                },
                "state_changes": [],
            }

        legacy_payload = {
            "command": command.get("name") or command.get("id"),
            "args": payload.get("args") if isinstance(payload.get("args"), dict) else {},
            "conversation_id": payload.get("conversation_id"),
            "mode": payload.get("mode") or "chat",
            "invocation_id": operation_id,
            "idempotency_key": payload.get("idempotency_key"),
            "client_sequence": payload.get("client_sequence"),
            "expected_revision": payload.get("expected_revision"),
        }
        if command.get("source") == "settings.registered_slash_commands":
            legacy_result = {
                "status": "ok",
                "data": {
                    "command": deepcopy(command),
                    "executed": False,
                    "action": command.get("execution", {}).get("action"),
                    "args": deepcopy(legacy_payload["args"]),
                },
            }
        else:
            legacy_result = self.legacy.execute(legacy_payload, context or {})
        if legacy_result.get("status") == "error":
            return {
                "api_version": API_VERSION,
                "operation_id": operation_id,
                "status": "failed",
                "command_ref": resolved["canonical_id"],
                "error": deepcopy(legacy_result.get("error") or {}),
                "state_changes": [],
            }
        data = legacy_result.get("data") if isinstance(legacy_result.get("data"), dict) else {}
        requires_approval = bool(data.get("requires_approval"))
        return {
            "api_version": API_VERSION,
            "operation_id": str(data.get("operation_id") or operation_id),
            "status": "approval_required" if requires_approval else "succeeded",
            "command_ref": resolved["canonical_id"],
            "client_sequence": data.get("client_sequence", payload.get("client_sequence")),
            "state_changes": deepcopy(data.get("state_changes") or []),
            "approval": (
                {
                    "required": True,
                    "permission_ids": resolved.get("authorization", {}).get("permissions", []),
                }
                if requires_approval
                else None
            ),
            "message": data.get("message"),
            "legacy_result": deepcopy(data),
        }

    def query_states(self, state_refs: list[str] | None = None) -> dict[str, Any]:
        requested = {str(item or "").strip() for item in state_refs or [] if str(item or "").strip()}
        states: list[dict[str, Any]] = []
        deepthink_ref = "defaultspack:models.deepthink_enabled"
        if not requested or deepthink_ref in requested:
            from domain.ai_client.model_runtime_settings import ModelRuntimeSettingsService

            value = ModelRuntimeSettingsService(self.pack_root).get_deepthink_enabled()
            states.append(
                {
                    "state_ref": deepthink_ref,
                    "value": bool(value.get("enabled")),
                    "revision": int(value.get("revision") or 0),
                    "freshness": "authoritative",
                }
            )
        return {"api_version": API_VERSION, "states": states}

    def query_datasource(self, payload: dict[str, Any]) -> dict[str, Any]:
        datasource_ref = str(payload.get("datasource_ref") or "").strip()
        datasource_aliases = {
            "tobkiri:model_catalog": "tobkiri:model_catalog",
            "tobkiri:models.resolved": "tobkiri:model_catalog",
            "tobkiri:provider_catalog": "tobkiri:provider_catalog",
            "tobkiri:providers.resolved": "tobkiri:provider_catalog",
        }
        canonical_ref = datasource_aliases.get(datasource_ref)
        if canonical_ref is None:
            return {
                "api_version": API_VERSION,
                "status": "failed",
                "error": {"code": "DATASOURCE_NOT_FOUND", "message": "datasource not found"},
                "items": [],
            }
        from ecosystem.defaultspack.backend.ai_client.provider_catalog import list_profile_catalog

        query = self._search_text(payload.get("query"))
        try:
            offset = max(0, int(str(payload.get("cursor") or "0")))
        except ValueError:
            offset = 0
        try:
            limit = max(1, min(100, int(payload.get("limit") or 25)))
        except (TypeError, ValueError):
            limit = 25
        profiles = self._cached_profile_catalog(list_profile_catalog)
        if canonical_ref == "tobkiri:provider_catalog":
            items = self._provider_options(profiles)
        else:
            items = [self._model_option(profile) for profile in profiles if isinstance(profile, dict)]
        if query:
            items = [
                item
                for item in items
                if query in self._search_text(
                    " ".join(
                        [
                            str(item.get("value") or ""),
                            str(item.get("label", {}).get("fallback") or ""),
                            str(item.get("description", {}).get("fallback") or ""),
                        ]
                    )
                )
            ]
        selected_values = {
            str(value or "").strip()
            for value in payload.get("selected_values") or []
            if str(value or "").strip()
        }
        retained = [item for item in items if str(item.get("value") or "") in selected_values]
        page = items[offset : offset + limit]
        if offset == 0 and retained:
            page_ids = {str(item.get("value") or "") for item in page}
            page = [*retained, *(item for item in page if str(item.get("value") or "") not in page_ids)]
            page = page[:limit]
        next_offset = offset + len(page)
        return {
            "api_version": API_VERSION,
            "status": "succeeded",
            "datasource_ref": canonical_ref,
            "request_id": str(payload.get("request_id") or uuid.uuid4()),
            "items": page,
            "page": {
                "has_more": next_offset < len(items),
                "next_cursor": str(next_offset) if next_offset < len(items) else None,
            },
        }

    def _resolve_command(
        self, command: dict[str, Any], diagnostics: list[dict[str, Any]]
    ) -> dict[str, Any]:
        command_id = str(command.get("id") or command.get("name") or "").strip()
        canonical_id = f"{PACK_ID}:{command_id}"
        execution = command.get("execution") if isinstance(command.get("execution"), dict) else {}
        execution_type = str(execution.get("type") or "frontend")
        availability: dict[str, Any] = {"status": "available"}
        if execution_type == "frontend":
            action = str(execution.get("action") or "").strip()
            if action not in LEGACY_FRONTEND_HANDLERS:
                availability = {
                    "status": "unavailable",
                    "reason_code": "handler_missing",
                    "reason": f"Frontend handler is not registered for {action or command_id}",
                }
                diagnostics.append(
                    {
                        "level": "error",
                        "code": "handler_missing",
                        "command_ref": canonical_id,
                        "message": availability["reason"],
                    }
                )
        elif execution_type not in {
            "model_command",
            "settings_patch",
            "rumi_function",
            "chat_action",
            "pack_block",
        }:
            availability = {
                "status": "unavailable",
                "reason_code": "binding_missing",
                "reason": f"Unsupported legacy execution type: {execution_type}",
            }

        return {
            "canonical_id": canonical_id,
            "pack_id": PACK_ID,
            "pack_generation": 1,
            "command_version": "1.0.0",
            "identity": {
                "id": command_id,
                "name": self._slash_token(command.get("name") or command_id),
                "aliases": list(
                    dict.fromkeys(
                        token
                        for token in (
                            self._slash_token(item)
                            for item in command.get("aliases") or []
                        )
                        if token
                    )
                )[:16],
                "version": "1.0.0",
            },
            "presentation": self._presentation(command),
            "execution": self._execution(command),
            "authorization": {
                "risk": command.get("risk") or "low",
                "permissions": [],
                "approval_required": command.get("risk") == "high",
            },
            "constraints": {"modes": deepcopy(command.get("modes") or [])},
            "availability": availability,
            "legacy": deepcopy(command),
        }

    def _registered_settings_commands(self) -> list[dict[str, Any]]:
        settings = FrontendSettingsStore(
            defaultspack_frontend_settings_path(self.pack_root)
        ).read()
        commands_section = settings.get("commands") if isinstance(settings.get("commands"), dict) else {}
        records = commands_section.get("registered_slash_commands") if isinstance(commands_section, dict) else []
        if not isinstance(records, list):
            return []
        commands: list[dict[str, Any]] = []
        seen: set[str] = set()
        for raw in records:
            record = raw if isinstance(raw, dict) else {"name": raw, "action": "toggle_yolo"}
            if record.get("enabled") is False:
                continue
            name = self._slash_token(record.get("name") or record.get("command") or record.get("id"))
            action = str(record.get("action") or record.get("frontend_action") or "").strip()
            if not name or name in seen or action not in LEGACY_FRONTEND_HANDLERS:
                continue
            seen.add(name)
            args = self._registered_action_args(action)
            raw_aliases = record.get("aliases")
            aliases = raw_aliases.split(",") if isinstance(raw_aliases, str) else raw_aliases
            if not isinstance(aliases, list):
                aliases = []
            commands.append(
                {
                    "id": f"user_{name}",
                    "name": name,
                    "aliases": [
                        token
                        for token in dict.fromkeys(
                            self._slash_token(item)
                            for item in aliases
                        )
                        if token and token != name
                    ][:8],
                    "label": str(record.get("label") or name),
                    "description": str(record.get("description") or f"Run {action}."),
                    "category": self._registered_action_category(action),
                    "visibility": "default",
                    "risk": "medium" if action in {"toggle_yolo", "toggle_ultra_yolo"} else "low",
                    "modes": ["chat", "coding", "agent"],
                    "args": args,
                    "execution": {"type": "frontend", "action": action},
                    "source": "settings.registered_slash_commands",
                }
            )
        return commands

    @staticmethod
    def _registered_action_args(action: str) -> list[dict[str, Any]]:
        if action in {"toggle_yolo", "toggle_ultra_yolo", "set_fast_mode"}:
            return [{"name": "enabled", "type": "boolean", "required": False}]
        if action in {"open_model_picker", "open_tool_picker"}:
            return [{"name": "query", "type": "string", "required": False}]
        if action == "open_settings":
            return [{"name": "section", "type": "string", "required": False}]
        if action == "set_price_mode":
            return [{"name": "tier", "type": "enum", "required": False, "values": ["low", "high"]}]
        return []

    @staticmethod
    def _registered_action_category(action: str) -> str:
        if "model" in action or action in {"set_fast_mode", "set_price_mode"}:
            return "model"
        if "tool" in action:
            return "tools"
        if "settings" in action or action in {"open_permissions", "open_theme_settings", "open_keymap_settings"}:
            return "settings"
        if "mode" in action or "yolo" in action:
            return "mode"
        return "chat"

    def _presentation(self, command: dict[str, Any]) -> dict[str, Any]:
        args = command.get("args") if isinstance(command.get("args"), list) else []
        execution = command.get("execution") if isinstance(command.get("execution"), dict) else {}
        execution_type = str(execution.get("type") or "frontend")
        command_id = str(command.get("id") or "")
        frontend_action = str(execution.get("action") or "")
        qualified_name = str(execution.get("qualified_name") or "")
        if execution_type == "model_command":
            input_contract: dict[str, Any] = {
                "kind": "search_select",
                "argument": "query",
                "selection": "single",
                "datasource_ref": "tobkiri:model_catalog",
                "search": {"enabled": True, "min_chars": 0, "debounce_ms": 150},
                "keyboard": {"commit_keys": ["Enter", "Tab"]},
            }
        elif qualified_name == "defaultspack:ai.provider_command":
            input_contract = {
                "kind": "search_select",
                "argument": "target",
                "selection": "single",
                "datasource_ref": "tobkiri:provider_catalog",
                "search": {"enabled": True, "min_chars": 0, "debounce_ms": 150},
                "keyboard": {"commit_keys": ["Enter", "Tab"]},
            }
        elif frontend_action in LEGACY_HOST_STATE_REFS:
            input_contract = {
                "kind": "toggle",
                "argument": "enabled",
                "state_ref": LEGACY_HOST_STATE_REFS[frontend_action],
                "bare_behavior": "toggle",
                "show_current_state": True,
            }
        elif command_id == "deepthink" or execution_type == "settings_patch":
            section = str(execution.get("section") or "models")
            field = str(execution.get("field") or "deepthink_enabled")
            input_contract = {
                "kind": "toggle",
                "argument": "enabled",
                "state_ref": f"defaultspack:{section}.{field}",
                "bare_behavior": "toggle",
                "show_current_state": True,
            }
        elif len(args) == 1 and args[0].get("type") == "enum":
            input_contract = {
                "kind": "select",
                "argument": args[0].get("name"),
                "selection": "single",
                "options": [
                    {"value": value, "label": {"fallback": str(value)}}
                    for value in args[0].get("values", [])
                ],
            }
        elif args:
            input_contract = {
                "kind": "form",
                "fields": [
                    self._form_field(item)
                    for item in args
                    if isinstance(item, dict)
                ],
            }
        else:
            input_contract = {"kind": "action", "run_on_bare": True}

        mounts = [
            {
                "slot_ref": "tobkiri:command_palette.commands",
                "display": "command",
                "order": 100,
            }
        ]
        if command_id == "deepthink":
            mounts.insert(
                0,
                {
                    "slot_ref": "tobkiri:composer.toolbar.leading",
                    "display": "persistent",
                    "order": 20,
                },
            )
        return {
            "label": {"fallback": str(command.get("label") or command_id)},
            "description": {"fallback": str(command.get("description") or "")},
            "category": command.get("category") or "other",
            "visibility": command.get("visibility") or "default",
            "icon": self._icon_token(command, input_contract),
            "input": input_contract,
            "mounts": mounts,
        }

    @staticmethod
    def _form_field(item: dict[str, Any]) -> dict[str, Any]:
        field = {
            "argument": item.get("name"),
            "control": "checkbox" if item.get("type") == "boolean" else "text",
            "required": bool(item.get("required")),
        }
        label = str(item.get("label") or "").strip()
        placeholder = str(item.get("placeholder") or "").strip()
        if label:
            field["label"] = {"fallback": label}
        if placeholder:
            field["placeholder"] = {"fallback": placeholder}
        return field

    @staticmethod
    def _execution(command: dict[str, Any]) -> dict[str, Any]:
        execution = command.get("execution") if isinstance(command.get("execution"), dict) else {}
        execution_type = str(execution.get("type") or "frontend")
        if execution_type == "frontend":
            action = str(execution.get("action") or command.get("id") or "")
            state_ref = LEGACY_HOST_STATE_REFS.get(action)
            if state_ref:
                return {
                    "kind": "state_mutation",
                    "state_ref": state_ref,
                    "mutation": {"argument": "enabled", "when_present": "set"},
                    "legacy_type": execution_type,
                }
            return {
                "kind": "host_operation",
                "operation_ref": f"host:{action}",
                "legacy_type": execution_type,
            }
        if execution_type == "model_command":
            return {
                "kind": "state_mutation",
                "state_ref": "tobkiri:active_model",
                "mutation": {"argument": "query", "when_present": "set"},
                "legacy_type": execution_type,
            }
        if execution_type == "settings_patch":
            return {
                "kind": "state_mutation",
                "state_ref": (
                    f"defaultspack:{execution.get('section')}.{execution.get('field')}"
                ),
                "mutation": {"argument": "enabled", "when_present": "set"},
                "legacy_type": execution_type,
            }
        qualified = str(
            execution.get("qualified_name")
            or execution.get("action")
            or command.get("id")
            or ""
        )
        if command.get("id") == "deepthink":
            return {
                "kind": "state_mutation",
                "state_ref": "defaultspack:models.deepthink_enabled",
                "mutation": {"argument": "enabled", "when_present": "set"},
                "legacy_type": execution_type,
            }
        return {
            "kind": "pack_operation",
            "operation_ref": qualified,
            "legacy_type": execution_type,
        }

    @staticmethod
    def _identity_collisions(commands: list[dict[str, Any]]) -> list[dict[str, Any]]:
        claims: dict[str, list[str]] = {}
        for command in commands:
            canonical = f"{PACK_ID}:{command.get('id')}"
            for claim in [command.get("name"), *(command.get("aliases") or [])]:
                token = CommandProtocolRegistry._slash_token(claim)
                if token:
                    claims.setdefault(token, []).append(canonical)
        return [
            {
                "level": "error",
                "code": "identity_collision",
                "claim": claim,
                "commands": refs,
                "message": f"Short command claim '{claim}' is ambiguous; use canonical invocation",
            }
            for claim, refs in claims.items()
            if len(set(refs)) > 1
        ]

    @staticmethod
    def _search_text(value: Any) -> str:
        return unicodedata.normalize("NFKC", str(value or "")).casefold().strip()

    @staticmethod
    def _slash_token(value: Any) -> str:
        normalized = unicodedata.normalize("NFKC", str(value or "")).casefold().strip()
        normalized = re.sub(r"[\s-]+", "_", normalized)
        normalized = re.sub(r"[^a-z0-9._-]", "", normalized)
        normalized = re.sub(r"_+", "_", normalized).strip("_.-")
        return normalized[:128]

    @staticmethod
    def _model_option(profile: dict[str, Any]) -> dict[str, Any]:
        profile_id = str(
            profile.get("profile_id")
            or profile.get("qualified_model_id")
            or profile.get("id")
            or ""
        )
        provider_id = str(profile.get("provider_id") or profile.get("provider") or "")
        label = str(profile.get("display_name") or profile.get("name") or profile_id)
        availability = profile.get("availability") if isinstance(profile.get("availability"), dict) else {}
        configured = bool(availability.get("configured") or availability.get("active"))
        available = availability.get("available") is not False
        disabled_reason = None
        if not configured:
            disabled_reason = {"fallback": "Provider credential is not configured"}
        elif not available:
            disabled_reason = {"fallback": "Model is currently unavailable"}
        return {
            "id": profile_id,
            "value": profile_id,
            "label": {"fallback": label},
            "description": {"fallback": f"{provider_id} · {profile.get('model_id') or profile_id}"},
            "icon": "model",
            "badges": [
                {"label": "Configured", "tone": "success"}
            ] if configured else [],
            "disabled": bool(disabled_reason),
            "disabled_reason": disabled_reason,
            "metadata": {
                "provider_id": provider_id,
                "configured": configured,
                "available": available,
                "capability_tags": deepcopy(profile.get("capability_tags") or []),
            },
        }

    @classmethod
    def _cached_profile_catalog(cls, loader: Any) -> list[dict[str, Any]]:
        now = time.monotonic()
        with cls._datasource_cache_lock:
            cached = cls._datasource_cache.get("profiles")
            if cached and now - cached[0] < cls._datasource_cache_ttl_seconds:
                return deepcopy(cached[1])
        profiles = [item for item in loader() if isinstance(item, dict)]
        with cls._datasource_cache_lock:
            cls._datasource_cache["profiles"] = (now, deepcopy(profiles))
        return profiles

    @classmethod
    def invalidate_datasource_cache(cls) -> None:
        with cls._datasource_cache_lock:
            cls._datasource_cache.clear()

    @classmethod
    def _provider_options(cls, profiles: list[dict[str, Any]]) -> list[dict[str, Any]]:
        providers: dict[str, dict[str, Any]] = {}
        for profile in profiles:
            provider_id = str(profile.get("provider_id") or profile.get("provider") or "").strip()
            if not provider_id:
                continue
            availability = profile.get("availability") if isinstance(profile.get("availability"), dict) else {}
            current = providers.setdefault(
                provider_id,
                {
                    "id": provider_id,
                    "value": provider_id,
                    "label": {"fallback": str(profile.get("provider_display_name") or provider_id)},
                    "description": {"fallback": "0 models"},
                    "icon": "provider",
                    "badges": [],
                    "disabled": True,
                    "disabled_reason": {"fallback": "No selectable models are currently available"},
                    "metadata": {
                        "provider_id": provider_id,
                        "configured": False,
                        "available": False,
                        "model_count": 0,
                    },
                },
            )
            metadata = current["metadata"]
            metadata["model_count"] = int(metadata["model_count"]) + 1
            metadata["configured"] = bool(metadata["configured"] or availability.get("configured") or availability.get("active"))
            metadata["available"] = bool(metadata["available"] or availability.get("available") is not False)
        for item in providers.values():
            metadata = item["metadata"]
            item["description"] = {"fallback": f"{metadata['model_count']} models"}
            item["disabled"] = not bool(metadata["available"])
            item["disabled_reason"] = (
                {"fallback": "No selectable models are currently available"}
                if item["disabled"]
                else None
            )
            if metadata["configured"]:
                item["badges"] = [{"label": "Configured", "tone": "success"}]
        return sorted(providers.values(), key=lambda item: str(item["label"]["fallback"]).casefold())

    @staticmethod
    def _icon_token(command: dict[str, Any], input_contract: dict[str, Any]) -> str:
        command_token = CommandProtocolRegistry._slash_token(command.get("id") or command.get("name"))
        if command_token:
            return command_token
        kind = str(input_contract.get("kind") or "action")
        category = str(command.get("category") or "other")
        if kind == "toggle":
            return "toggle"
        if kind in {"select", "search_select"}:
            return "search" if kind == "search_select" else "list"
        return {
            "chat": "message-square",
            "model": "cpu",
            "mode": "sliders-horizontal",
            "coding": "code-2",
            "tools": "wrench",
            "settings": "settings",
            "debug": "bug",
        }.get(category, "sparkles")
