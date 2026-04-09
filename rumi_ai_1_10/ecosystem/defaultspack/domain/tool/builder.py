"""
domain.tool.builder — AI によるツール handler コード生成ヘルパー。
JSON Schema からスケルトンを生成し、AIClient 経由で完全なコードを生成する。
"""
import json
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from domain.ai_client.client import AIClient


def generate_skeleton(name, description, parameters):
    """
    JSON Schema (parameters) からハンドラコードのスケルトンを生成する。
    戻り値: Python コード文字列
    """
    props = parameters.get("properties", {})
    required = parameters.get("required", [])

    arg_lines = []
    for prop_name, prop_schema in props.items():
        prop_type = prop_schema.get("type", "any")
        is_required = prop_name in required
        req_mark = " (required)" if is_required else " (optional)"
        arg_lines.append("    # {}: {}{}"
                         .format(prop_name, prop_type, req_mark))

    args_doc = "\n".join(arg_lines) if arg_lines else "    # (no parameters)"

    skeleton = '''def handler(arguments, context):
    """
    {description}

    arguments keys:
{args_doc}

    Returns: dict with "result" (str), "is_error" (bool), "widget" (dict|None)
    """
    # TODO: implement
    return {{
        "result": "{name} executed successfully",
        "is_error": False,
        "widget": None,
    }}
'''.format(description=description, args_doc=args_doc, name=name)

    return skeleton


def generate_handler_code_with_ai(name, description, parameters, model=None):
    """
    AI を使って完全な handler コードを生成する。
    model: 使用する AI モデル文字列（None の場合は利用可能な最初の非 stub プロバイダーを使用）
    戻り値: Python コード文字列
    """
    client = AIClient()

    if model is None:
        providers = client.list_providers()
        for p in providers:
            if p["id"] != "stub":
                models = client.list_models(provider=p["id"])
                if models:
                    model = models[0]["id"]
                    break
        if model is None:
            # AI プロバイダーが利用不可ならスケルトンを返す
            return generate_skeleton(name, description, parameters)

    params_json = json.dumps(parameters, ensure_ascii=False, indent=2)

    messages = [
        {
            "role": "system",
            "content": (
                "You are a tool handler code generator for the rumiai ecosystem. "
                "Generate a Python function named 'handler' that takes two arguments: "
                "'arguments' (dict) and 'context' (dict). "
                "The function must return a dict with keys: "
                "'result' (str), 'is_error' (bool), 'widget' (dict or None). "
                "Output ONLY the Python code, no markdown fences, no explanation."
            ),
        },
        {
            "role": "user",
            "content": (
                "Generate a handler function for a tool with the following spec:\n\n"
                "Name: {name}\n"
                "Description: {description}\n"
                "Parameters (JSON Schema):\n{params_json}\n\n"
                "The function signature must be: def handler(arguments, context):\n"
                "Return a dict with 'result', 'is_error', 'widget' keys."
            ).format(name=name, description=description, params_json=params_json),
        },
    ]

    try:
        result = client.complete(model, messages)
        content = ""
        if isinstance(result, dict):
            # provider returns {"content": "..."} or {"choices": [...]}
            content = result.get("content", "")
            if not content and "choices" in result:
                choices = result.get("choices", [])
                if choices:
                    msg = choices[0].get("message", {})
                    content = msg.get("content", "")
        if content and "def handler" in content:
            # strip markdown fences if present
            lines = content.strip().splitlines()
            cleaned = []
            in_fence = False
            for line in lines:
                if line.strip().startswith("```"):
                    in_fence = not in_fence
                    continue
                cleaned.append(line)
            return "\n".join(cleaned)
        # AI の出力が不正な場合はスケルトンにフォールバック
        return generate_skeleton(name, description, parameters)
    except Exception:
        return generate_skeleton(name, description, parameters)
