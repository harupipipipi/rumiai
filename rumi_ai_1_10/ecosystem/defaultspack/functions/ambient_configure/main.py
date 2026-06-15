from __future__ import annotations

from domain.function_runtime.dispatcher import run_defaultspack_function


def run(args, context):
    return run_defaultspack_function("ambient_configure", args, context)
