from __future__ import annotations
from typing import Any, Dict

def run(context: Dict[str, Any]) -> None:
    ir = context.get("interface_registry")
    if ir:
        ir.register("foundation.http.routes", {"version": "1.0"}, meta={"component": "foundation_v1"})
