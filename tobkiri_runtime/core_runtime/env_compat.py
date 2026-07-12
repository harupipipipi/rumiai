"""Canonical Tobkiri environment variables with legacy Rumi fallbacks."""

from __future__ import annotations

import logging
import os
from typing import Mapping

_warned: set[tuple[str, str]] = set()


def read_migrated_env(
    canonical_name: str,
    legacy_name: str,
    default: str | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    logger: logging.Logger | None = None,
) -> str | None:
    source = os.environ if environ is None else environ
    canonical = source.get(canonical_name)
    if canonical is not None:
        return canonical
    legacy = source.get(legacy_name)
    if legacy is None:
        return default
    warning_key = (canonical_name, legacy_name)
    if warning_key not in _warned:
        _warned.add(warning_key)
        (logger or logging.getLogger(__name__)).warning(
            "%s is deprecated; use %s instead (value redacted)",
            legacy_name,
            canonical_name,
        )
    return legacy


def reset_migration_warnings_for_tests() -> None:
    _warned.clear()
