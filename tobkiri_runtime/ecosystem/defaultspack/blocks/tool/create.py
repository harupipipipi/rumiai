import sys, os; sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..")); from _common import ok, error, gen_id, timestamp
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from domain.tool.registry import ToolRegistry
from domain.tool.builder import generate_handler_code_with_ai
from domain.tool.runtime_creator import RuntimeToolCreator
from blocks.tool._safety import (
    approved_or_request,
    record_tool_attempt,
    record_tool_execution,
    record_tool_failure,
)


OPERATION = "tool.create"
RISK = "high"


def run(input_data, context):
    """defaults.tool.create — 動的ツールを作成・登録する"""
    name = input_data.get("name")
    if not name:
        return error("name is required", "MISSING_PARAM")

    description = input_data.get("description", "")
    parameters = input_data.get("parameters")
    if parameters is None:
        return error("parameters (JSON Schema) is required", "MISSING_PARAM")
    if not isinstance(parameters, dict):
        return error("parameters must be a JSON Schema object", "INVALID_PARAM")

    handler_code = input_data.get("handler_code")

    registry = ToolRegistry()

    # 既に同名のツールが存在するか確認
    existing = registry.get(name)
    if existing is not None:
        return error("Tool '{}' already exists".format(name), "ALREADY_EXISTS")

    record_tool_attempt(OPERATION, RISK, input_data)
    approval = approved_or_request(input_data, context, OPERATION, RISK)
    if approval is not None:
        return approval

    # handler_code が null / 未指定の場合は AI で生成
    if handler_code is None:
        model = input_data.get("model")
        try:
            handler_code = generate_handler_code_with_ai(
                name, description, parameters, model=model
            )
        except Exception as exc:
            record_tool_failure(OPERATION, RISK, input_data, str(exc), tool_name=name)
            return error("Failed to generate handler_code: {}".format(exc), "GENERATION_ERROR")

    validation = RuntimeToolCreator().validate_tool_definition(
        {
            "name": name,
            "description": description,
            "parameters": parameters,
            "handler_code": handler_code,
        }
    )
    if not validation.get("valid"):
        record_tool_failure(OPERATION, RISK, input_data, "; ".join(validation.get("errors", [])), tool_name=name)
        return error("Tool validation failed: {}".format("; ".join(validation.get("errors", []))), "VALIDATION_ERROR")

    tool_def = {
        "tool_id": name,
        "name": name,
        "summary": description,
        "tags": input_data.get("tags", ["dynamic", "user-created"]),
        "schema": {
            "parameters": parameters,
        },
        "execution": {"type": "dynamic"},
        "created_at": timestamp(),
        "requires_approval": True,
        "approval_policy": "user_approved",
        "metadata": {
            "source": "tool_create",
            "agent_callable": True,
            "created_by": str((context or {}).get("agent_id") or (context or {}).get("run_source") or "user"),
            "validation": validation,
        },
    }

    try:
        registered = registry.register_dynamic(tool_def, handler_code=handler_code)
    except Exception as exc:
        record_tool_failure(OPERATION, RISK, input_data, str(exc), tool_name=name)
        return error("Failed to register tool: {}".format(exc), "REGISTER_ERROR")

    record_tool_execution(OPERATION, RISK, input_data, tool_name=registered["tool_id"])
    return ok({
        "tool_id": registered["tool_id"],
        "name": registered["name"],
        "summary": registered["summary"],
        "handler_code": handler_code,
        "created_at": registered.get("created_at", ""),
        "validation": validation,
    })
