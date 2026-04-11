from __future__ import annotations


def run(context=None, args=None):
    return {"status": "ok", "domain": "ai_client", "args": dict(args or {})}
