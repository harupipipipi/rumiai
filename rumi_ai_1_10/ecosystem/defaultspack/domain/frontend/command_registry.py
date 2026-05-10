from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from domain.chat.store import ChatStore


CATEGORIES = {"chat", "model", "mode", "coding", "tools", "settings", "debug"}
VISIBILITIES = {"default", "advanced", "hidden"}
MODES = {"chat", "coding", "agent"}
RISKS = {"low", "medium", "high"}
MANIFEST_ORIGIN_DEFAULT = "default"
MANIFEST_ORIGIN_PACK = "pack"
MANIFEST_ORIGIN_USER = "user"
ALLOWED_RUMI_FUNCTIONS = {
    "ai_get_preferred_model",
    "ai_set_preferred_model",
    "ai_get_thinking_level",
    "ai_set_thinking_level",
    "ai_get_effective_thinking_level",
    "ai_normalize_thinking_level",
}


def ok(data: Any = None) -> dict[str, Any]:
    return {"status": "ok", "data": data}


def error(message: str, code: str = "ERROR", **extra: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {"code": code, "message": message}
    payload.update(extra)
    return {"status": "error", "error": payload}


class SlashCommandRegistry:
    """Manifest-driven slash command registry for defaultspack UI commands."""

    def __init__(self, pack_root: Path | None = None) -> None:
        self._pack_root = pack_root or Path(__file__).resolve().parents[2]

    def list_commands(self) -> list[dict[str, Any]]:
        commands, _manifest_errors = self._commands_with_errors()
        return [self._public_command(command) for command in commands]

    def manifest_errors(self) -> list[dict[str, Any]]:
        _commands, manifest_errors = self._commands_with_errors()
        return manifest_errors

    def find_command(self, name: str) -> dict[str, Any] | None:
        needle = str(name or "").strip().lower().lstrip("/")
        if not needle:
            return None
        commands, _manifest_errors = self._commands_with_errors()
        for command in reversed(commands):
            names = [command.get("id"), command.get("name"), *(command.get("aliases") or [])]
            if needle in {str(item or "").strip().lower() for item in names}:
                return command
        return None

    def execute(self, payload: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
        command = self.find_command(str(payload.get("command") or ""))
        if command is None:
            return error("command not found", "NOT_FOUND")

        mode = str(payload.get("mode") or "chat")
        if mode not in command.get("modes", []):
            return error("command is not available in this mode", "COMMAND_UNAVAILABLE", details={"mode": mode})

        args_result = self._coerce_args(command, payload.get("args") if isinstance(payload.get("args"), dict) else {})
        if isinstance(args_result, dict) and args_result.get("status") == "error":
            return args_result
        args = args_result
        if command.get("risk") == "high":
            return ok({
                "command": self._public_command(command),
                "executed": False,
                "requires_approval": True,
                "message": "This command requires approval center confirmation.",
            })

        execution = command.get("execution") if isinstance(command.get("execution"), dict) else {}
        execution_type = str(execution.get("type") or "frontend")

        if execution_type == "frontend":
            return ok({
                "command": self._public_command(command),
                "executed": False,
                "action": execution.get("action"),
                "args": args,
            })

        if execution_type == "rumi_function":
            if command.get("_manifest_origin") != MANIFEST_ORIGIN_DEFAULT:
                return error("rumi_function execution is only allowed for built-in default commands", "INVALID_COMMAND")
            qualified_name = str(execution.get("qualified_name") or "").strip()
            if not qualified_name:
                return error("rumi_function command is missing qualified_name", "INVALID_COMMAND")
            if self._rumi_function_id(qualified_name) not in ALLOWED_RUMI_FUNCTIONS:
                return error("rumi_function command is not allowlisted", "INVALID_COMMAND")
            function_args = dict(args)
            if payload.get("conversation_id"):
                function_args.setdefault("conversation_id", payload.get("conversation_id"))
            builtin_result = self._execute_builtin_rumi_function(qualified_name, function_args)
            if isinstance(builtin_result, dict) and builtin_result.get("status") == "error":
                return builtin_result
            if builtin_result is not None:
                return ok({"command": self._public_command(command), "executed": True, "result": builtin_result})
            return error("rumi_function command is not allowlisted", "INVALID_COMMAND")

        if execution_type == "chat_action":
            return self._execute_chat_action(command, execution, args, payload, context or {})

        return error("unsupported command execution type", "INVALID_COMMAND", details={"type": execution_type})

    def _execute_chat_action(
        self,
        command: dict[str, Any],
        execution: dict[str, Any],
        args: dict[str, Any],
        payload: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        action = str(execution.get("action") or "")
        if action != "compact_conversation":
            return ok({"command": self._public_command(command), "executed": False, "action": action, "args": args})

        conversation_id = str(payload.get("conversation_id") or "").strip()
        if not conversation_id:
            return error("conversation_id is required", "INVALID_INPUT")
        conversation = ChatStore().get_conversation(conversation_id)
        if conversation is None:
            return error("Conversation not found", "NOT_FOUND")

        from blocks.context.compact import run as compact_run

        result = compact_run(
            {
                "conversation_id": conversation_id,
                "goal": str(args.get("instruction") or "Compact current conversation"),
                "messages": conversation.get("messages", []),
                "summary": args.get("instruction"),
            },
            context,
        )
        if isinstance(result, dict) and result.get("status") == "ok":
            return ok({"command": self._public_command(command), "executed": True, "result": result.get("data")})
        return result if isinstance(result, dict) else error("compact command failed", "EXECUTION_FAILED")

    def _execute_builtin_rumi_function(self, qualified_name: str, args: dict[str, Any]) -> dict[str, Any] | None:
        function_id = self._rumi_function_id(qualified_name)
        if function_id not in ALLOWED_RUMI_FUNCTIONS:
            return None

        try:
            from domain.ai_client.model_runtime_settings import ModelRuntimeSettingsService

            service = ModelRuntimeSettingsService(self._pack_root)
            if function_id == "ai_get_preferred_model":
                return {"profile_id": service.get_preferred_model()}
            if function_id == "ai_set_preferred_model":
                return service.set_preferred_model(str(args.get("profile_id") or args.get("model") or ""))
            if function_id == "ai_get_thinking_level":
                return service.get_thinking_level(args.get("scope", "global"), args.get("profile_id"), args.get("conversation_id"))
            if function_id == "ai_set_thinking_level":
                return service.set_thinking_level(str(args.get("level") or ""), args.get("scope", "global"), args.get("profile_id"), args.get("conversation_id"))
            if function_id == "ai_get_effective_thinking_level":
                return service.get_effective_thinking_level(args.get("profile_id"), args.get("conversation_id"))
            if function_id == "ai_normalize_thinking_level":
                return service.normalize_for_provider(
                    str(args.get("provider_id") or ""),
                    str(args.get("model_id") or args.get("model") or ""),
                    str(args.get("level") or args.get("thinking_level") or ""),
                )
        except Exception as exc:
            return error(str(exc), "EXECUTION_FAILED")
        return None

    def _commands_with_errors(self) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        manifest_errors: list[dict[str, Any]] = []
        commands: list[dict[str, Any]] = []
        commands.extend(
            self._load_manifest_file(
                self._pack_root / "commands" / "default_commands.json",
                MANIFEST_ORIGIN_DEFAULT,
                manifest_errors,
            )
        )
        commands.extend(self._load_manifest_dir(self._pack_root / "commands" / "manifests", MANIFEST_ORIGIN_PACK, manifest_errors))
        commands.extend(self._load_manifest_dir(self._pack_root / "user_data" / "shared" / "commands", MANIFEST_ORIGIN_USER, manifest_errors))
        normalized = [self._normalize(item) for item in commands if isinstance(item, dict)]
        return self._dedupe_by_id(normalized, manifest_errors), manifest_errors

    def _load_manifest_dir(self, path: Path, origin: str, manifest_errors: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not path.exists():
            return []
        items: list[dict[str, Any]] = []
        for file_path in sorted(path.glob("*.json")):
            items.extend(self._load_manifest_file(file_path, origin, manifest_errors))
        return items

    def _load_manifest_file(self, path: Path, origin: str, manifest_errors: list[dict[str, Any]]) -> list[dict[str, Any]]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            if path.exists():
                manifest_errors.append(self._manifest_issue("error", "command_manifest_invalid_json", str(exc), path))
            return []
        items: list[dict[str, Any]]
        if isinstance(payload, list):
            items = [item for item in payload if isinstance(item, dict)]
        elif isinstance(payload, dict):
            commands = payload.get("commands")
            if isinstance(commands, list):
                items = [item for item in commands if isinstance(item, dict)]
            else:
                items = [payload]
        else:
            manifest_errors.append(self._manifest_issue("error", "command_manifest_invalid_shape", "command manifest must be an object or list", path))
            return []
        tagged: list[dict[str, Any]] = []
        for item in items:
            tagged_item = deepcopy(item)
            tagged_item["_manifest_origin"] = origin
            tagged_item["_manifest_path"] = str(path)
            tagged.append(tagged_item)
        return tagged

    @staticmethod
    def _normalize(command: dict[str, Any]) -> dict[str, Any]:
        normalized = deepcopy(command)
        command_id = str(normalized.get("id") or normalized.get("name") or "").strip().lower().lstrip("/")
        normalized["id"] = command_id
        normalized["name"] = str(normalized.get("name") or command_id).strip().lower().lstrip("/")
        normalized["label"] = str(normalized.get("label") or normalized["name"])
        normalized["aliases"] = [
            str(alias).strip().lower().lstrip("/")
            for alias in normalized.get("aliases", [])
            if str(alias or "").strip()
        ]
        category = str(normalized.get("category") or "chat")
        normalized["category"] = category if category in CATEGORIES else "chat"
        visibility = str(normalized.get("visibility") or "default")
        normalized["visibility"] = visibility if visibility in VISIBILITIES else "default"
        risk = str(normalized.get("risk") or "low")
        normalized["risk"] = risk if risk in RISKS else "low"
        modes = normalized.get("modes")
        if not isinstance(modes, list) or not modes:
            normalized["modes"] = ["chat", "coding", "agent"]
        else:
            normalized["modes"] = [mode for mode in (str(item) for item in modes) if mode in MODES] or ["chat", "coding", "agent"]
        if not isinstance(normalized.get("args"), list):
            normalized["args"] = []
        if not isinstance(normalized.get("execution"), dict):
            normalized["execution"] = {"type": "frontend", "action": normalized["id"]}
        return normalized

    def _dedupe_by_id(self, commands: list[dict[str, Any]], manifest_errors: list[dict[str, Any]]) -> list[dict[str, Any]]:
        order: list[str] = []
        deduped: dict[str, dict[str, Any]] = {}
        token_owners: dict[str, dict[str, str]] = {}
        for command in commands:
            command_id = str(command.get("id") or "")
            if not command_id:
                continue
            existing = deduped.get(command_id)
            if existing is not None:
                manifest_errors.append(
                    self._manifest_issue(
                        "warning",
                        "command_duplicate_id",
                        f"command id '{command_id}' from {self._source_label(command)} overrides {self._source_label(existing)}",
                        command.get("_manifest_path"),
                    )
                )
            if command_id not in deduped:
                order.append(command_id)
            deduped[command_id] = command
            for token, kind in self._command_tokens(command).items():
                owner = token_owners.get(token)
                if owner is not None and owner["command_id"] != command_id:
                    manifest_errors.append(
                        self._manifest_issue(
                            "warning",
                            "command_alias_override",
                            f"{kind} '{token}' for command '{command_id}' overrides command '{owner['command_id']}'",
                            command.get("_manifest_path"),
                        )
                    )
                token_owners[token] = {"command_id": command_id, "source": self._source_label(command)}
        return [deduped[item] for item in order]

    @staticmethod
    def _coerce_args(command: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
        coerced = dict(args)
        for spec in command.get("args", []):
            if not isinstance(spec, dict):
                continue
            name = str(spec.get("name") or "")
            if not name:
                continue
            if spec.get("required") is True and (name not in coerced or SlashCommandRegistry._missing_arg_value(coerced.get(name))):
                return error(
                    f"{name} is required",
                    "MISSING_ARGUMENT",
                    details={"argument": name},
                )
            if name not in coerced:
                continue
            value = coerced[name]
            arg_type = spec.get("type")
            if arg_type == "boolean":
                boolean_value = SlashCommandRegistry._coerce_boolean(value)
                if boolean_value is None:
                    return error(
                        f"{name} must be a boolean",
                        "INVALID_ARGUMENT",
                        details={"argument": name},
                    )
                coerced[name] = boolean_value
            elif arg_type == "enum":
                values = [str(item) for item in spec.get("values", [])]
                if values and str(value) not in values:
                    return error(
                        f"{name} must be one of: {', '.join(values)}",
                        "INVALID_ARGUMENT",
                        details={"argument": name, "values": values},
                    )
            elif arg_type == "string":
                coerced[name] = str(value)
        return coerced

    @staticmethod
    def _coerce_boolean(value: Any) -> bool | None:
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)) and value in {0, 1}:
            return bool(value)
        normalized = str(value).strip().lower()
        if normalized in {"1", "true", "yes", "on", "enabled"}:
            return True
        if normalized in {"0", "false", "no", "off", "disabled"}:
            return False
        return None

    @staticmethod
    def _missing_arg_value(value: Any) -> bool:
        return value is None or (isinstance(value, str) and not value.strip())

    @staticmethod
    def _rumi_function_id(qualified_name: str) -> str:
        return str(qualified_name or "").strip().split(":", 1)[-1]

    @staticmethod
    def _command_tokens(command: dict[str, Any]) -> dict[str, str]:
        tokens: dict[str, str] = {}
        for key, kind in (("id", "id"), ("name", "name")):
            token = str(command.get(key) or "").strip().lower().lstrip("/")
            if token:
                tokens[token] = kind
        for alias in command.get("aliases") or []:
            token = str(alias or "").strip().lower().lstrip("/")
            if token:
                tokens[token] = "alias"
        return tokens

    @staticmethod
    def _public_command(command: dict[str, Any]) -> dict[str, Any]:
        return {key: deepcopy(value) for key, value in command.items() if not str(key).startswith("_manifest_")}

    @staticmethod
    def _source_label(command: dict[str, Any]) -> str:
        origin = str(command.get("_manifest_origin") or "unknown")
        path = str(command.get("_manifest_path") or "")
        return f"{origin} manifest {path}".strip()

    @staticmethod
    def _manifest_issue(level: str, code: str, message: str, source: Any) -> dict[str, Any]:
        return {
            "level": level,
            "code": code,
            "message": message,
            "source": str(source or ""),
        }
