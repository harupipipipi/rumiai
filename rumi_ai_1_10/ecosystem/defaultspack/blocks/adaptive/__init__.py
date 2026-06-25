from __future__ import annotations

from domain.adaptive.service import dispatch


def run(args, context=None):
    operation = str((args or {}).get("operation") or "")
    return dispatch(operation, args or {}, context or {})
