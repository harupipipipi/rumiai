"""
Sandbox Handlers

このディレクトリに配置された .py ファイルは自動的にハンドラとして登録されます。

ハンドラのルール:
1. execute(context: dict, args: dict) -> dict 関数を定義
2. オプションで META 辞書を定義（メタ情報）

例:
    def execute(context, args):
        return {"success": True, "data": ...}
    
    META = {
        "requires_scope": True,
        "supports_modes": ["sandbox", "raw"],
        "description": "説明"
    }
"""
