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
        elif tool_name == "browser_computer":
            from domain.tool.browser_computer import BrowserComputerController

            policy = policy_from_context(context if isinstance(context, dict) else {})
            result = BrowserComputerController().run(
                str(arguments.get("action", "browser.session")),
                dict(arguments.get("payload") or {}),
                yolo_mode=bool(policy.get("yolo_mode")),
            )
            return {
                "result": str(result),
                "is_error": False,
                "widget": {"type": "browser_computer", **result}
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
