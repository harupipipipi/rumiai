"""defaults.prompt.convert — tool ↔ prompt 相互変換 handler

入力:
    {
        "source_type": "tool" | "prompt",
        "source_name": str,
        "target_type": "tool" | "prompt"
    }

変換ルール:
    tool → prompt:
        tool の parameters を変数に、description をテンプレート本文のヘッダに。
    prompt → tool:
        テンプレートの変数を parameters に、本文を description に。
        P2-1: register_dynamic() を使って実際にツールとして登録し、
              execution.type="prompt" でテンプレート本文を実行できるようにする。

出力:
    {"status": "ok", "data": {"result": {...}, "target_type": str}}
"""

from blocks._common import ok, error
from domain.prompt.manager import get_manager
from domain.prompt.template import PromptTemplate
from domain.tool.registry import ToolRegistry


def run(input_data: dict, context: dict) -> dict:
    source_type = input_data.get("source_type", "")
    source_name = input_data.get("source_name", "")
    target_type = input_data.get("target_type", "")

    if source_type not in ("tool", "prompt"):
        return error(
            "'source_type' must be 'tool' or 'prompt'",
            "INVALID_INPUT",
        )
    if target_type not in ("tool", "prompt"):
        return error(
            "'target_type' must be 'tool' or 'prompt'",
            "INVALID_INPUT",
        )
    if not source_name:
        return error("'source_name' is required", "INVALID_INPUT")
    if source_type == target_type:
        return error(
            "source_type and target_type must differ",
            "INVALID_INPUT",
        )

    # ---- tool → prompt ----
    if source_type == "tool" and target_type == "prompt":
        registry = ToolRegistry()
        tool_def = registry.get(source_name)
        if tool_def is None:
            return error(
                f"Tool not found: {source_name}",
                "NOT_FOUND",
            )
        template = PromptTemplate.from_tool_schema(tool_def)
        manager = get_manager()
        prompt = manager.create_from_template(template)
        return ok({"result": prompt, "target_type": "prompt"})

    # ---- prompt → tool ----
    if source_type == "prompt" and target_type == "tool":
        manager = get_manager()
        template = manager.to_template(source_name)
        if template is None:
            return error(
                f"Prompt not found: {source_name}",
                "NOT_FOUND",
            )
        tool_schema = template.to_tool_schema()

        # P2-1: register_dynamic() を使って実際にツールとして登録する。
        # execution.type="prompt" のツールは executor の _execute_prompt() で実行される。
        # handler_code は不要（prompt ベースの実行パスを使う）ため None。
        registry = ToolRegistry()
        registry.register_dynamic(tool_schema, handler_code=None)

        return ok({"result": tool_schema, "target_type": "tool"})

    return error("Unexpected conversion path", "INTERNAL")
