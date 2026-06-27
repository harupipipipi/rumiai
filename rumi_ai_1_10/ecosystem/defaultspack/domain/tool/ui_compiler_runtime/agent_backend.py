from __future__ import annotations

from typing import Any, Protocol

from domain.ui_compiler import UIAgentResult, UIAgentTask


class UIAgentBackend(Protocol):
    def run_task(self, task: UIAgentTask, context: dict[str, Any] | None = None) -> UIAgentResult:
        ...
