from __future__ import annotations

from .approve import run as approve_run
from .deny import run as deny_run


def run(input_data, context=None):
    payload = dict(input_data or {})
    decision = str(payload.get("decision") or payload.get("action") or "").lower()
    if decision in {"approve", "approved", "allow"}:
        payload["scope"] = payload.get("scope") or "once"
        return approve_run(payload, context)
    if decision in {"approve_session", "approve_for_session"}:
        payload["scope"] = "session"
        return approve_run(payload, context)
    return deny_run(payload, context)
