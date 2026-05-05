from __future__ import annotations

from .approve import run as _run


def run(input_data, context=None):
    input_data = dict(input_data or {})
    input_data["scope"] = "once"
    return _run(input_data, context)
