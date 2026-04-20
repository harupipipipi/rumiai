"""Compatibility shim for legacy frontend setup location.

The lifecycle executor now loads setup.py from components/frontend/, so this
file intentionally does nothing beyond documenting the migration.
"""


def run(context=None):
    return {
        "status": "ok",
        "message": "frontend setup moved to components/frontend/setup.py",
    }
