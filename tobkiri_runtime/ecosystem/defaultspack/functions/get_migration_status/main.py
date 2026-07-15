from __future__ import annotations

from ecosystem.defaultspack.backend.migration.migrator import get_defaults_migrator


def run(context, args):
    return get_defaults_migrator().status()
