from __future__ import annotations

from typing import List, Optional

from .module_catalog import ModuleCatalog
from .module_state import ModuleStateManager


class DependencyManager:
    def __init__(self, state_manager: Optional[ModuleStateManager] = None) -> None:
        self.catalog = ModuleCatalog(state_manager)

    def resolve_load_order(self) -> List[str]:
        graph = self.catalog.dependency_graph()
        resolved: List[str] = []
        visiting = set()

        def visit(module_id: str) -> None:
            if module_id in resolved:
                return
            if module_id in visiting:
                return
            visiting.add(module_id)
            for dep in graph.get(module_id, []):
                if dep in graph:
                    visit(dep)
            visiting.remove(module_id)
            resolved.append(module_id)

        for module_id in graph:
            visit(module_id)
        return resolved
