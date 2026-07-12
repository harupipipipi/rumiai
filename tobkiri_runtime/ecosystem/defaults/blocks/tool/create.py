import sys, os; sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..")); from _common import ok, error, gen_id, timestamp
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from domain.tool.registry import ToolRegistry
from domain.tool.builder import generate_handler_code_with_ai


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

    # handler_code が null / 未指定の場合は AI で生成
    if handler_code is None:
        model = input_data.get("model")
        handler_code = generate_handler_code_with_ai(
            name, description, parameters, model=model
        )

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
    }

    try:
        registered = registry.register_dynamic(tool_def, handler_code=handler_code)
    except Exception as exc:
        return error("Failed to register tool: {}".format(exc), "REGISTER_ERROR")

    return ok({
        "tool_id": registered["tool_id"],
        "name": registered["name"],
        "summary": registered["summary"],
        "handler_code": handler_code,
        "created_at": registered.get("created_at", ""),
    })
