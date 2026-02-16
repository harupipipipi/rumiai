from __future__ import annotations
from typing import Callable, Optional, Set, Any

def route_exists(app, rule: str, methods: Optional[Set[str]] = None) -> bool:
    want = set(m.upper() for m in (methods or set()))
    for r in app.url_map.iter_rules():
        if str(r.rule) != rule:
            continue
        if want:
            existing = set(m.upper() for m in (r.methods or set()))
            if not want.issubset(existing):
                continue
        return True
    return False

def safe_add_url_rule(app, rule: str, endpoint: str, view_func: Callable[..., Any], methods: Set[str]) -> bool:
    if route_exists(app, rule, methods):
        return False
    app.add_url_rule(rule, endpoint=endpoint, view_func=view_func, methods=sorted(list(methods)))
    return True
