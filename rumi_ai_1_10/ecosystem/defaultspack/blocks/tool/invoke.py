import sys, os; sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..")); from _common import ok, error, gen_id, timestamp
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from domain.tool.permission_checker import PermissionChecker
from domain.tool.executor import ToolExecutor
from domain.tool.registry import ToolRegistry


def run(input_data, context):
    """defaults.tool.invoke — ツールを実行する"""
    tool_name = input_data.get("tool_name")
    if not tool_name:
        return error("tool_name is required", "MISSING_PARAM")

    arguments = input_data.get("arguments")
    if arguments is None:
        return error("arguments is required", "MISSING_PARAM")

    registry = ToolRegistry()
    tool_def = registry.get(tool_name)
    if tool_def is None:
        for item in registry.list_tools():
            if item.get("name") == tool_name:
                tool_def = item
                tool_name = item.get("tool_id", tool_name)
                break

    checker = PermissionChecker(registry=registry)
    decision = checker.decide(tool_name, context=context, arguments=arguments, tool_def=tool_def)
    if not decision.get("allowed", False):
        return {
            "status": "error",
            "error": {
                "code": "PERMISSION_DENIED",
                "message": "Permission denied for tool: {}".format(tool_name),
                "details": {
                    "action": decision.get("action"),
                    "matched_by": decision.get("matched_by"),
                    "matched_value": decision.get("matched_value"),
                    "reason": decision.get("reason"),
                },
            },
        }

    executor = ToolExecutor()
    try:
        result = executor.execute(tool_name, arguments, context)
    except Exception as exc:
        return error("Tool execution failed: {}".format(exc), "EXEC_ERROR")

    return ok({
        "result": result.get("result", ""),
        "is_error": result.get("is_error", False),
        "widget": result.get("widget"),
        "tool_name": tool_name,
        "permission": {
            "action": decision.get("action", "allow"),
            "allowed": decision.get("allowed", False),
            "matched_by": decision.get("matched_by"),
            "matched_value": decision.get("matched_value"),
        },
    })
