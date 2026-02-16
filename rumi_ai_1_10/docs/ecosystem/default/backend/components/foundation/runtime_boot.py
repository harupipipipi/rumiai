from __future__ import annotations
from typing import Any, Dict, Set

_registered_endpoints: Set[str] = set()


def safe_add_url_rule(app, rule: str, endpoint: str, view_func, methods: set) -> bool:
    """
    重複登録を防ぐFlaskルート追加
    
    Args:
        app: Flaskアプリケーション
        rule: URLルール (例: "/api/chats")
        endpoint: エンドポイント名 (例: "io_http_api.chats_list")
        view_func: ビュー関数
        methods: HTTPメソッドのセット (例: {"GET", "POST"})
    
    Returns:
        登録成功した場合True、既に登録済みの場合False
    """
    if endpoint in _registered_endpoints:
        return False
    if endpoint in getattr(app, 'view_functions', {}):
        return False
    try:
        app.add_url_rule(rule, endpoint, view_func, methods=list(methods))
        _registered_endpoints.add(endpoint)
        return True
    except Exception:
        return False


def run(context: Dict[str, Any]) -> None:
    """
    Foundationコンポーネントのランタイム初期化
    
    InterfaceRegistryに以下を登録:
    - foundation.safe_add_url_rule: 重複防止付きルート追加関数
    - foundation.http.routes: HTTPルーティング関連のメタ情報
    
    Args:
        context: Kernelから渡されるコンテキスト
    """
    ir = context.get("interface_registry")
    if ir:
        ir.register(
            "foundation.safe_add_url_rule",
            safe_add_url_rule,
            meta={"component": "foundation_v1"}
        )
        ir.register(
            "foundation.http.routes",
            {"version": "1.0", "safe_add_url_rule": safe_add_url_rule},
            meta={"component": "foundation_v1"}
        )
