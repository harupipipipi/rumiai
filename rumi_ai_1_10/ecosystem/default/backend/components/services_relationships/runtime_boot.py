from __future__ import annotations
from typing import Any, Dict

def run(context: Dict[str, Any]) -> None:
    ir = context.get("interface_registry")
    if not ir:
        return
    from relationship_manager import RelationshipManager
    ir.register("service.relationships", RelationshipManager(), meta={"component": "services_relationships_v1"})
