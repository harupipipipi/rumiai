from __future__ import annotations

from backend.tool.permission_policy import (
    get_tool_permission_policy_manager,
)
from domain.tool.registry import ToolRegistry


class PermissionChecker:
    """ツール実行権限チェッカー。永続化されたポリシーを参照する。"""

    def __init__(self, registry=None):
        self._registry = registry or ToolRegistry()

    def decide(self, tool_name, context=None, arguments=None, tool_def=None):
        manager = get_tool_permission_policy_manager()
        return manager.decide(
            tool_name,
            tool_def=tool_def or self._registry.get(tool_name),
            arguments=arguments,
            context=context,
        )

    def check(self, tool_name, context, arguments=None, tool_def=None):
        decision = self.decide(
            tool_name,
            context=context,
            arguments=arguments,
            tool_def=tool_def,
        )
        return bool(decision.get("allowed", False))
