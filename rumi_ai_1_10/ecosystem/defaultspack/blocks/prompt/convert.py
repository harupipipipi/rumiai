"""defaults.prompt.convert — tool ↔ prompt conversion helper

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
        passive prompt 方針では authoring 経路として無効。
        prompt は tool/provider/permission を動かさず、必要な場合は function/flow から
        defaults.prompt.render を明示的に呼ぶ。

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
        return error(
            "Prompt-to-tool authoring is disabled. Use a rumi_function/capability tool "
            "facade or call defaults.prompt.render from a flow.",
            "PROMPT_TOOL_AUTHORING_DISABLED",
        )

    return error("Unexpected conversion path", "INTERNAL")
