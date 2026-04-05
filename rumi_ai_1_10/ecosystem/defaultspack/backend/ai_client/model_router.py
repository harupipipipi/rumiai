"""
model_router.py - Task-based model/provider routing.

Analyzes incoming requests and routes to the optimal model based on
task type, complexity, cost constraints, and availability.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class RoutingRule:
    name: str
    conditions: Dict[str, Any] = field(default_factory=dict)
    target_provider: str = ""
    target_model: str = ""
    priority: int = 0


class ModelRouter:
    """Routes AI requests to optimal model based on task analysis."""

    def __init__(self):
        self._rules: List[RoutingRule] = []

    def add_rule(self, rule: RoutingRule) -> None:
        self._rules.append(rule)
        self._rules.sort(key=lambda r: r.priority, reverse=True)

    def route(self, task_info: Dict[str, Any]) -> Optional[Dict[str, str]]:
        for rule in self._rules:
            if self._matches(rule, task_info):
                return {
                    "provider_id": rule.target_provider,
                    "model_id": rule.target_model,
                    "rule_name": rule.name,
                }
        return None

    def _matches(self, rule: RoutingRule, task_info: Dict[str, Any]) -> bool:
        for key, value in rule.conditions.items():
            if task_info.get(key) != value:
                return False
        return True
