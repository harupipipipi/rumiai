import json
import re
import time
from pathlib import Path

from .registry import ToolRegistry
from .mcp_client import McpClient
from .schema_adapter import is_tool_rejected_by_policy, policy_from_context


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

        execution = tool_def.get("execution", {})
        exec_type = execution.get("type", "local")

        if exec_type == "mcp":
            server_name = execution.get("server_name", "")
            mcp_tool_name = execution.get("mcp_tool_name", tool_name)
            return self._mcp_client.invoke(server_name, mcp_tool_name, arguments)

        if exec_type == "dynamic":
            return self._execute_dynamic(tool_def, arguments, context)

        if exec_type == "prompt":
            return self._execute_prompt(tool_def, arguments, context)

        handler = str(execution.get("handler") or "")
        if handler and not handler.endswith(":ToolExecutor.execute"):
            return self._execute_handler(tool_def, arguments, context)

        return self._execute_local(tool_name, arguments, context)

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

    def _execute_prompt(self, tool_def, arguments, context):
        """
        P2-1: prompt ベースのツール実行パス。
        execution.type == "prompt" のツールを実行する。
        テンプレート本文の {{var}} を arguments で展開し、結果を返す。
        """
        import re

        execution = tool_def.get("execution", {})
        body = execution.get("body", "")
        if not body:
            return {
                "result": "Prompt tool '{}' has no body".format(
                    tool_def.get("name", "unknown")
                ),
                "is_error": True,
                "widget": None,
            }

        # テンプレート変数を展開
        def replace_var(match):
            var_name = match.group(1).strip()
            if var_name in arguments:
                return str(arguments[var_name])
            return match.group(0)  # 未知の変数はそのまま残す

        rendered = re.sub(r"\{\{\s*([\w.]+)\s*\}\}", replace_var, body)

        return {
            "result": rendered,
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
        next_context = dict(context or {}) if isinstance(context, dict) else {}
        if bool(policy.get("yolo_mode")):
            next_context["_tool_server_approved"] = True
        elif _is_policy_allow_context(context):
            next_context["_tool_server_approved"] = True
        elif _requires_approval(tool_def):
            return {
                "result": "Tool '{}' requires approval".format(tool_def.get("name", tool_def.get("tool_id", "tool"))),
                "is_error": False,
                "widget": {
                    "type": "approval_request",
                    "tool_name": tool_def.get("name", tool_def.get("tool_id", "tool")),
                    "approval_required": True,
                    "risk_level": "high" if _is_shell_or_git(tool_def) else "medium",
                    "arguments": next_arguments,
                },
            }

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
        elif tool_name in {"browser_computer", "browser_use", "computer_use", "zoom"}:
            from domain.tool.browser_computer import BrowserComputerController

            policy = policy_from_context(context if isinstance(context, dict) else {})
            if tool_name == "browser_use":
                browser_v2 = _try_execute_browser_v2(arguments, context)
                if browser_v2 is not None:
                    result_text = browser_v2 if isinstance(browser_v2, str) else json.dumps(browser_v2, ensure_ascii=False)
                    return {
                        "result": result_text,
                        "is_error": bool(isinstance(browser_v2, dict) and browser_v2.get("status") == "error"),
                        "widget": {"type": "browser_use", **browser_v2} if isinstance(browser_v2, dict) else None,
                    }
            action, payload = _browser_computer_action_payload(tool_name, arguments)
            payload = _apply_tool_support_desktop_defaults(action, payload, context)
            result = BrowserComputerController(artifact_root=_conversation_tool_artifact_root(context)).run(
                action,
                payload,
                yolo_mode=bool(policy.get("yolo_mode")),
            )
            action_name = result.get("action", "action")
            is_error = result.get("status") == "error"
            requires_approval = bool(result.get("requires_approval"))
            if is_error:
                error = result.get("error")
                message = error.get("message") if isinstance(error, dict) else error
                summary = "{} {} failed: {}".format(tool_name, action_name, message or "error")
            elif requires_approval:
                summary = "{} {} requires approval".format(tool_name, action_name)
            else:
                summary = "{} {} completed".format(tool_name, action_name)
            if result.get("path"):
                summary += "; artifact: {}".format(result.get("path"))
            return {
                "result": summary,
                "is_error": is_error,
                "widget": {"type": tool_name, **result}
            }
        elif tool_name == "todo":
            from domain.tool.todo import TodoController

            result = TodoController().run(arguments, context if isinstance(context, dict) else {})
            return {
                "result": result.get("summary", "todo updated"),
                "is_error": False,
                "widget": {"type": "todo", **result},
            }
        elif tool_name == "wait":
            result = _execute_wait(arguments, context if isinstance(context, dict) else {})
            return {
                "result": result.get("summary", "wait completed"),
                "is_error": result.get("status") == "error",
                "widget": {"type": "wait", **result},
            }
        elif tool_name == "think":
            result = _execute_think(arguments, context if isinstance(context, dict) else {})
            return {
                "result": result.get("summary", "checkpoint recorded"),
                "is_error": False,
                "widget": {"type": "think", **result},
            }
        elif tool_name == "subagent":
            from domain.tool.subagent import SubagentController

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
            path = arguments.get("path", "")
            return {
                "result": "File content from: {} (stub)".format(path),
                "is_error": False,
                "widget": None
            }
        else:
            return {
                "result": "Tool '{}' executed with args: {} (stub)".format(tool_name, arguments),
                "is_error": False,
                "widget": None
            }


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


def _execute_wait(arguments, context):
    del context
    try:
        seconds = _wait_seconds(arguments if isinstance(arguments, dict) else {})
    except Exception as exc:
        return {"status": "error", "summary": str(exc)}
    max_seconds = float((arguments or {}).get("max_seconds") or 6 * 60 * 60)
    if seconds < 0:
        return {"status": "error", "summary": "wait duration must be non-negative", "seconds": seconds}
    if seconds > max_seconds:
        return {
            "status": "error",
            "summary": "wait duration exceeds max_seconds",
            "seconds": seconds,
            "max_seconds": max_seconds,
        }
    if bool((arguments or {}).get("dry_run")):
        return {"status": "ok", "dry_run": True, "summary": f"would wait {seconds:g} seconds", "seconds": seconds}
    started = time.time()
    time.sleep(seconds)
    elapsed = time.time() - started
    return {
        "status": "ok",
        "summary": f"waited {elapsed:.2f} seconds",
        "seconds": seconds,
        "elapsed_seconds": elapsed,
        "reason": str((arguments or {}).get("reason") or ""),
    }


def _wait_seconds(arguments):
    total = 0.0
    for key, multiplier in (("seconds", 1.0), ("minutes", 60.0), ("hours", 3600.0)):
        if arguments.get(key) is not None:
            total += float(arguments.get(key) or 0) * multiplier
    if total > 0 or not arguments.get("duration"):
        return total
    raw = str(arguments.get("duration") or "").strip().lower()
    match = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)\s*(s|sec|secs|second|seconds|m|min|mins|minute|minutes|h|hr|hrs|hour|hours)?", raw)
    if not match:
        raise ValueError("duration must look like 30s, 10m, or 2h")
    value = float(match.group(1))
    unit = match.group(2) or "seconds"
    if unit.startswith("h"):
        return value * 3600
    if unit.startswith("m"):
        return value * 60
    return value


def _execute_think(arguments, context):
    del context
    arguments = arguments if isinstance(arguments, dict) else {}

    def text(name, fallback=""):
        value = arguments.get(name, fallback)
        if value is None:
            return ""
        return str(value).strip()

    def list_text(name):
        value = arguments.get(name)
        if value is None:
            return []
        if isinstance(value, str):
            return [line.strip(" -\t") for line in value.splitlines() if line.strip(" -\t")]
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        return [str(value).strip()] if str(value).strip() else []

    summary = text("summary") or text("checkpoint") or "Checkpoint recorded."
    completed = list_text("completed")
    next_steps = list_text("next_steps") or list_text("next")
    blockers = list_text("blockers")
    confidence = arguments.get("confidence")
    try:
        confidence = None if confidence is None else max(0.0, min(1.0, float(confidence)))
    except Exception:
        confidence = None

    parts = [summary]
    if completed:
        parts.append("Done: " + "; ".join(completed[:5]))
    if next_steps:
        parts.append("Next: " + "; ".join(next_steps[:5]))
    if blockers:
        parts.append("Blocked: " + "; ".join(blockers[:5]))

    return {
        "status": "ok",
        "summary": "\n".join(parts),
        "checkpoint": summary,
        "completed": completed,
        "next_steps": next_steps,
        "blockers": blockers,
        "confidence": confidence,
    }


def _browser_computer_action_payload(tool_name, arguments):
    arguments = arguments if isinstance(arguments, dict) else {}
    raw_action = ""
    if tool_name == "browser_computer":
        action = str(arguments.get("action", "browser.session"))
        raw_payload = dict(arguments.get("payload") or {})
    elif tool_name == "zoom":
        action = "computer.zoom"
        raw_payload = dict(arguments)
    else:
        raw_payload = dict(arguments.get("payload") or {})
        raw_action = str(arguments.get("action") or "").strip()
    if tool_name == "browser_use":
        action_map = {
            "": "browser.session",
            "session": "browser.session",
            "open_url": "browser.open_url",
            "open": "browser.open_url",
            "screenshot": "computer.screenshot",
            "move": "computer.move",
            "cursor_move": "computer.move",
            "mouse_move": "computer.move",
            "click": "computer.click",
            "input": "computer.type",
            "type": "computer.type",
            "key": "computer.key",
            "scroll": "computer.scroll",
            "wait": "computer.wait",
            "zoom": "computer.zoom",
            "computer.zoom": "computer.zoom",
            "new_tab": "computer.hotkey",
            "close_tab": "computer.hotkey",
            "refresh": "computer.hotkey",
            "reload": "computer.hotkey",
            "select_all": "computer.hotkey",
            "copy": "computer.hotkey",
            "paste": "computer.hotkey",
            "app.focus": "computer.app.focus",
            "app_focus": "computer.app.focus",
            "focus_app": "computer.app.focus",
            "application.focus": "computer.app.focus",
            "app.open": "computer.app.open",
            "app_open": "computer.app.open",
            "open_app": "computer.app.open",
            "active_window": "computer.active_window",
            "windows.list": "computer.windows.list",
            "windows_list": "computer.windows.list",
            "apps.list": "computer.apps.list",
            "apps_list": "computer.apps.list",
            "app.list": "computer.apps.list",
            "app_list": "computer.apps.list",
            "app.find": "computer.app.find",
            "app_find": "computer.app.find",
            "find_app": "computer.app.find",
        }
        action = action_map.get(raw_action, raw_action)
        for key in (
            "url",
            "x",
            "y",
            "point",
            "points",
            "normalized_point",
            "point_order",
            "width",
            "height",
            "radius",
            "scale",
            "source_path",
            "latest",
            "text",
            "input_text",
            "seconds",
            "key",
            "keys",
            "combo",
            "amount",
            "direction",
            "target",
            "target_scope",
            "coordinate_space",
            "focus",
            "quality",
            "image_detail",
            "vision_detail",
            "screenshot_path",
            "model_image_path",
            "visual_feedback",
            "show_click_feedback",
            "post_click_delay",
            "app",
            "name",
            "query",
        ):
            if key in arguments:
                raw_payload[key] = arguments.get(key)
    elif tool_name not in {"browser_computer", "zoom"}:
        action_map = {
            "": "computer.screenshot",
            "screenshot": "computer.screenshot",
            "move": "computer.move",
            "cursor_move": "computer.move",
            "mouse_move": "computer.move",
            "click": "computer.click",
            "input": "computer.type",
            "type": "computer.type",
            "key": "computer.key",
            "scroll": "computer.scroll",
            "wait": "computer.wait",
            "zoom": "computer.zoom",
            "computer.zoom": "computer.zoom",
            "new_tab": "computer.hotkey",
            "close_tab": "computer.hotkey",
            "refresh": "computer.hotkey",
            "reload": "computer.hotkey",
            "select_all": "computer.hotkey",
            "copy": "computer.hotkey",
            "paste": "computer.hotkey",
            "app.focus": "computer.app.focus",
            "app_focus": "computer.app.focus",
            "focus_app": "computer.app.focus",
            "application.focus": "computer.app.focus",
            "app.open": "computer.app.open",
            "app_open": "computer.app.open",
            "open_app": "computer.app.open",
            "active_window": "computer.active_window",
            "windows.list": "computer.windows.list",
            "windows_list": "computer.windows.list",
            "apps.list": "computer.apps.list",
            "apps_list": "computer.apps.list",
            "app.list": "computer.apps.list",
            "app_list": "computer.apps.list",
            "app.find": "computer.app.find",
            "app_find": "computer.app.find",
            "find_app": "computer.app.find",
        }
        action = action_map.get(raw_action, raw_action)
        for key in (
            "x",
            "y",
            "point",
            "points",
            "normalized_point",
            "point_order",
            "width",
            "height",
            "radius",
            "scale",
            "source_path",
            "latest",
            "text",
            "content",
            "input_text",
            "key",
            "keys",
            "combo",
            "amount",
            "direction",
            "seconds",
            "limit",
            "target",
            "target_scope",
            "coordinate_space",
            "focus",
            "window_id",
            "window_index",
            "app",
            "name",
            "query",
            "path",
            "bundle_id",
            "quality",
            "image_detail",
            "vision_detail",
            "screenshot_path",
            "model_image_path",
            "visual_feedback",
            "show_click_feedback",
            "post_click_delay",
        ):
            if key in arguments:
                raw_payload[key] = arguments.get(key)
    if raw_action in {"new_tab", "close_tab", "refresh", "reload", "select_all", "copy", "paste"} and "combo" not in raw_payload and "keys" not in raw_payload:
        raw_payload["shortcut"] = raw_action
    if action == "computer.type" and "text" not in raw_payload and "input_text" in raw_payload:
        raw_payload["text"] = raw_payload.get("input_text")
    if action == "computer.move" and not bool(arguments.get("dry_run")) and "visual_feedback" not in raw_payload and "show_click_feedback" not in raw_payload:
        raw_payload["visual_feedback"] = True
    if action == "computer.click" and not bool(arguments.get("dry_run")) and "visual_feedback" not in raw_payload and "show_click_feedback" not in raw_payload:
        raw_payload["visual_feedback"] = True
    if "dry_run" in arguments:
        raw_payload["dry_run"] = arguments.get("dry_run")
    if "approval_token" in arguments:
        raw_payload["approval_token"] = arguments.get("approval_token")
    return action, raw_payload


def _try_execute_browser_v2(arguments, context):
    try:
        from domain.browser.actions import map_browser_use_action
        from domain.browser.profiles import BrowserProfileManager
        from domain.browser.sessions import BrowserSessionManager
    except Exception:
        return None
    mapped = map_browser_use_action(arguments if isinstance(arguments, dict) else {})
    action = str(mapped.get("action") or "")
    if not action.startswith("browser."):
        return None
    payload = dict(mapped.get("payload") or {})
    root = None
    if isinstance(context, dict) and isinstance(context.get("browser_root"), str):
        root = context.get("browser_root")
    profile_manager = BrowserProfileManager(root)
    manager = BrowserSessionManager(root, profile_manager=profile_manager)
    profile_id = str(payload.get("profile_id") or profile_manager.get_active_profile_id() or "default")
    session_id = str(payload.get("session_id") or f"session-{profile_id}")
    tab_id = payload.get("tab_id")

    if action == "browser.profile.list":
        return {"action": action, "profiles": profile_manager.list_profiles(), "active_profile_id": profile_manager.get_active_profile_id()}
    if action == "browser.profile.get":
        return {"action": action, "profile": profile_manager.get_profile(profile_id)}
    if action == "browser.profile.create":
        return {"action": action, "profile": profile_manager.create_profile(**_profile_create_kwargs(payload))}
    if action == "browser.profile.update":
        return {"action": action, "profile": profile_manager.update_profile(profile_id, payload)}
    if action == "browser.profile.delete":
        return {"action": action, **profile_manager.delete_profile(profile_id, delete_files=bool(payload.get("delete_files")))}
    if action == "browser.profile.set_active":
        return {"action": action, **profile_manager.set_active_profile(profile_id)}
    if action == "browser.session.start":
        return {
            "action": action,
            **manager.start_session(
                session_id=session_id,
                profile_id=profile_id,
                url=payload.get("url"),
                launch=payload.get("launch", True) is not False,
            ),
        }
    if action == "browser.session.stop":
        return {"action": action, **manager.stop_session(session_id)}
    if action == "browser.session.restart":
        return {"action": action, **manager.restart_session(session_id)}
    if action == "browser.session.health":
        return {"action": action, **manager.health(session_id)}
    if action == "browser.session.list":
        return {"action": action, "sessions": manager.list_sessions()}
    if action == "browser.tab.list":
        return {"action": action, **manager.list_tabs(session_id)}
    if action == "browser.tab.open":
        return {"action": action, **manager.open_tab(session_id=session_id, url=str(payload.get("url") or "about:blank"))}
    if action == "browser.tab.focus":
        return {"action": action, **manager.focus_tab(session_id=session_id, tab_id=str(tab_id or payload.get("id") or ""))}
    if action == "browser.tab.close":
        return {"action": action, **manager.close_tab(session_id=session_id, tab_id=str(tab_id or payload.get("id") or ""))}
    if action == "browser.tab.navigate":
        return {"action": action, **manager.navigate_tab(session_id=session_id, tab_id=tab_id, url=str(payload.get("url") or ""))}
    if action == "browser.tab.snapshot":
        return {"action": action, **manager.snapshot_tab(session_id=session_id, tab_id=tab_id)}
    if action == "browser.tab.screenshot":
        return {
            "action": action,
            **manager.screenshot_tab(
                session_id=session_id,
                tab_id=tab_id,
                format=str(payload.get("format") or "png"),
                quality=payload.get("quality"),
            ),
        }
    if action.startswith("browser.ref."):
        return {
            "action": action,
            **manager.execute_ref_action(
                action=action.rsplit(".", 1)[-1],
                ref_id=str(payload.get("ref") or payload.get("ref_id") or ""),
                session_id=session_id,
                tab_id=tab_id,
                payload=payload,
                current_snapshot=payload.get("current_snapshot") if isinstance(payload.get("current_snapshot"), dict) else None,
            ),
        }
    return {"status": "error", "action": action, "error": {"message": f"unsupported browser v2 action: {action}"}}


def _profile_create_kwargs(payload):
    allowed = {"profile_id", "name", "browser", "schema", "settings", "metadata", "set_active"}
    return {key: payload.get(key) for key in allowed if key in payload}


def _conversation_tool_artifact_root(context):
    if not isinstance(context, dict):
        return None
    workspace = context.get("conversation_workspace_dir")
    if not isinstance(workspace, str) or not workspace:
        return None
    return Path(workspace) / "tools" / "computer"


def _apply_tool_support_desktop_defaults(action, payload, context):
    if not isinstance(payload, dict):
        return payload
    if not str(action or "").startswith("computer."):
        return payload
    chat_params = context.get("chat_params") if isinstance(context, dict) else {}
    support = chat_params.get("tool_support") if isinstance(chat_params, dict) else {}
    if not isinstance(support, dict) or support.get("app_scoped_desktop_actions") is False:
        return payload
    default_app = str(support.get("default_target_app") or "").strip()
    if not default_app:
        return payload
    if action in {"computer.move", "computer.click"} and _payload_has_explicit_point_reference(payload):
        return payload
    scoped_actions = {
        "computer.screenshot",
        "computer.move",
        "computer.click",
        "computer.type",
        "computer.key",
        "computer.hotkey",
        "computer.scroll",
    }
    if action not in scoped_actions:
        return payload
    next_payload = dict(payload)
    next_payload.setdefault("target", "app")
    next_payload.setdefault("app", default_app)
    next_payload.setdefault("focus", False)
    return next_payload


def _payload_has_explicit_point_reference(payload):
    coordinate_keys = {
        "x",
        "y",
        "point",
        "points",
        "normalized_point",
        "screenshot_path",
        "screenshot_metadata_path",
        "metadata_path",
        "model_image_path",
        "source_path",
    }
    if any(key in payload for key in coordinate_keys):
        return True
    coordinate_space = str(payload.get("coordinate_space") or payload.get("coordinates") or "").strip().lower()
    return coordinate_space in {
        "model_image",
        "screenshot_image",
        "source_image",
        "image",
        "normalized",
        "normalized_1000",
    }


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
    return bool(_tool_value(tool_def, "requires_approval") or _tool_value(tool_def, "write_action"))


def _is_shell_or_git(tool_def):
    action_type = str(_tool_value(tool_def, "action_type") or "")
    category = str(_tool_value(tool_def, "category") or "")
    return action_type == "shell" or category in {"shell", "git"}


def _is_policy_allow_context(context):
    if not isinstance(context, dict):
        return False
    decision = context.get("_tool_permission_decision")
    return isinstance(decision, dict) and decision.get("action") == "allow" and bool(decision.get("allowed"))
