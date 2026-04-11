from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List, Optional

from .module_state import ModuleState, ModuleStateManager


class ModuleCatalog:
    def __init__(self, state_manager: Optional[ModuleStateManager] = None) -> None:
        self.state_manager = state_manager or ModuleStateManager()

    def list_modules(self) -> List[Dict[str, Any]]:
        return self.state_manager.list_modules()

    def get_module(self, module_id: str) -> Optional[Dict[str, Any]]:
        for module in self.list_modules():
            if module["module_id"] == module_id:
                return module
        return None

    def summary(self) -> Dict[str, Any]:
        modules = self.list_modules()
        counts = Counter(module["state"] for module in modules)
        return {"total": len(modules), "by_state": dict(counts)}

    def dependency_graph(self) -> Dict[str, List[str]]:
        return {module["module_id"]: list(module.get("dependencies", [])) for module in self.list_modules()}

    def impact_analysis(self, module_id: str) -> Dict[str, Any]:
        modules = self.list_modules()
        graph = self.dependency_graph()
        direct = [mid for mid, deps in graph.items() if module_id in deps]
        indirect: List[str] = []
        queue = list(direct)
        seen = set(direct)
        while queue:
            current = queue.pop(0)
            for mid, deps in graph.items():
                if current in deps and mid not in seen and mid != module_id:
                    seen.add(mid)
                    indirect.append(mid)
                    queue.append(mid)
        return {
            "module_id": module_id,
            "module": self.get_module(module_id),
            "direct_dependents": direct,
            "indirect_dependents": indirect,
            "depends_on": graph.get(module_id, []),
        }

    def impact_map(self) -> Dict[str, List[str]]:
        return self.state_manager.get_impact_map()
