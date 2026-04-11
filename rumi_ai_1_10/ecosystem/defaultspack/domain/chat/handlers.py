from __future__ import annotations


def run(context=None, args=None):
    return {"status": "ok", "domain": "chat", "args": dict(args or {})}
