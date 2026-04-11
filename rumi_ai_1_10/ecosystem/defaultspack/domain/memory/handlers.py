from __future__ import annotations


def run(context=None, args=None):
    return {"status": "ok", "domain": "memory", "args": dict(args or {})}
