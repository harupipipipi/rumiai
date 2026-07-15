from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, List

logger = logging.getLogger(__name__)

UI_ROOTS = [Path(__file__).parent / "ui", Path(__file__).parent / "ui_shell"]


def build_frontend_dependency_graph() -> Dict[str, List[str]]:
    graph: Dict[str, List[str]] = {}
    for root in UI_ROOTS:
        if not root.is_dir():
            continue
        spec_paths = []
        root_spec = root / "module.json"
        if root_spec.is_file():
            spec_paths.append(root_spec)
        for child in sorted(root.iterdir()):
            child_spec = child / "module.json"
            if child.is_dir() and child_spec.is_file():
                spec_paths.append(child_spec)
        for spec_path in spec_paths:
            try:
                spec = json.loads(spec_path.read_text(encoding="utf-8"))
            except Exception as exc:
                logger.warning("Failed to parse %s: %s", spec_path, exc)
                continue
            mid = str(spec.get("module_id", spec_path.parent.name))
            graph[mid] = [str(dep) for dep in spec.get("dependencies", []) if isinstance(dep, str)]
    return graph
