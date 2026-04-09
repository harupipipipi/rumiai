"""defaults.prompt.render — プロンプトレンダリング handler

入力:
    {"prompt_id": str, "variables": dict}
    または
    {"template": str, "variables": dict}

    prompt_id 指定時は PromptManager から取得してレンダリングする。
    template 直指定時はそのままレンダリングする。
    両方指定された場合は prompt_id を優先する。

出力:
    {"status": "ok", "data": {"rendered": str, "prompt_id": str | null}}
"""

from blocks._common import ok, error
from domain.prompt.manager import get_manager
from domain.prompt.renderer import render


def run(input_data: dict, context: dict) -> dict:
    prompt_id = input_data.get("prompt_id")
    template = input_data.get("template")
    variables = input_data.get("variables") or {}

    # prompt_id 優先
    if prompt_id:
        manager = get_manager()
        prompt = manager.get_prompt(prompt_id)
        if prompt is None:
            return error(
                f"Prompt not found: {prompt_id}",
                "NOT_FOUND",
            )
        template = prompt["content"]
    elif template is None:
        return error(
            "Either 'prompt_id' or 'template' is required",
            "INVALID_INPUT",
        )

    rendered = render(template, variables)
    return ok({"rendered": rendered, "prompt_id": prompt_id})
