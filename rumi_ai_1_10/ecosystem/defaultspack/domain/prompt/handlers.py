from __future__ import annotations


def run(context=None, args=None):
    return {"status": "ok", "domain": "prompt", "args": dict(args or {})}
