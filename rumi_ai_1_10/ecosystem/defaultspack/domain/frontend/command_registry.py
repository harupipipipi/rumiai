from __future__ import annotations

import importlib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

CATEGORIES = {
    "chat",
    "model",
    "mode",
    "coding",
    "tools",
    "settings",
    "debug",
    "surface",
    "write",
    "image",
    "slide",
    "movie",
}
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
    "ai_get_deepthink_enabled",
    "ai_set_deepthink_enabled",
}

# pack_block execution type: lets a manifest-defined slash command dispatch to a
# pack-controlled Python block (modules under blocks/) that exposes a run(input,
# context) callable. Restricted to default/pack origins so user manifests can
# never load arbitrary modules.
PACK_BLOCK_ALLOWED_ORIGINS = (MANIFEST_ORIGIN_DEFAULT, MANIFEST_ORIGIN_PACK)
PACK_BLOCK_ALLOWED_MODULE_PREFIXES = ("blocks.",)
PACK_BLOCK_ALLOWED_PACK_IDS = {"defaultspack", "default"}
TEMPLATE_COMMAND_KEYS = ("commands", "slash_commands", "slashCommands")
TEMPLATE_ACTION_KEYS = ("actions",)
TEMPLATE_TRUST_BUILTIN = "builtin"


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

    def execute(
        self, payload: dict[str, Any], context: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        command = self.find_command(str(payload.get("command") or ""))
        if command is None:
            return error("command not found", "NOT_FOUND")

        mode = str(payload.get("mode") or "chat")
        if mode not in command.get("modes", []):
            return error(
                "command is not available in this mode",
                "COMMAND_UNAVAILABLE",
                details={"mode": mode},
            )

        args_result = self._coerce_args(
            command, payload.get("args") if isinstance(payload.get("args"), dict) else {}
        )
        if isinstance(args_result, dict) and args_result.get("status") == "error":
            return args_result
        args = args_result
        if command.get("risk") == "high":
            return ok(
                {
                    "command": self._public_command(command),
                    "executed": False,
                    "requires_approval": True,
                    "message": "This command requires approval center confirmation.",
                }
            )

        execution = command.get("execution") if isinstance(command.get("execution"), dict) else {}
        execution_type = str(execution.get("type") or "frontend")

        if execution_type == "frontend":
            return ok(
                {
                    "command": self._public_command(command),
                    "executed": False,
                    "action": execution.get("action"),
                    "args": args,
                    "effects": self._collect_effects(command, execution, args, payload, None),
                }
            )

        if execution_type == "model_command":
            return self._execute_model_command(command, execution, args)

        if execution_type == "rumi_function":
            return self._execute_rumi_function(command, execution, args, payload, context or {})

        if execution_type == "chat_action":
            return self._execute_chat_action(command, execution, args, payload, context or {})

        if execution_type == "pack_block":
            return self._execute_pack_block(command, execution, args, payload, context or {})

        return error(
            "unsupported command execution type",
            "INVALID_COMMAND",
            details={"type": execution_type},
        )

    def _execute_model_command(
        self,
        command: dict[str, Any],
        execution: dict[str, Any],
        args: dict[str, Any],
    ) -> dict[str, Any]:
        action = str(execution.get("action") or "")
        if action != "select_or_suggest_model":
            return error(
                "unsupported model command action", "INVALID_COMMAND", details={"action": action}
            )

        query = str(args.get("query") or "").strip()
        if not query:
            return ok(
                {
                    "command": self._public_command(command),
                    "executed": False,
                    "action": "open_model_picker",
                    "candidates": [],
                    "args": args,
                }
            )

        try:
            from domain.ai_client.model_runtime_settings import ModelRuntimeSettingsService

            service = ModelRuntimeSettingsService(self._pack_root)
            resolution = service.resolve_model_candidates(query)
            exact = resolution.get("exact") if isinstance(resolution, dict) else None
            candidates = resolution.get("candidates", []) if isinstance(resolution, dict) else []
            if isinstance(exact, dict) and exact.get("profile_id"):
                result = service.set_preferred_model(str(exact["profile_id"]))
                return ok(
                    {
                        "command": self._public_command(command),
                        "executed": True,
                        "result": result,
                        "selected_model": exact,
                        "args": args,
                    }
                )
            message = "No matching models found." if not candidates else "Choose a model candidate."
            return ok(
                {
                    "command": self._public_command(command),
                    "executed": False,
                    "action": "show_model_candidates",
                    "candidates": candidates,
                    "args": args,
                    "message": message,
                }
            )
        except Exception as exc:
            return error(str(exc), "EXECUTION_FAILED")

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
            return ok(
                {
                    "command": self._public_command(command),
                    "executed": False,
                    "action": action,
                    "args": args,
                }
            )

        conversation_id = str(payload.get("conversation_id") or "").strip()
        if conversation_id:
            from blocks.chat.compact import run as chat_compact_run

            compact_input = dict(args)
            compact_input["conversation_id"] = conversation_id
            result = chat_compact_run(compact_input, context)
            if isinstance(result, dict) and result.get("status") == "ok":
                return ok(
                    {
                        "command": self._public_command(command),
                        "executed": True,
                        "result": result.get("data"),
                    }
                )
            return (
                result
                if isinstance(result, dict)
                else error("compact command failed", "EXECUTION_FAILED")
            )

        from blocks.context.compact import run as compact_run

        result = compact_run(
            {
                "goal": str(args.get("instruction") or "Compact current conversation"),
                "messages": payload.get("messages", []),
                "summary": args.get("instruction"),
            },
            context,
        )
        if isinstance(result, dict) and result.get("status") == "ok":
            return ok(
                {
                    "command": self._public_command(command),
                    "executed": True,
                    "result": result.get("data"),
                }
            )
        return (
            result
            if isinstance(result, dict)
            else error("compact command failed", "EXECUTION_FAILED")
        )

    def _execute_pack_block(
        self,
        command: dict[str, Any],
        execution: dict[str, Any],
        args: dict[str, Any],
        payload: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Dispatch the slash command to a pack-controlled block module.

        Manifests provide ``execution.qualified_name`` as ``"<pack_id>:<dotted.path>"``;
        the dotted path is resolved relative to ``blocks.`` (or accepted as-is when
        already starting with ``blocks.``). The target module must expose a callable
        ``run(input, context)`` that returns ``{"status": "ok", "data": ...}`` or
        ``{"status": "error", ...}``.

        Restricted to default and pack origins (never user origin) and to modules
        under ``blocks.`` so user manifests can never load arbitrary modules.
        """
        origin = command.get("_manifest_origin")
        if origin not in PACK_BLOCK_ALLOWED_ORIGINS:
            return error(
                "pack_block execution is only allowed for default and pack manifests",
                "INVALID_COMMAND",
            )
        qualified_name = str(execution.get("qualified_name") or "").strip()
        if not qualified_name or ":" not in qualified_name:
            return error(
                "pack_block command requires qualified_name '<pack_id>:<module.path>'",
                "INVALID_COMMAND",
            )
        _pack_id, _, module_id = qualified_name.partition(":")
        pack_id = _pack_id.strip()
        if pack_id not in PACK_BLOCK_ALLOWED_PACK_IDS:
            return error("pack_block pack_id is not allowed for this registry", "INVALID_COMMAND")
        module_id = module_id.strip().lstrip(".")
        if not module_id:
            return error(
                "pack_block command requires a module path after the pack prefix",
                "INVALID_COMMAND",
            )
        if module_id.startswith("blocks."):
            module_path = module_id
        else:
            module_path = "blocks." + module_id
        if not any(module_path.startswith(prefix) for prefix in PACK_BLOCK_ALLOWED_MODULE_PREFIXES):
            return error(
                "pack_block target module is not on the allowlist of module roots",
                "INVALID_COMMAND",
            )
        try:
            module = importlib.import_module(module_path)
        except Exception as exc:
            return error(f"pack_block target failed to import: {exc}", "EXECUTION_FAILED")
        module_file = getattr(module, "__file__", None)
        if not module_file:
            return error("pack_block target escaped pack blocks root", "INVALID_COMMAND")
        allowed_root = (self._pack_root / "blocks").resolve()
        try:
            Path(module_file).resolve().relative_to(allowed_root)
        except ValueError:
            return error("pack_block target escaped pack blocks root", "INVALID_COMMAND")
        runner = getattr(module, "run", None)
        if not callable(runner):
            return error(
                "pack_block target does not expose a callable run(input, context)",
                "INVALID_COMMAND",
            )

        block_input: dict[str, Any] = dict(args)
        for forwarded in ("conversation_id", "mode"):
            value = payload.get(forwarded)
            if value not in (None, "") and forwarded not in block_input:
                block_input[forwarded] = value

        try:
            result = runner(block_input, dict(context or {}))
        except Exception as exc:
            return error(f"pack_block execution failed: {exc}", "EXECUTION_FAILED")
        if isinstance(result, dict) and result.get("status") == "ok":
            data = result.get("data")
            payload = {
                "command": self._public_command(command),
                "executed": True,
                "result": data,
            }
            if isinstance(data, dict) and str(data.get("message") or "").strip():
                payload["message"] = str(data.get("message") or "")
            return ok(payload)
        if isinstance(result, dict):
            return result
        return error("pack_block returned an unexpected response", "EXECUTION_FAILED")

    def _execute_rumi_function(
        self,
        command: dict[str, Any],
        execution: dict[str, Any],
        args: dict[str, Any],
        payload: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        origin = str(command.get("_manifest_origin") or "")
        if origin == MANIFEST_ORIGIN_USER:
            return error("rumi_function execution is not allowed for user commands", "INVALID_COMMAND")

        resolved = self._resolve_rumi_function_target(command, execution)
        if resolved.get("status") == "error":
            return resolved
        source_pack_id = str(resolved["source_pack_id"])
        execution_pack_id = str(resolved["pack_id"])
        function_id = str(resolved["function_id"])
        qualified_name = f"{execution_pack_id}:{function_id}"

        function_args = self._apply_context_bindings(command, args, payload, context)
        if payload.get("conversation_id"):
            function_args.setdefault("conversation_id", payload.get("conversation_id"))

        try:
            from domain.function_runtime.bridge import (
                ensure_pack_functions_registered,
                invoke_function,
            )

            source_pack_root = command.get("_manifest_pack_root")
            if isinstance(source_pack_root, Path) and source_pack_id == execution_pack_id:
                ensure_pack_functions_registered(execution_pack_id, source_pack_root)
            result = invoke_function(
                qualified_name,
                function_args,
                context,
                principal_id=source_pack_id or "defaultspack",
                function_pack_root=source_pack_root if isinstance(source_pack_root, Path) else None,
            )
        except Exception as exc:
            return error(f"rumi_function execution failed: {exc}", "EXECUTION_FAILED")

        if self._should_use_builtin_rumi_function_fallback(result):
            builtin_result = self._execute_builtin_rumi_function(qualified_name, function_args)
            if builtin_result is not None:
                return self._rumi_function_response(
                    command, execution, args, payload, builtin_result
                )

        return self._rumi_function_response(command, execution, args, payload, result)

    def _rumi_function_response(
        self,
        command: dict[str, Any],
        execution: dict[str, Any],
        args: dict[str, Any],
        payload: dict[str, Any],
        result: Any,
    ) -> dict[str, Any]:
        if isinstance(result, dict) and result.get("status") == "error":
            return result
        result_data = result.get("data") if isinstance(result, dict) and result.get("status") == "ok" else result
        response_payload = {
            "command": self._public_command(command),
            "executed": True,
            "result": result_data,
            "effects": self._collect_effects(command, execution, args, payload, result_data),
        }
        if isinstance(result_data, dict) and str(result_data.get("message") or "").strip():
            response_payload["message"] = str(result_data.get("message") or "")
        return ok(response_payload)

    @staticmethod
    def _should_use_builtin_rumi_function_fallback(result: Any) -> bool:
        if not isinstance(result, dict) or result.get("status") != "error":
            return False
        err = result.get("error")
        code = str(err.get("code") if isinstance(err, dict) else "").strip().upper()
        return code == "FUNCTION_NOT_FOUND"

    def _resolve_rumi_function_target(
        self, command: dict[str, Any], execution: dict[str, Any]
    ) -> dict[str, Any]:
        source_pack_id = str(command.get("source_pack_id") or command.get("_manifest_source_pack_id") or "").strip()
        if not source_pack_id and command.get("_manifest_origin") in {
            MANIFEST_ORIGIN_DEFAULT,
            MANIFEST_ORIGIN_PACK,
        }:
            source_pack_id = "defaultspack"

        execution_pack_id = str(execution.get("pack_id") or "").strip()
        function_id = str(execution.get("function_id") or "").strip()
        qualified_name = str(execution.get("qualified_name") or "").strip()
        if qualified_name:
            parsed_pack_id, parsed_function_id = self._parse_qualified_function_name(qualified_name)
            execution_pack_id = execution_pack_id or parsed_pack_id
            function_id = function_id or parsed_function_id
        if not execution_pack_id:
            execution_pack_id = source_pack_id
        if not execution_pack_id or not function_id:
            return error("rumi_function command requires pack_id and function_id", "INVALID_COMMAND")

        aliases = {"default": "defaultspack", "defaults": "defaultspack"}
        source_pack_id = aliases.get(source_pack_id, source_pack_id)
        execution_pack_id = aliases.get(execution_pack_id, execution_pack_id)
        if source_pack_id != execution_pack_id:
            return error(
                "cross-pack rumi_function command execution is not allowed",
                "INVALID_COMMAND",
                details={"source_pack_id": source_pack_id, "execution_pack_id": execution_pack_id},
            )
        return {
            "status": "ok",
            "source_pack_id": source_pack_id,
            "pack_id": execution_pack_id,
            "function_id": function_id,
        }

    def _execute_builtin_rumi_function(
        self, qualified_name: str, args: dict[str, Any]
    ) -> dict[str, Any] | None:
        function_id = self._rumi_function_id(qualified_name)
        if function_id not in ALLOWED_RUMI_FUNCTIONS:
            return None

        try:
            from domain.ai_client.model_runtime_settings import ModelRuntimeSettingsService

            service = ModelRuntimeSettingsService(self._pack_root)
            if function_id == "ai_get_preferred_model":
                return {"profile_id": service.get_preferred_model()}
            if function_id == "ai_set_preferred_model":
                return service.set_preferred_model(
                    str(args.get("profile_id") or args.get("model") or "")
                )
            if function_id == "ai_get_thinking_level":
                return service.get_thinking_level(
                    args.get("scope", "global"), args.get("profile_id"), args.get("conversation_id")
                )
            if function_id == "ai_set_thinking_level":
                return service.set_thinking_level(
                    str(args.get("level") or ""),
                    args.get("scope", "global"),
                    args.get("profile_id"),
                    args.get("conversation_id"),
                )
            if function_id == "ai_get_effective_thinking_level":
                return service.get_effective_thinking_level(
                    args.get("profile_id"), args.get("conversation_id")
                )
            if function_id == "ai_normalize_thinking_level":
                return service.normalize_for_provider(
                    str(args.get("provider_id") or ""),
                    str(args.get("model_id") or args.get("model") or ""),
                    str(args.get("level") or args.get("thinking_level") or ""),
                )
            if function_id == "ai_get_deepthink_enabled":
                return service.get_deepthink_enabled()
            if function_id == "ai_set_deepthink_enabled":
                enabled = args.get("enabled")
                return service.set_deepthink_enabled(enabled if isinstance(enabled, bool) else None)
        except Exception as exc:
            return error(str(exc), "EXECUTION_FAILED")
        return None

    def _commands_with_errors(self) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        manifest_errors: list[dict[str, Any]] = []
        commands: list[dict[str, Any]] = []
        template_commands = self._load_template_catalog_commands(manifest_errors)
        commands.extend(
            self._load_manifest_file(
                self._pack_root / "commands" / "default_commands.json",
                MANIFEST_ORIGIN_DEFAULT,
                manifest_errors,
            )
        )
        commands.extend(template_commands[MANIFEST_ORIGIN_DEFAULT])
        commands.extend(
            self._load_manifest_dir(
                self._pack_root / "commands" / "manifests", MANIFEST_ORIGIN_PACK, manifest_errors
            )
        )
        commands.extend(self._load_extension_command_manifests(manifest_errors))
        commands.extend(
            self._load_manifest_dir(
                self._pack_root / "user_data" / "shared" / "commands",
                MANIFEST_ORIGIN_USER,
                manifest_errors,
            )
        )
        commands.extend(template_commands[MANIFEST_ORIGIN_USER])
        normalized = [self._normalize(item) for item in commands if isinstance(item, dict)]
        return self._dedupe_by_id(normalized, manifest_errors), manifest_errors

    def _load_template_catalog_commands(
        self, manifest_errors: list[dict[str, Any]]
    ) -> dict[str, list[dict[str, Any]]]:
        buckets: dict[str, list[dict[str, Any]]] = {
            MANIFEST_ORIGIN_DEFAULT: [],
            MANIFEST_ORIGIN_USER: [],
        }
        if not self._has_template_roots():
            return buckets

        try:
            projectors = importlib.import_module("domain.templates.projectors")
        except ModuleNotFoundError:
            return buckets
        except Exception as exc:
            manifest_errors.append(
                self._manifest_issue(
                    "warning",
                    "template_command_projection_failed",
                    f"failed to import template projectors: {exc}",
                    "domain.templates.projectors",
                )
            )
            return buckets

        build_template_catalog = getattr(projectors, "build_template_catalog", None)
        if not callable(build_template_catalog):
            return buckets

        try:
            catalog = build_template_catalog(defaultspack_root=self._pack_root)
        except Exception as exc:
            manifest_errors.append(
                self._manifest_issue(
                    "warning",
                    "template_command_projection_failed",
                    f"failed to project template commands: {exc}",
                    self._pack_root / "templates",
                )
            )
            return buckets
        if not isinstance(catalog, dict):
            return buckets

        templates_by_id = self._template_summaries_by_id(catalog)
        for command_item, projection in self._iter_template_command_items(catalog):
            command = self._template_command_from_projection(
                command_item, projection, templates_by_id
            )
            if command is None:
                continue
            origin = str(command.get("_manifest_origin") or MANIFEST_ORIGIN_USER)
            if origin == MANIFEST_ORIGIN_DEFAULT:
                buckets[MANIFEST_ORIGIN_DEFAULT].append(command)
            else:
                buckets[MANIFEST_ORIGIN_USER].append(command)
        return buckets

    def _has_template_roots(self) -> bool:
        return any(
            path.exists()
            for path in (
                self._pack_root / "templates",
                self._pack_root / "user_data" / "shared" / "templates",
            )
        )

    @classmethod
    def _iter_template_command_items(
        cls, catalog: dict[str, Any]
    ) -> list[tuple[dict[str, Any], dict[str, Any]]]:
        items: list[tuple[dict[str, Any], dict[str, Any]]] = []
        for key in TEMPLATE_COMMAND_KEYS:
            values = catalog.get(key)
            if isinstance(values, list):
                for item in values:
                    items.extend(cls._extract_template_command_items(item, require_marker=False))
        for key in TEMPLATE_ACTION_KEYS:
            values = catalog.get(key)
            if isinstance(values, list):
                for item in values:
                    items.extend(cls._extract_template_command_items(item, require_marker=True))
        return items

    @classmethod
    def _extract_template_command_items(
        cls,
        item: Any,
        *,
        require_marker: bool,
    ) -> list[tuple[dict[str, Any], dict[str, Any]]]:
        if not isinstance(item, dict):
            return []

        extracted: list[tuple[dict[str, Any], dict[str, Any]]] = []
        for key in TEMPLATE_COMMAND_KEYS:
            nested_list = item.get(key)
            if not isinstance(nested_list, list):
                continue
            for nested in nested_list:
                if isinstance(nested, dict):
                    extracted.append((nested, item))

        for key in ("slash_command", "command"):
            nested = item.get(key)
            if isinstance(nested, dict):
                extracted.append((nested, item))
            elif nested is True:
                extracted.append((item, item))

        if extracted:
            return extracted
        if require_marker and not cls._looks_like_template_command(item):
            return []
        if not require_marker or cls._looks_like_template_command(item):
            return [(item, item)]
        return []

    @staticmethod
    def _looks_like_template_command(item: dict[str, Any]) -> bool:
        if not any(str(item.get(key) or "").strip() for key in ("id", "name", "command_id")):
            return False
        return isinstance(item.get("execution"), dict)

    @staticmethod
    def _template_summaries_by_id(catalog: dict[str, Any]) -> dict[str, dict[str, Any]]:
        summaries: dict[str, dict[str, Any]] = {}
        templates = catalog.get("templates")
        if not isinstance(templates, list):
            return summaries
        for item in templates:
            if not isinstance(item, dict):
                continue
            template_id = str(item.get("id") or "").strip()
            if template_id:
                summaries[template_id] = item
        return summaries

    @classmethod
    def _template_command_from_projection(
        cls,
        command_item: dict[str, Any],
        projection: dict[str, Any],
        templates_by_id: dict[str, dict[str, Any]],
    ) -> dict[str, Any] | None:
        command = deepcopy(command_item)
        command_id = str(
            command.get("id") or command.get("command_id") or command.get("name") or ""
        ).strip()
        if not command_id:
            return None
        command.setdefault("id", command_id)
        command.setdefault("name", command.get("command_id") or command_id)
        for key in (
            "label",
            "description",
            "category",
            "visibility",
            "risk",
            "modes",
            "args",
            "execution",
            "override",
        ):
            if key not in command and key in projection:
                command[key] = deepcopy(projection[key])

        template_id = str(projection.get("template_id") or "").strip()
        piece_id = str(projection.get("piece_id") or "").strip()
        origin = projection.get("origin") if isinstance(projection.get("origin"), dict) else {}
        source = str(
            projection.get("source_path") or projection.get("_source") or origin.get("path") or ""
        ).strip()
        template_summary = templates_by_id.get(template_id, {})
        trust_level = str(
            projection.get("trust_level") or template_summary.get("trust_level") or ""
        ).strip()

        command["template_id"] = template_id
        command["piece_id"] = piece_id
        command["source_path"] = source
        command["trust_level"] = trust_level
        command["_manifest_origin"] = cls._manifest_origin_for_template_trust(trust_level)
        command["_manifest_path"] = cls._template_source_label(template_id, piece_id, source)
        command["_template_id"] = template_id
        command["_template_piece_id"] = piece_id
        command["_template_source"] = source
        command["_template_trust_level"] = trust_level
        command["_public_id"] = command_id
        return command

    @staticmethod
    def _manifest_origin_for_template_trust(trust_level: str) -> str:
        if str(trust_level or "").strip().lower() == TEMPLATE_TRUST_BUILTIN:
            return MANIFEST_ORIGIN_DEFAULT
        return MANIFEST_ORIGIN_USER

    @staticmethod
    def _template_source_label(template_id: str, piece_id: str, source: str) -> str:
        details = []
        if template_id:
            details.append(f"template_id={template_id}")
        if piece_id:
            details.append(f"piece_id={piece_id}")
        if source:
            details.append(f"source={source}")
        return "template command " + " ".join(details) if details else "template command"

    def _load_manifest_dir(
        self, path: Path, origin: str, manifest_errors: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        if not path.exists():
            return []
        items: list[dict[str, Any]] = []
        for file_path in sorted(path.glob("*.json")):
            items.extend(self._load_manifest_file(file_path, origin, manifest_errors))
        return items

    def _load_manifest_file(
        self,
        path: Path,
        origin: str,
        manifest_errors: list[dict[str, Any]],
        *,
        extra_fields: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            if path.exists():
                manifest_errors.append(
                    self._manifest_issue("error", "command_manifest_invalid_json", str(exc), path)
                )
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
            manifest_errors.append(
                self._manifest_issue(
                    "error",
                    "command_manifest_invalid_shape",
                    "command manifest must be an object or list",
                    path,
                )
            )
            return []
        tagged: list[dict[str, Any]] = []
        for item in items:
            tagged_item = deepcopy(item)
            tagged_item["_manifest_origin"] = origin
            tagged_item["_manifest_path"] = str(path)
            for key, value in (extra_fields or {}).items():
                tagged_item[key] = value
            tagged.append(tagged_item)
        return tagged

    def _load_extension_command_manifests(
        self, manifest_errors: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for extensions_root in self._extension_roots():
            commands_root = extensions_root / "commands"
            if not commands_root.is_dir():
                continue
            source_pack_root = self._source_pack_root_for_extension_root(extensions_root)
            source_pack_id = self._pack_id_for_pack_root(source_pack_root)
            for manifest_path in sorted(commands_root.glob("*/manifest.json")):
                items.extend(
                    self._load_manifest_file(
                        manifest_path,
                        MANIFEST_ORIGIN_PACK,
                        manifest_errors,
                        extra_fields={
                            "source_pack_id": source_pack_id,
                            "source_path": str(manifest_path),
                            "trust_level": "activated_pack",
                            "_manifest_source_pack_id": source_pack_id,
                            "_manifest_pack_root": source_pack_root,
                        },
                    )
                )
        return items

    def _extension_roots(self) -> list[Path]:
        try:
            from domain.extensions.runtime import (
                _extra_extension_roots_from_env,
                build_extensions_roots,
                get_extensions_roots,
            )

            default_pack_root = Path(__file__).resolve().parents[2]
            if self._pack_root.resolve() == default_pack_root.resolve():
                roots = get_extensions_roots()
            else:
                roots = build_extensions_roots(
                    self._pack_root,
                    extra_roots=_extra_extension_roots_from_env(),
                )
        except Exception:
            roots = [self._pack_root / "extensions"]
        return [Path(root) for root in roots if Path(root).is_dir()]

    @staticmethod
    def _normalize(command: dict[str, Any]) -> dict[str, Any]:
        normalized = deepcopy(command)
        command_id = (
            str(normalized.get("id") or normalized.get("name") or "").strip().lower().lstrip("/")
        )
        normalized["id"] = command_id
        normalized["name"] = str(normalized.get("name") or command_id).strip().lower().lstrip("/")
        normalized["_public_id"] = command_id
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
            normalized["modes"] = [
                mode for mode in (str(item) for item in modes) if mode in MODES
            ] or ["chat", "coding", "agent"]
        if not isinstance(normalized.get("args"), list):
            normalized["args"] = []
        if not isinstance(normalized.get("execution"), dict):
            normalized["execution"] = {"type": "frontend", "action": normalized["id"]}
        origin = str(normalized.get("_manifest_origin") or "")
        if not str(normalized.get("source_pack_id") or "").strip():
            if origin in {MANIFEST_ORIGIN_DEFAULT, MANIFEST_ORIGIN_PACK}:
                normalized["source_pack_id"] = "defaultspack"
            elif origin == MANIFEST_ORIGIN_USER:
                normalized["source_pack_id"] = "user_data"
        if not str(normalized.get("source_path") or "").strip() and normalized.get("_manifest_path"):
            normalized["source_path"] = str(normalized.get("_manifest_path") or "")
        if not str(normalized.get("trust_level") or "").strip():
            if origin == MANIFEST_ORIGIN_DEFAULT:
                normalized["trust_level"] = "builtin"
            elif origin == MANIFEST_ORIGIN_PACK:
                normalized["trust_level"] = "pack"
            elif origin == MANIFEST_ORIGIN_USER:
                normalized["trust_level"] = "user"
        return normalized

    def _dedupe_by_id(
        self, commands: list[dict[str, Any]], manifest_errors: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        order: list[str] = []
        deduped: dict[str, dict[str, Any]] = {}
        token_owners: dict[str, dict[str, str]] = {}
        for command in commands:
            command_id = str(command.get("id") or "")
            if not command_id:
                continue
            existing = deduped.get(command_id)
            if existing is not None:
                if self._command_override_allows(command, existing):
                    manifest_errors.append(
                        self._manifest_issue(
                            "info",
                            "command_explicit_override",
                            f"command id '{command_id}' from {self._source_label(command)} explicitly replaces {self._source_label(existing)}",
                            command.get("_manifest_path"),
                        )
                    )
                    deduped[command_id] = command
                    continue
                manifest_errors.append(
                    self._manifest_issue(
                        "error",
                        "command_duplicate_id",
                        f"command id '{command_id}' from {self._source_label(command)} collides with {self._source_label(existing)}; keeping the first definition",
                        command.get("_manifest_path"),
                    )
                )
                continue
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
                            f"{kind} '{token}' for command '{command_id}' from {self._source_label(command)} overrides command '{owner['command_id']}' from {owner['source']}",
                            command.get("_manifest_path"),
                        )
                    )
                token_owners[token] = {
                    "command_id": command_id,
                    "source": self._source_label(command),
                }
        return [deduped[item] for item in order]

    @staticmethod
    def _command_override_allows(command: dict[str, Any], existing: dict[str, Any]) -> bool:
        override = command.get("override")
        if not isinstance(override, dict):
            return False
        if str(override.get("mode") or "").strip() != "replace":
            return False
        target_public_id = str(override.get("target_public_id") or "").strip().lower().lstrip("/")
        if target_public_id and target_public_id != str(existing.get("id") or "").strip():
            return False
        target_projected_id = str(override.get("target_projected_id") or "").strip()
        existing_projected_id = str(
            existing.get("projected_id") or existing.get("_template_piece_id") or ""
        ).strip()
        if target_projected_id and target_projected_id != existing_projected_id:
            return False
        if command.get("_manifest_origin") != MANIFEST_ORIGIN_DEFAULT:
            return False
        if existing.get("_manifest_origin") not in {MANIFEST_ORIGIN_DEFAULT, None}:
            return False
        return bool(target_public_id or target_projected_id)

    @staticmethod
    def _coerce_args(command: dict[str, Any], args: dict[str, Any]) -> dict[str, Any]:
        coerced = dict(args)
        for spec in command.get("args", []):
            if not isinstance(spec, dict):
                continue
            name = str(spec.get("name") or "")
            if not name:
                continue
            if spec.get("required") is True and (
                name not in coerced or SlashCommandRegistry._missing_arg_value(coerced.get(name))
            ):
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
    def _parse_qualified_function_name(qualified_name: str) -> tuple[str, str]:
        value = str(qualified_name or "").strip()
        if ":" in value:
            pack_id, _, function_id = value.partition(":")
            return pack_id.strip(), function_id.strip()
        if "." in value:
            pack_id, _, function_id = value.partition(".")
            return pack_id.strip(), function_id.strip()
        return "", value

    def _apply_context_bindings(
        self,
        command: dict[str, Any],
        args: dict[str, Any],
        payload: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        bound = dict(args)
        bindings = command.get("context_bindings")
        if isinstance(bindings, dict):
            binding_names = [str(key) for key, enabled in bindings.items() if enabled]
        elif isinstance(bindings, list):
            binding_names = [str(item) for item in bindings if str(item or "").strip()]
        else:
            binding_names = []
        for name in binding_names:
            if name in bound:
                continue
            value = self._context_binding_value(name, payload, context)
            if value not in (None, ""):
                bound[name] = value
        return bound

    @staticmethod
    def _context_binding_value(
        name: str, payload: dict[str, Any], context: dict[str, Any]
    ) -> Any:
        if name in payload:
            return payload.get(name)
        if name in context:
            return context.get(name)
        if name == "conversation_id":
            return payload.get("conversation_id") or context.get("conversation_id")
        if name == "workspace_id":
            return payload.get("workspace_id") or context.get("workspace_id")
        if name == "surface_id":
            return payload.get("surface_id") or context.get("surface_id")
        if name == "selection":
            return payload.get("selection") or context.get("selection")
        if name == "attached_files":
            return payload.get("attached_files") or context.get("attached_files")
        if name == "chat_json_url":
            conversation_id = str(payload.get("conversation_id") or context.get("conversation_id") or "").strip()
            return f"/api/chat/conversations/{conversation_id}/export?format=json" if conversation_id else ""
        return None

    def _collect_effects(
        self,
        command: dict[str, Any],
        execution: dict[str, Any],
        args: dict[str, Any],
        payload: dict[str, Any],
        result_data: Any,
    ) -> list[dict[str, Any]]:
        effects: list[dict[str, Any]] = []
        values = self._effect_template_values(command, args, payload, result_data)
        for source in (execution.get("effects"), command.get("effects")):
            if isinstance(source, list):
                for effect in source:
                    if isinstance(effect, dict):
                        materialized = self._materialize_effect_value(effect, values)
                        if (
                            isinstance(materialized, dict)
                            and str(materialized.get("type") or "").strip()
                        ):
                            effects.append(materialized)
        if isinstance(result_data, dict) and isinstance(result_data.get("effects"), list):
            for effect in result_data.get("effects") or []:
                if isinstance(effect, dict) and str(effect.get("type") or "").strip():
                    effects.append(effect)
        return effects

    @staticmethod
    def _effect_template_values(
        command: dict[str, Any],
        args: dict[str, Any],
        payload: dict[str, Any],
        result_data: Any,
    ) -> dict[str, Any]:
        values: dict[str, Any] = {}
        values.update({f"arg.{key}": value for key, value in args.items()})
        values.update({key: value for key, value in payload.items() if isinstance(key, str)})
        values.setdefault("command_id", command.get("id"))
        values.setdefault("source_pack_id", command.get("source_pack_id"))
        if isinstance(result_data, dict):
            values.update(result_data)
            for key, value in result_data.items():
                values[f"result.{key}"] = value
        return values

    @classmethod
    def _materialize_effect_value(cls, value: Any, values: dict[str, Any]) -> Any:
        if isinstance(value, dict):
            return {key: cls._materialize_effect_value(item, values) for key, item in value.items()}
        if isinstance(value, list):
            return [cls._materialize_effect_value(item, values) for item in value]
        if isinstance(value, str):
            result = value
            for key, replacement in values.items():
                if isinstance(replacement, (str, int, float, bool)):
                    result = result.replace("{" + str(key) + "}", str(replacement))
            return result
        return value

    @staticmethod
    def _rumi_function_id(qualified_name: str) -> str:
        return str(qualified_name or "").strip().split(":", 1)[-1]

    @staticmethod
    def _source_pack_root_for_extension_root(extensions_root: Path) -> Path:
        root = Path(extensions_root)
        if root.name == "extensions":
            return root.parent
        return root

    @staticmethod
    def _pack_id_for_pack_root(pack_root: Path) -> str:
        for manifest_name in ("ecosystem.json", "rumi-pack.json"):
            manifest_path = Path(pack_root) / manifest_name
            if not manifest_path.is_file():
                continue
            try:
                raw = json.loads(manifest_path.read_text(encoding="utf-8"))
            except Exception:
                continue
            if not isinstance(raw, dict):
                continue
            for key in ("pack_id", "id"):
                value = str(raw.get(key) or "").strip()
                if value:
                    return value
        if Path(pack_root).name == "defaultspack":
            return "defaultspack"
        return Path(pack_root).name

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
        return {
            key: deepcopy(value)
            for key, value in command.items()
            if not str(key).startswith("_")
        }

    @staticmethod
    def _source_label(command: dict[str, Any]) -> str:
        template_id = str(command.get("_template_id") or "").strip()
        if template_id:
            piece_id = str(command.get("_template_piece_id") or "").strip()
            trust_level = str(command.get("_template_trust_level") or "unknown").strip()
            source = str(command.get("_template_source") or "").strip()
            piece = f"/{piece_id}" if piece_id else ""
            suffix = f" {source}" if source else ""
            return f"{trust_level} template {template_id}{piece}{suffix}".strip()
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
