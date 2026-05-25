from .registry import ToolRegistry
from .mcp_client import McpClient
from .mcp_registry import McpRegistry
from .eligibility import rejection_result
from .schema_adapter import is_tool_rejected_by_policy, policy_from_context
from .security import is_trusted_pack_id, requires_approval_for_security, unsupported_execution_reason
from domain.tool_policy.internal_context import internal_tool_decision_allows
from pathlib import Path
import json


# P1-2: サンドボックス用の安全なビルトイン一覧
_SAFE_BUILTINS = {
    "None": None,
    "True": True,
    "False": False,
    "abs": abs,
    "all": all,
    "any": any,
    "bool": bool,
    "bytes": bytes,
    "callable": callable,
    "chr": chr,
    "dict": dict,
    "divmod": divmod,
    "enumerate": enumerate,
    "filter": filter,
    "float": float,
    "format": format,
    "frozenset": frozenset,
    "getattr": getattr,
    "hasattr": hasattr,
    "hash": hash,
    "hex": hex,
    "id": id,
    "int": int,
    "isinstance": isinstance,
    "issubclass": issubclass,
    "iter": iter,
    "len": len,
    "list": list,
    "map": map,
    "max": max,
    "min": min,
    "next": next,
    "oct": oct,
    "ord": ord,
    "pow": pow,
    "print": print,
    "range": range,
    "repr": repr,
    "reversed": reversed,
    "round": round,
    "set": set,
    "slice": slice,
    "sorted": sorted,
    "str": str,
    "sum": sum,
    "tuple": tuple,
    "type": type,
    "zip": zip,
    # 明示的に除外: __import__, exec, eval, compile, open, globals, locals,
    #               breakpoint, exit, quit, input, memoryview, vars, dir,
    #               delattr, setattr, super, classmethod, staticmethod,
    #               property, object, __build_class__
}


def json_dumps(value):
    return json.dumps(value, ensure_ascii=False)


def _approval_module():
    from domain.safety import approval

    return approval


class ToolExecutor:
    """ツール実行エンジン"""

    def __init__(self):
        try:
            from domain.integrations.secrets import load_integration_secrets_into_env

            load_integration_secrets_into_env()
        except Exception:
            pass
        self._registry = ToolRegistry()
        self._mcp_client = McpClient()

    def execute(self, tool_name, arguments, context):
        """
        ツールを実行する。
        戻り値: {"result": str, "is_error": bool, "widget": dict|None}
        """
        if _is_cancelled(context):
            return _cancelled_tool_result(tool_name)
        filtered_rejection = _filtered_tool_rejection(tool_name, context)
        if filtered_rejection is not None:
            return {
                "result": "Tool '{}' was rejected: {}".format(tool_name, filtered_rejection.get("reason") or filtered_rejection.get("code")),
                "is_error": True,
                "widget": {"type": "tool_rejection", **filtered_rejection},
                **filtered_rejection,
            }
        tool_def = self._registry.get(tool_name)
        if tool_def is None:
            return {
                "result": "Tool '{}' not found".format(tool_name),
                "is_error": True,
                "widget": None
            }
        policy = policy_from_context(context if isinstance(context, dict) else {})
        if is_tool_rejected_by_policy(tool_def, policy):
            return {
                "result": "Tool '{}' rejected by runtime policy".format(tool_name),
                "is_error": True,
                "widget": None,
                "rejected_by_policy": True,
            }
        security_rejection = unsupported_execution_reason(tool_def)
        if security_rejection is not None:
            return {
                "result": "Tool '{}' rejected by tool security policy: {}".format(
                    tool_name,
                    security_rejection,
                ),
                "is_error": True,
                "widget": None,
                "rejected_by_security": True,
            }

        execution = tool_def.get("execution", {})
        exec_type = execution.get("type", "local")

        if exec_type == "mcp":
            server_name = execution.get("server_name", "")
            mcp_tool_name = execution.get("mcp_tool_name", tool_name)
            if not McpRegistry().is_approved(server_name):
                return {
                    "result": "MCP server '{}' is not approved for tool execution".format(server_name),
                    "is_error": True,
                    "widget": None,
                    "approval_required": True,
                }
            try:
                from domain.safety.audit import record_execution

                record_execution(
                    "tool.mcp_call",
                    "medium",
                    {"server_name": server_name, "tool_name": mcp_tool_name},
                )
            except Exception:
                pass
            return self._mcp_client.invoke(server_name, mcp_tool_name, arguments)

        if exec_type == "rumi_function":
            return self._execute_rumi_function(tool_def, arguments, context)

        if exec_type == "capability":
            return self._execute_capability(tool_def, arguments, context)

        if exec_type == "dynamic":
            return self._execute_dynamic(tool_def, arguments, context)

        handler = str(execution.get("handler") or "")
        if handler and not handler.endswith(":ToolExecutor.execute"):
            return self._execute_handler(tool_def, arguments, context)

        return self._execute_local(tool_name, arguments, context)

    def _execute_rumi_function(self, tool_def, arguments, context):
        execution = tool_def.get("execution", {}) if isinstance(tool_def, dict) else {}
        qualified_name = str(execution.get("qualified_name") or "").strip()
        if not qualified_name:
            return {
                "result": "Tool '{}' has no rumi_function qualified_name".format(
                    tool_def.get("name", tool_def.get("tool_id", "tool"))
                ),
                "is_error": True,
                "widget": None,
            }
        pack_id, _, function_id = qualified_name.partition(":")
        request = {
            "type": "function.call",
            "qualified_name": qualified_name,
            "args": arguments or {},
        }
        if isinstance(context, dict) and context.get("request_id"):
            request["request_id"] = context.get("request_id")
        approved_context, approval_error = _context_with_tool_approval_token(context, tool_def, arguments)
        if approval_error is not None:
            return approval_error
        forwarded_context = _function_call_context(approved_context, tool_def)
        if forwarded_context:
            request["context"] = forwarded_context
        self._ensure_shared_function_registered(qualified_name)
        return self._execute_capability_request(tool_def, request, approved_context)

    def _execute_capability(self, tool_def, arguments, context):
        execution = tool_def.get("execution", {}) if isinstance(tool_def, dict) else {}
        permission_id = str(execution.get("permission_id") or "").strip()
        if not permission_id:
            return {
                "result": "Tool '{}' has no capability permission_id".format(
                    tool_def.get("name", tool_def.get("tool_id", "tool"))
                ),
                "is_error": True,
                "widget": None,
            }
        request = {
            "permission_id": permission_id,
            "args": arguments or {},
        }
        qualified_name = str(execution.get("qualified_name") or "").strip()
        if qualified_name:
            request["qualified_name"] = qualified_name
        approved_context, approval_error = _context_with_tool_approval_token(context, tool_def, arguments)
        if approval_error is not None:
            return approval_error
        return self._execute_capability_request(tool_def, request, approved_context)

    def _execute_capability_request(self, tool_def, request, context):
        principal_id = self._principal_id(tool_def, context)
        try:
            executor = self._capability_executor(context)
            response = executor.execute(principal_id, request)
            fallback = self._fallback_function_call_if_first_party_unapproved(
                tool_def,
                request,
                context,
                response,
            )
            if fallback is not None:
                return fallback
            denied_fallback = self._fallback_local_tool_if_first_party_capability_denied(
                tool_def,
                request,
                context,
                response,
            )
            if denied_fallback is not None:
                return denied_fallback
            fallback_tool = self._local_tool_fallback_for_capability_response(response, request)
            if fallback_tool:
                return self._execute_local(fallback_tool, request.get("args") or {}, context)
        except Exception as exc:
            return {
                "result": "Capability execution failed: {}".format(exc),
                "is_error": True,
                "widget": None,
            }
        return self._tool_response_from_capability(response, tool_def, request.get("args") or {})

    def _fallback_local_tool_if_first_party_capability_denied(self, tool_def, request, context, response):
        if request.get("type") != "function.call":
            return None
        if bool(getattr(response, "success", False)):
            return None
        if getattr(response, "error_type", "") not in {"caller_requires_denied", "requires_denied"}:
            return None
        qualified_name = str(request.get("qualified_name") or "")
        pack_id, _, function_id = qualified_name.partition(":")
        local_tool = self._first_party_browser_computer_tool_for_function(pack_id, function_id)
        if local_tool not in {"browser_computer", "browser_use", "computer_use"}:
            return None
        if _requires_approval(tool_def) and not _context_has_tool_server_approval(context):
            return None
        return self._execute_local(local_tool, request.get("args") or {}, context)

    @staticmethod
    def _first_party_browser_computer_tool_for_function(pack_id, function_id):
        if pack_id != "rumi_default_tools_pack":
            return None
        return {
            "browser_computer": "browser_computer",
            "browser_use": "browser_use",
            "computer_use": "computer_use",
        }.get(function_id)

    @staticmethod
    def _local_tool_fallback_for_capability_response(response, request):
        if bool(getattr(response, "success", False)):
            return None
        if request.get("type") != "function.call":
            return None
        if getattr(response, "error_type", None) not in {"function_not_found", "function_registry_unavailable"}:
            return None
        qualified_name = str(request.get("qualified_name") or "")
        return {
            "defaultspack:tool_calculator": "calculator",
            "rumi_default_tools_pack:calculator": "calculator",
        }.get(qualified_name)

    @staticmethod
    def _fallback_function_call_if_first_party_unapproved(tool_def, request, context, response):
        if request.get("type") != "function.call":
            return None
        if bool(getattr(response, "success", False)):
            return None
        if getattr(response, "error_type", "") not in {
            "function_not_found",
            "function_registry_unavailable",
            "pack_not_approved",
        }:
            return None
        qualified_name = str(request.get("qualified_name") or "")
        pack_id, _, function_id = qualified_name.partition(":")
        if pack_id not in {"defaultspack", "rumi_default_tools_pack"} or not function_id:
            return None
        if _is_explicitly_untrusted_tool(tool_def if isinstance(tool_def, dict) else {}):
            return None
        local_tool = ToolExecutor._first_party_local_tool_for_function(pack_id, function_id)
        if local_tool:
            return ToolExecutor()._execute_local(local_tool, request.get("args") or {}, context)
        if not ToolExecutor._allows_direct_first_party_function_fallback(pack_id, function_id):
            return None
        try:
            from core_runtime.pack_function_runtime import invoke_pack_function

            fallback_context = dict(context or {}) if isinstance(context, dict) else {}
            fallback_context.update(_function_call_context(fallback_context, tool_def))
            output = invoke_pack_function(
                pack_id,
                function_id,
                args=request.get("args") or {},
                context=fallback_context,
            )
        except Exception:
            return None
        return ToolExecutor._tool_response_from_pack_function_output(output)

    @staticmethod
    def _first_party_local_tool_for_function(pack_id, function_id):
        if pack_id == "rumi_default_tools_pack":
            return {
                "calculator": "calculator",
            }.get(function_id)
        if pack_id == "defaultspack":
            return {
                "tool_calculator": "calculator",
            }.get(function_id)
        return None

    @staticmethod
    def _allows_direct_first_party_function_fallback(pack_id, function_id):
        return (pack_id, function_id) in {
            ("defaultspack", "tool_calculator"),
            ("defaultspack", "coding_file_create"),
            ("defaultspack", "coding_file_write"),
            ("rumi_default_tools_pack", "calculator"),
        }

    @staticmethod
    def _tool_response_from_pack_function_output(output):
        if isinstance(output, dict) and output.get("status") in {"ok", "error"}:
            if output.get("status") == "error":
                error_payload = output.get("error")
                if isinstance(error_payload, dict):
                    message = error_payload.get("message") or error_payload.get("code")
                else:
                    message = error_payload
                return {
                    "result": str(message or "Pack function failed"),
                    "is_error": True,
                    "widget": None,
                }
            output = output.get("data")
        if isinstance(output, dict):
            if "result" in output or "is_error" in output or "widget" in output:
                return {
                    "result": output.get("result", output.get("summary", "")),
                    "is_error": bool(output.get("is_error", False)),
                    "widget": output.get("widget"),
                }
            return {
                "result": json_dumps(output),
                "is_error": False,
                "widget": output,
            }
        return {"result": "" if output is None else str(output), "is_error": False, "widget": None}

    @staticmethod
    def _capability_executor(context):
        if isinstance(context, dict):
            for key in ("capability_executor", "_capability_executor"):
                executor = context.get(key)
                if executor is not None and callable(getattr(executor, "execute", None)):
                    return executor
        try:
            from core_runtime.di_container import get_container

            executor = get_container().get_or_none("capability_executor")
            if executor is not None and callable(getattr(executor, "execute", None)):
                return executor
        except Exception:
            pass
        try:
            from core_runtime.capability_executor import CapabilityExecutor
        except Exception as exc:
            raise RuntimeError("CapabilityExecutor is not available: {}".format(exc)) from exc
        return CapabilityExecutor()

    @staticmethod
    def _ensure_shared_function_registered(qualified_name):
        try:
            from core_runtime.di_container import get_container

            registry = get_container().get("function_registry")
        except Exception:
            return
        try:
            if registry.get(qualified_name) is not None:
                return
        except Exception:
            return
        ToolExecutor._load_pack_functions_into_registry(registry)

    @staticmethod
    def _load_pack_functions_into_registry(registry):
        ecosystem_dir = Path(__file__).resolve().parents[3]
        for pack_root in sorted(ecosystem_dir.iterdir()):
            if not pack_root.is_dir() or not (pack_root / "ecosystem.json").exists():
                continue
            try:
                pack_manifest = json.loads((pack_root / "ecosystem.json").read_text(encoding="utf-8"))
            except Exception:
                pack_manifest = {}
            pack_id = str(pack_manifest.get("pack_id") or pack_root.name).strip() or pack_root.name
            functions_root = pack_root / "functions"
            if not functions_root.exists():
                continue
            for function_dir in sorted(path for path in functions_root.iterdir() if path.is_dir()):
                manifest_path = function_dir / "manifest.json"
                if not manifest_path.is_file():
                    continue
                try:
                    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                except Exception:
                    continue
                function_id = str(manifest.get("function_id") or function_dir.name).strip()
                if not function_id:
                    continue
                try:
                    registry.register(
                        pack_id=pack_id,
                        function_id=function_id,
                        manifest=manifest,
                        function_dir=function_dir,
                    )
                except Exception:
                    continue

    @staticmethod
    def _principal_id(tool_def, context):
        if isinstance(context, dict):
            for key in ("principal_id", "pack_id", "_source_pack_id"):
                value = context.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()
        source_pack_id = tool_def.get("source_pack_id") or tool_def.get("metadata", {}).get("source_pack_id")
        if isinstance(source_pack_id, str) and source_pack_id.strip():
            return source_pack_id.strip()
        return "defaultspack"

    @staticmethod
    def _tool_response_from_capability(response, tool_def=None, arguments=None):
        success = bool(getattr(response, "success", False))
        output = getattr(response, "output", None)
        error = getattr(response, "error", None)
        if not success:
            if (
                getattr(response, "error_type", None) in {"caller_requires_denied", "pack_not_approved", "requires_denied"}
                and isinstance(tool_def, dict)
                and _requires_approval(tool_def)
            ):
                return _approval_required_tool_response(tool_def, arguments or {})
            return {
                "result": str(error or "Capability execution failed"),
                "is_error": True,
                "widget": None,
            }
        if isinstance(output, dict) and output.get("status") in {"ok", "error"}:
            return ToolExecutor._tool_response_from_pack_function_output(output)
        if isinstance(output, dict):
            if "result" in output or "is_error" in output or "widget" in output:
                return {
                    "result": output.get("result", output.get("summary", "")),
                    "is_error": bool(output.get("is_error", False)),
                    "widget": output.get("widget"),
                }
            return {
                "result": json_dumps(output),
                "is_error": False,
                "widget": output,
            }
        return {
            "result": "" if output is None else str(output),
            "is_error": False,
            "widget": None,
        }

    def _execute_dynamic(self, tool_def, arguments, context):
        """
        動的ツール実行。handler_code（Python 文字列）を exec() で実行する。
        handler_code には def handler(arguments, context): ... が定義されている想定。
        P1-2: __builtins__ を制限付きの安全なセットに差し替え。
        """
        handler_code = tool_def.get("handler_code", "")
        if not handler_code:
            return {
                "result": "Dynamic tool '{}' has no handler_code".format(
                    tool_def.get("name", "unknown")
                ),
                "is_error": True,
                "widget": None,
            }

        # P1-2: サンドボックス化 — 危険なビルトインを除去した制限付き globals
        namespace = {"__builtins__": dict(_SAFE_BUILTINS)}
        try:
            exec(handler_code, namespace)
        except Exception as exc:
            return {
                "result": "Failed to load handler_code: {}".format(exc),
                "is_error": True,
                "widget": None,
            }

        handler_fn = namespace.get("handler")
        if handler_fn is None or not callable(handler_fn):
            return {
                "result": "handler_code does not define a callable 'handler' function",
                "is_error": True,
                "widget": None,
            }

        try:
            result = handler_fn(arguments, context)
        except Exception as exc:
            return {
                "result": "Dynamic tool execution failed: {}".format(exc),
                "is_error": True,
                "widget": None,
            }

        # result が dict ならそのまま返す、str なら wrap する
        if isinstance(result, dict):
            return {
                "result": result.get("result", str(result)),
                "is_error": result.get("is_error", False),
                "widget": result.get("widget"),
            }
        return {
            "result": str(result) if result is not None else "",
            "is_error": False,
            "widget": None,
        }

    def _execute_handler(self, tool_def, arguments, context):
        import importlib
        import json

        execution = tool_def.get("execution", {})
        handler = str(execution.get("handler") or "")
        if ":" not in handler:
            return {
                "result": "Tool handler '{}' must use module:callable format".format(handler),
                "is_error": True,
                "widget": None,
            }

        policy = policy_from_context(context if isinstance(context, dict) else {})
        next_arguments = dict(arguments or {})
        next_context, approval_error = _context_with_tool_approval_token(context, tool_def, next_arguments)
        if approval_error is not None:
            return approval_error
        if _truthy(policy.get("yolo_mode")):
            next_context["_tool_server_approved"] = True
        elif _is_policy_allow_context(context):
            next_context["_tool_server_approved"] = True
        elif _context_has_tool_server_approval(next_context):
            pass
        elif _requires_approval(tool_def):
            return _approval_required_tool_response(tool_def, next_arguments)

        module_name, attr_name = handler.split(":", 1)
        try:
            module = importlib.import_module(module_name)
            callable_obj = getattr(module, attr_name)
            result = callable_obj(next_arguments, next_context)
        except Exception as exc:
            return {
                "result": "Tool handler execution failed: {}".format(exc),
                "is_error": True,
                "widget": None,
            }

        if not isinstance(result, dict):
            return {"result": str(result), "is_error": False, "widget": None}

        if "result" in result or "is_error" in result or "widget" in result:
            return {
                "result": result.get("result", ""),
                "is_error": bool(result.get("is_error", False)),
                "widget": result.get("widget"),
            }

        if result.get("status") == "error":
            error_info = result.get("error", {})
            return {
                "result": str(error_info.get("message") if isinstance(error_info, dict) else error_info),
                "is_error": True,
                "widget": result,
            }

        data = result.get("data", result)
        result_text = data if isinstance(data, str) else json.dumps(data, ensure_ascii=False)
        is_approval = isinstance(data, dict) and bool(data.get("approval_required"))
        return {
            "result": result_text,
            "is_error": False,
            "widget": {"type": "approval_request", **data} if is_approval else result,
        }

    def _execute_local(self, tool_name, arguments, context):
        """
        ローカルツール実行（最小動作版: 固定レスポンスを返す）
        """
        if _is_cancelled(context):
            return _cancelled_tool_result(tool_name)
        if tool_name == "web_search":
            from domain.research.providers import ExternalWebProvider

            query = arguments.get("query", "")
            result = ExternalWebProvider().search(
                query,
                limit=int(arguments.get("limit", 5)),
                allow_network=bool(arguments.get("allow_network", True)),
            )
            return {
                "result": result.summary,
                "is_error": False,
                "widget": {"type": "research_sources", **result.as_dict()}
            }
        elif tool_name == "reddit_search":
            from domain.research.providers import RedditProvider

            query = arguments.get("query", "")
            result = RedditProvider().search(
                query,
                subreddit=arguments.get("subreddit"),
                sort=arguments.get("sort", "relevance"),
                limit=int(arguments.get("limit", 10)),
                allow_network=bool(arguments.get("allow_network", True)),
            )
            return {
                "result": result.summary,
                "is_error": False,
                "widget": {"type": "research_sources", **result.as_dict()}
            }
        elif tool_name in {"browser_computer", "browser_use", "computer_use"}:
            from ecosystem.rumi_default_tools_pack.domain.tool.browser_computer import BrowserComputerController

            policy = policy_from_context(context if isinstance(context, dict) else {})
            action, payload = _browser_computer_action_payload(tool_name, arguments)
            if _is_cancelled(context):
                return _cancelled_tool_result(tool_name, action=action)
            user_requested = bool(isinstance(context, dict) and context.get("user_requested_computer_use"))
            if user_requested and action == "browser.open_url" and not any(
                key in payload for key in ("persistent", "profile_id", "session_id")
            ):
                payload["persistent"] = False
            result = BrowserComputerController(artifact_root=_conversation_tool_artifact_root(context)).run(
                action,
                _computer_use_payload_with_context_defaults(action, payload, context),
                yolo_mode=_truthy(policy.get("yolo_mode")),
            )
            if _is_cancelled(context):
                return _cancelled_tool_result(tool_name, action=action)
            is_error = bool(result.get("is_error"))
            summary = "{} {} {}".format(
                tool_name,
                result.get("action", "action"),
                "failed" if is_error else "completed",
            )
            if is_error and result.get("reason"):
                summary += ": {}".format(result.get("reason"))
            if result.get("path"):
                summary += "; artifact: {}".format(result.get("path"))
            output = {
                "result": summary,
                "is_error": is_error,
                "widget": {"type": tool_name, **result},
            }
            if isinstance(result.get("recovery"), dict):
                output["recovery"] = result.get("recovery")
            return output
        elif tool_name == "browser_companion":
            from ecosystem.rumi_default_tools_pack.domain.tool.browser_companion import BrowserCompanionController

            action = str(arguments.get("action") or "session")
            payload = {key: value for key, value in (arguments or {}).items() if key != "action"}
            result = BrowserCompanionController(artifact_root=_conversation_browser_companion_artifact_root(context)).run(
                action,
                payload,
                context=context if isinstance(context, dict) else {},
            )
            is_error = bool(result.get("is_error"))
            summary = "{} {} {}".format(
                tool_name,
                result.get("action", "action"),
                "failed" if is_error else "completed",
            )
            if result.get("reason"):
                summary += ": {}".format(result.get("reason"))
            if result.get("path"):
                summary += "; artifact: {}".format(result.get("path"))
            return {
                "result": summary,
                "is_error": is_error,
                "widget": {"type": tool_name, **result},
            }
        elif tool_name == "todo":
            from ecosystem.rumi_default_tools_pack.domain.tool.todo import TodoController

            result = TodoController().run(arguments, context if isinstance(context, dict) else {})
            return {
                "result": result.get("summary", "todo updated"),
                "is_error": False,
                "widget": {"type": "todo", **result},
            }
        elif tool_name == "subagent":
            from ecosystem.rumi_default_tools_pack.domain.tool.subagent import SubagentController

            result = SubagentController().run(arguments, context if isinstance(context, dict) else {})
            return {
                "result": result.get("summary", "subagent completed"),
                "is_error": False,
                "widget": {"type": "subagent", **result},
            }
        elif tool_name == "calculator":
            expression = arguments.get("expression", "")
            calculation = _safe_calculate(expression)
            if calculation["is_error"]:
                return {
                    "result": calculation["error"],
                    "is_error": True,
                    "widget": None,
                }
            return {
                "result": "Calculated: {} = {}".format(expression, calculation["result"]),
                "is_error": False,
                "widget": None
            }
        elif tool_name == "file_reader":
            from blocks.coding.file_read import run as file_read_run

            path = arguments.get("path", "")
            workspace_root = arguments.get("workspace_root")
            if workspace_root is None and isinstance(context, dict):
                workspace_root = context.get("workspace_root")
            result = file_read_run(
                {
                    "path": path,
                    "workspace_root": workspace_root,
                },
                context if isinstance(context, dict) else {},
            )
            if result.get("status") != "ok":
                err = result.get("error", {})
                message = (
                    err.get("message", "file read failed")
                    if isinstance(err, dict)
                    else str(err)
                )
                return {
                    "result": message,
                    "is_error": True,
                    "widget": {"type": "file_reader", "path": path, "error": err},
                }
            data = result.get("data", {})
            return {
                "result": data.get("content", ""),
                "is_error": False,
                "widget": {"type": "file_reader", **data},
            }
        else:
            return {
                "result": "Tool '{}' is not implemented".format(tool_name),
                "is_error": True,
                "widget": {
                    "type": tool_name,
                    "error": "not_implemented",
                    "arguments": arguments,
                },
            }


def _is_cancelled(context):
    checker = context.get("is_cancelled") if isinstance(context, dict) else None
    if callable(checker):
        try:
            return bool(checker())
        except Exception:
            return False
    return False


def _cancelled_tool_result(tool_name, *, action=""):
    detail = " during {}".format(action) if action else ""
    return {
        "result": "Tool '{}' cancelled{}".format(tool_name, detail),
        "is_error": True,
        "widget": {
            "type": tool_name,
            "action": action or "cancelled",
            "is_error": True,
            "cancelled": True,
            "reason": "Tool execution cancelled by user.",
        },
        "cancelled": True,
    }


def _truthy(value):
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return bool(value)


def _filtered_tool_rejection(tool_name, context):
    if not isinstance(context, dict):
        return None
    entries = context.get("tool_filter_result")
    if isinstance(entries, list):
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            if str(entry.get("tool_name") or "") != str(tool_name or ""):
                continue
            if str(entry.get("status") or "") in {"blocked", "hidden"}:
                return rejection_result(str(tool_name or ""), entry)
    capability_graph = context.get("capability_graph") if isinstance(context.get("capability_graph"), dict) else {}
    connected = capability_graph.get("connected_tools") if isinstance(capability_graph.get("connected_tools"), list) else []
    if connected and str(tool_name or "") not in {str(item) for item in connected if str(item or "").strip()}:
        return rejection_result(
            str(tool_name or ""),
            {
                "reason_code": "not_connected_to_profile",
                "reason": "tool is not connected to the active runtime profile",
                "required": {"runtime_capabilities": ["runtime.connected_tools"]},
                "actual": {"runtime_capabilities": list(connected)},
                "repair_suggestions": ["Connect the tool in the active runtime profile."],
            },
        )
    return None


def _safe_calculate(expression):
    import ast
    import operator

    operators = {
        ast.Add: operator.add,
        ast.Sub: operator.sub,
        ast.Mult: operator.mul,
        ast.Div: operator.truediv,
        ast.FloorDiv: operator.floordiv,
        ast.Mod: operator.mod,
        ast.Pow: operator.pow,
        ast.USub: operator.neg,
        ast.UAdd: operator.pos,
    }

    def evaluate(node):
        if isinstance(node, ast.Expression):
            return evaluate(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in operators:
            left = evaluate(node.left)
            right = evaluate(node.right)
            if isinstance(node.op, ast.Pow) and abs(right) > 100:
                raise ValueError("Exponent is too large")
            return operators[type(node.op)](left, right)
        if isinstance(node, ast.UnaryOp) and type(node.op) in operators:
            return operators[type(node.op)](evaluate(node.operand))
        raise ValueError("Unsupported calculator expression")

    try:
        parsed = ast.parse(str(expression or ""), mode="eval")
        result = evaluate(parsed)
    except Exception as exc:
        return {"is_error": True, "error": "Calculator error: {}".format(exc)}
    return {"is_error": False, "result": result}


def _browser_computer_action_payload(tool_name, arguments):
    arguments = arguments if isinstance(arguments, dict) else {}
    if tool_name == "browser_computer":
        return str(arguments.get("action", "browser.session")), dict(arguments.get("payload") or {})

    raw_payload = dict(arguments.get("payload") or {})
    raw_action = str(arguments.get("action") or "").strip()
    if tool_name == "browser_use":
        action_map = {
            "": "browser.session",
            "session": "browser.session",
            "open_url": "browser.open_url",
            "open": "browser.open_url",
            "context": "computer.context",
            "app_context": "computer.context",
            "state": "computer.context",
            "screenshot": "computer.screenshot",
            "move": "computer.move",
            "cursor_move": "computer.move",
            "mouse_move": "computer.move",
            "click": "computer.click",
            "drag": "computer.drag",
            "mouse_drag": "computer.drag",
            "type": "computer.type",
            "key": "computer.key",
            "scroll": "computer.scroll",
            "apps": "computer.apps",
            "applications": "computer.apps",
            "open_apps": "computer.apps",
            "list_apps": "computer.apps",
            "select_app": "computer.select_app",
            "app": "computer.select_app",
            "show_app": "computer.show_app",
            "focus_app": "computer.show_app",
            "activate_app": "computer.show_app",
            "main_app": "computer.show_app",
            "show": "computer.show_app",
            "select_window": "computer.select_window",
            "window": "computer.select_window",
            "windows": "computer.windows",
            "list_windows": "computer.windows",
        }
        action = action_map.get(raw_action, raw_action)
        for key in (
            "url",
            "url_contains",
            "x",
            "y",
            "point",
            "points",
            "point_order",
            "coordinate",
            "coordinates",
            "normalized_point",
            "normalized_x",
            "normalized_y",
            "x1",
            "y1",
            "x2",
            "y2",
            "from_x",
            "from_y",
            "to_x",
            "to_y",
            "text",
            "key",
            "modifier",
            "modifiers",
            "amount",
            "target",
            "scope",
            "app",
            "application",
            "name",
            "title",
            "title_contains",
            "window",
            "window_index",
            "tab_index",
            "button",
            "include_screenshot",
            "coordinate_space",
            "physical",
            "virtual_only",
            "crop",
            "zoom",
            "crop_box",
            "zoom_box",
            "source",
            "detail",
            "crop_x",
            "crop_y",
            "crop_width",
            "crop_height",
            "normalized_box",
            "normalized_width",
            "normalized_height",
            "normalized_right",
            "normalized_bottom",
            "box_format",
            "width_height",
            "focus",
            "open",
            "launch",
            "limit",
            "include_installed",
            "include_installed_apps",
            "mode",
            "method",
            "driver",
        ):
            if key in arguments:
                raw_payload[key] = arguments.get(key)
    else:
        action_map = {
            "": "computer.screenshot",
            "context": "computer.context",
            "app_context": "computer.context",
            "state": "computer.context",
            "screenshot": "computer.screenshot",
            "move": "computer.move",
            "cursor_move": "computer.move",
            "mouse_move": "computer.move",
            "click": "computer.click",
            "drag": "computer.drag",
            "mouse_drag": "computer.drag",
            "type": "computer.type",
            "key": "computer.key",
            "scroll": "computer.scroll",
            "apps": "computer.apps",
            "applications": "computer.apps",
            "open_apps": "computer.apps",
            "list_apps": "computer.apps",
            "select_app": "computer.select_app",
            "app": "computer.select_app",
            "show_app": "computer.show_app",
            "focus_app": "computer.show_app",
            "activate_app": "computer.show_app",
            "main_app": "computer.show_app",
            "show": "computer.show_app",
            "select_window": "computer.select_window",
            "window": "computer.select_window",
            "windows": "computer.windows",
            "list_windows": "computer.windows",
        }
        action = action_map.get(raw_action, raw_action)
        for key in (
            "url",
            "url_contains",
            "x",
            "y",
            "point",
            "points",
            "point_order",
            "coordinate",
            "coordinates",
            "normalized_point",
            "normalized_x",
            "normalized_y",
            "x1",
            "y1",
            "x2",
            "y2",
            "from_x",
            "from_y",
            "to_x",
            "to_y",
            "text",
            "key",
            "modifier",
            "modifiers",
            "amount",
            "target",
            "scope",
            "app",
            "application",
            "name",
            "title",
            "title_contains",
            "window",
            "window_index",
            "tab_index",
            "button",
            "include_screenshot",
            "coordinate_space",
            "physical",
            "virtual_only",
            "crop",
            "zoom",
            "crop_box",
            "zoom_box",
            "source",
            "detail",
            "crop_x",
            "crop_y",
            "crop_width",
            "crop_height",
            "normalized_box",
            "normalized_width",
            "normalized_height",
            "normalized_right",
            "normalized_bottom",
            "box_format",
            "width_height",
            "focus",
            "open",
            "launch",
            "limit",
            "include_installed",
            "include_installed_apps",
            "mode",
            "method",
            "driver",
        ):
            if key in arguments:
                raw_payload[key] = arguments.get(key)
    if "dry_run" in arguments:
        raw_payload["dry_run"] = arguments.get("dry_run")
    if "approval_token" in arguments:
        raw_payload["approval_token"] = arguments.get("approval_token")
    return action, raw_payload


def _computer_use_payload_with_context_defaults(action, payload, context):
    payload = dict(payload or {})
    if not isinstance(context, dict):
        return payload
    target_app = context.get("computer_use_target_app")
    target_title = context.get("computer_use_target_title")
    physical_clicks = _truthy(context.get("computer_use_physical_clicks"))
    if action == "browser.open_url":
        if isinstance(target_app, str) and target_app.strip() and not any(
            payload.get(key) for key in ("app", "application", "browser", "browser_app")
        ):
            payload["app"] = target_app.strip()
        return payload
    if action.startswith("computer.") and action not in {"computer.windows", "computer.apps"}:
        if isinstance(target_app, str) and target_app.strip():
            if action in {"computer.select_app", "computer.show_app"}:
                if not any(payload.get(key) for key in ("app", "application", "name")):
                    payload["app"] = target_app.strip()
            else:
                payload.setdefault("app", target_app.strip())
        if (
            isinstance(target_title, str)
            and target_title.strip()
            and action not in {"computer.select_app", "computer.show_app"}
        ):
            payload.setdefault("title", target_title.strip())
        if physical_clicks and action == "computer.click" and "physical" not in payload:
            payload["physical"] = True
    return payload


def _conversation_tool_artifact_root(context):
    if not isinstance(context, dict):
        return None
    workspace = context.get("conversation_workspace_dir")
    if not isinstance(workspace, str) or not workspace:
        return None
    return Path(workspace) / "tools" / "computer"


def _conversation_browser_companion_artifact_root(context):
    if not isinstance(context, dict):
        return None
    workspace = context.get("conversation_workspace_dir")
    if not isinstance(workspace, str) or not workspace:
        return None
    return Path(workspace) / "tools" / "browser_companion"


def _tool_value(tool_def, key):
    if key in tool_def:
        return tool_def.get(key)
    metadata = tool_def.get("metadata")
    if isinstance(metadata, dict) and key in metadata:
        return metadata.get(key)
    execution = tool_def.get("execution")
    if isinstance(execution, dict):
        return execution.get(key)
    return None


def _requires_approval(tool_def):
    return requires_approval_for_security(tool_def)


def _tool_approval_tool_name(tool_def):
    return str(tool_def.get("name") or tool_def.get("tool_id") or "tool").strip() or "tool"


def _tool_approval_operation(tool_def):
    return "tool.{}".format(_tool_approval_tool_name(tool_def))


def _tool_approval_risk_level(tool_def):
    return "high" if _is_high_risk_approval(tool_def) else "medium"


def _approval_token_from_arguments(arguments):
    if not isinstance(arguments, dict):
        return ""
    return str(arguments.get("approval_token") or "").strip()


def _approval_token_from_context(context, tool_def):
    if not isinstance(context, dict):
        return ""
    tokens = context.get("tool_approval_tokens")
    if not isinstance(tokens, dict):
        return ""
    for key in (
        _tool_approval_tool_name(tool_def),
        _tool_approval_operation(tool_def),
    ):
        token = str(tokens.get(key) or "").strip()
        if token:
            return token
    return ""


def _context_with_tool_approval_token(context, tool_def, arguments):
    next_context = dict(context or {}) if isinstance(context, dict) else {}
    if not isinstance(tool_def, dict) or not _requires_approval(tool_def):
        return next_context, None
    if _context_has_tool_server_approval(next_context):
        return next_context, None
    token = _approval_token_from_arguments(arguments) or _approval_token_from_context(context, tool_def)
    if not token:
        return next_context, None
    approval = _approval_module()
    verification = approval.verify_execution_token(
        token,
        _tool_approval_operation(tool_def),
        approval.hash_arguments(arguments if isinstance(arguments, dict) else {}),
    )
    if verification.valid:
        next_context["_tool_server_approved"] = True
        next_context["_tool_server_approval_token_valid"] = True
        return next_context, None
    return next_context, {
        "result": verification.message or "approval token is invalid",
        "is_error": True,
        "widget": None,
    }


def _approval_required_tool_response(tool_def, arguments):
    tool_name = _tool_approval_tool_name(tool_def)
    operation = _tool_approval_operation(tool_def)
    risk_level = _tool_approval_risk_level(tool_def)
    args = dict(arguments or {}) if isinstance(arguments, dict) else {}
    request = _approval_module().create_approval_request(
        operation,
        risk_level,
        args,
        details={"tool_name": tool_name},
    )
    return {
        "result": "Tool '{}' requires approval".format(tool_name),
        "is_error": False,
        "widget": {
            "type": "approval_request",
            "tool_name": tool_name,
            "approval_required": True,
            "requires_approval": True,
            "risk_level": risk_level,
            "operation": operation,
            "action": operation,
            "arguments": _redact_sensitive_arguments(args),
            "payload": args,
            "approval_request_id": request["request_id"],
            "args_hash": request["args_hash"],
            "expires_at": request["expires_at"],
            "display_summary": request["display_summary"],
        },
    }


def _redact_sensitive_arguments(value):
    if isinstance(value, dict):
        redacted = {}
        for key, item in value.items():
            key_text = str(key)
            if _is_sensitive_argument_key(key_text):
                redacted[key_text] = "[redacted]"
            else:
                redacted[key_text] = _redact_sensitive_arguments(item)
        return redacted
    if isinstance(value, list):
        return [_redact_sensitive_arguments(item) for item in value]
    return value


def _is_sensitive_argument_key(key):
    lowered = str(key or "").lower()
    return any(
        marker in lowered
        for marker in ("api_key", "authorization", "bearer", "credential", "password", "secret", "token")
    )


def _is_high_risk_approval(tool_def):
    if str(_tool_value(tool_def, "risk") or "").strip().lower() == "high":
        return True
    grants = _tool_value(tool_def, "capability_grants")
    if isinstance(grants, list):
        high_risk_prefixes = (
            "browser.",
            "computer.",
            "file.write",
            "git.write",
            "network.send",
            "terminal.exec",
        )
        for grant in grants:
            if str(grant or "").strip().startswith(high_risk_prefixes):
                return True
    return _is_shell_or_git(tool_def)


def _is_shell_or_git(tool_def):
    action_type = str(_tool_value(tool_def, "action_type") or "")
    category = str(_tool_value(tool_def, "category") or "")
    return action_type == "shell" or category in {"shell", "git"}


def _is_policy_allow_context(context):
    return internal_tool_decision_allows(context)


def _context_has_tool_server_approval(context):
    if not isinstance(context, dict):
        return False
    policy = policy_from_context(context)
    if _truthy(policy.get("yolo_mode")) or _is_policy_allow_context(context):
        return True
    if context.get("_tool_server_approval_token_valid") is True:
        return True
    return bool(
        context.get("_tool_server_approved")
        and any(str(context.get(key) or "").strip() for key in ("principal_id", "pack_id", "_source_pack_id"))
    )


def _function_call_context(context, tool_def):
    if not isinstance(context, dict):
        return {}
    forwarded = {}
    for key in (
        "workspace_id",
        "workspace_root",
        "conversation_id",
        "conversation_workspace_dir",
        "profile_id",
        "run_id",
        "request_id",
        "profile_policy",
        "user_requested_computer_use",
        "computer_use_target_app",
        "computer_use_target_title",
        "computer_use_physical_clicks",
    ):
        if key in context and _json_safe_value(context.get(key)):
            forwarded[key] = context.get(key)
    if "workspace_root" not in forwarded and _needs_cwd_workspace_default(tool_def):
        forwarded["workspace_root"] = str(Path.cwd())
    policy = policy_from_context(context)
    if _truthy(policy.get("yolo_mode")) or _is_policy_allow_context(context):
        forwarded["_tool_server_approved"] = True
    if _requires_approval(tool_def) and bool(context.get("_tool_server_approved")):
        forwarded["_tool_server_approved"] = True
    return forwarded


def _needs_cwd_workspace_default(tool_def):
    grants = _tool_value(tool_def, "capability_grants")
    if isinstance(grants, list):
        for grant in grants:
            value = str(grant or "").strip()
            if value.startswith(("file.", "git.", "terminal.")):
                return True
    category = str(_tool_value(tool_def, "category") or "").strip()
    return category in {"coding", "file", "filesystem", "git", "shell", "terminal"}


def _is_explicitly_untrusted_tool(tool_def):
    if not isinstance(tool_def, dict):
        return False
    metadata = tool_def.get("metadata")
    if isinstance(metadata, dict):
        if metadata.get("trusted") is False:
            return True
        source_pack_id = metadata.get("source_pack_id")
        if isinstance(source_pack_id, str) and source_pack_id.strip():
            return not is_trusted_pack_id(source_pack_id)
    source_pack_id = tool_def.get("source_pack_id")
    if isinstance(source_pack_id, str) and source_pack_id.strip():
        return not is_trusted_pack_id(source_pack_id)
    if "trusted" in tool_def and tool_def.get("trusted") is False:
        return True
    return False


def _json_safe_value(value):
    try:
        json.dumps(value, ensure_ascii=False)
        return True
    except (TypeError, ValueError):
        return False
