"""
dependency_manager.py - Module dependency graph and resolution.

Tracks which modules depend on which others. When a module fails,
finds all transitively-affected modules and marks them degraded.
"""

from __future__ import annotations

import logging
import threading
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


@dataclass
class ModuleDependency:
    """Dependency declaration for a module."""
    module_id: str
    required: List[str] = field(default_factory=list)  # hard deps
    optional: List[str] = field(default_factory=list)   # soft deps
    provides: List[str] = field(default_factory=list)    # capabilities
    pack_id: str = "defaultspack"


class DependencyManager:
    """
    Manages inter-module dependency graph.
    Thread-safe.
    """

    def __init__(self):
        self._lock = threading.RLock()
        self._deps: Dict[str, ModuleDependency] = {}
        self._provides_index: Dict[str, Set[str]] = {}  # capability -> modules

    def register(self, dep: ModuleDependency) -> None:
        with self._lock:
            self._deps[dep.module_id] = dep
            for cap in dep.provides:
                self._provides_index.setdefault(cap, set()).add(dep.module_id)

    def unregister(self, module_id: str) -> None:
        with self._lock:
            dep = self._deps.pop(module_id, None)
            if dep:
                for cap in dep.provides:
                    s = self._provides_index.get(cap)
                    if s:
                        s.discard(module_id)

    def get_required_deps(self, module_id: str) -> List[str]:
        with self._lock:
            dep = self._deps.get(module_id)
            return list(dep.required) if dep else []

    def get_optional_deps(self, module_id: str) -> List[str]:
        with self._lock:
            dep = self._deps.get(module_id)
            return list(dep.optional) if dep else []

    def get_dependents(self, module_id: str) -> List[str]:
        """Find all modules that depend on module_id."""
        with self._lock:
            result = []
            for mid, dep in self._deps.items():
                if module_id in dep.required or module_id in dep.optional:
                    result.append(mid)
            return result

    def get_transitive_dependents(self, module_id: str) -> List[str]:
        """BFS to find all transitively affected modules."""
        with self._lock:
            visited: Set[str] = set()
            queue = deque([module_id])
            while queue:
                current = queue.popleft()
                for dep_mid in self.get_dependents(current):
                    if dep_mid not in visited:
                        visited.add(dep_mid)
                        queue.append(dep_mid)
            return list(visited)

    def check_satisfied(self, module_id: str, enabled_modules: Set[str]) -> Dict[str, Any]:
        """Check if all required deps of a module are satisfied."""
        with self._lock:
            dep = self._deps.get(module_id)
            if dep is None:
                return {"satisfied": True, "missing": []}
            missing = [r for r in dep.required if r not in enabled_modules]
            return {
                "satisfied": len(missing) == 0,
                "missing": missing,
            }

    def resolve_load_order(self) -> List[str]:
        """Topological sort of all registered modules by their required deps."""
        with self._lock:
            in_degree: Dict[str, int] = {m: 0 for m in self._deps}
            adj: Dict[str, List[str]] = {m: [] for m in self._deps}

            for mid, dep in self._deps.items():
                for req in dep.required:
                    if req in self._deps:
                        adj[req].append(mid)
                        in_degree[mid] += 1

            queue = deque(sorted(m for m in in_degree if in_degree[m] == 0))
            result: List[str] = []

            while queue:
                node = queue.popleft()
                result.append(node)
                for neighbor in sorted(adj.get(node, [])):
                    in_degree[neighbor] -= 1
                    if in_degree[neighbor] == 0:
                        queue.append(neighbor)

            # Append cyclic modules at end
            remaining = [m for m in self._deps if m not in set(result)]
            if remaining:
                logger.warning("Circular dependency detected among: %s", remaining)
                result.extend(sorted(remaining))

            return result

    def get_catalog(self) -> Dict[str, Dict[str, Any]]:
        """Return full dependency catalog."""
        with self._lock:
            catalog = {}
            for mid, dep in self._deps.items():
                catalog[mid] = {
                    "module_id": mid,
                    "required": list(dep.required),
                    "optional": list(dep.optional),
                    "provides": list(dep.provides),
                    "pack_id": dep.pack_id,
                    "dependents": self.get_dependents(mid),
                }
            return catalog

    def get_impact_analysis(self, module_id: str) -> Dict[str, Any]:
        """What happens if module_id goes down?"""
        with self._lock:
            affected = self.get_transitive_dependents(module_id)
            return {
                "module_id": module_id,
                "direct_dependents": self.get_dependents(module_id),
                "transitive_dependents": affected,
                "total_affected": len(affected),
            }
