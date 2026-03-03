#!/usr/bin/env python3
"""
list - Core function entry point (stub).

This is a core function. It is executed in-process by the kernel.
This file exists to satisfy pack_validator checks.
The stdin/stdout JSON interface below is a placeholder for potential
future migration to a user function execution model.
"""

import json
import sys


def main():
    """Stub entry point for core function 'list'."""
    try:
        raw = sys.stdin.read()
        if raw.strip():
            request = json.loads(raw)
        else:
            request = {}
    except json.JSONDecodeError:
        request = {}

    response = {
        "status": "error",
        "message": (
            "This is a core function. "
            "It is executed in-process by the kernel. "
            "Direct invocation via stdin/stdout is not supported."
        ),
        "function_id": "list",
    }

    json.dump(response, sys.stdout)
    sys.stdout.write("\n")
    sys.stdout.flush()


if __name__ == "__main__":
    main()
