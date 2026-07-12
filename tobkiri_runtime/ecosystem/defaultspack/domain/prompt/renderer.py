"""Prompt Renderer — テンプレート内の {{variable}} を単純置換する。

仕様:
    - 構文: {{変数名}} で単純置換
    - ドット記法: {{context.total_tokens}} のようなドット付き変数もサポート
    - スペース許容: {{ name }} も有効
    - 存在しない変数はそのまま残す
    - 再帰的な変数解決はしない（1パスのみ）
"""

import re

# {{variable}} または {{context.xxx}} にマッチ。中のスペースは許容する。
_VARIABLE_PATTERN = re.compile(r"\{\{\s*([\w.]+)\s*\}\}")


def render(template: str, variables: dict | None = None) -> str:
    """テンプレート内の {{variable}} を *variables* の値で置換する。

    ドット記法キー（例: "context.total_tokens"）もフラットな dict キーとして
    そのまま照合する。

    Args:
        template:  置換対象のテンプレート文字列
        variables: 変数名→値 の辞書。None / 空なら置換せずそのまま返す。
                   ドット記法キーはそのまま文字列キーとして格納する。
                   例: {"context.total_tokens": 1234, "name": "Alice"}

    Returns:
        レンダリング済み文字列
    """
    if not variables:
        return template

    def _replace(match: re.Match) -> str:
        key = match.group(1)
        if key in variables:
            return str(variables[key])
        # 存在しない変数はそのまま残す
        return match.group(0)

    return _VARIABLE_PATTERN.sub(_replace, template)
