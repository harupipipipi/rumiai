from domain.tool.registry import ToolRegistry
from domain.tool.mcp_client import McpClient


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

    def _execute_local(self, tool_name, arguments, context):
        """
        ローカルツール実行（最小動作版: 固定レスポンスを返す）
        """
        if tool_name == "web_search":
            query = arguments.get("query", "")
            return {
                "result": "Search results for: {}".format(query),
                "is_error": False,
                "widget": None
            }
        elif tool_name == "calculator":
            expression = arguments.get("expression", "")
            return {
                "result": "Calculated: {} = (stub)".format(expression),
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
