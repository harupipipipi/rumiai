"""Canonical Tobkiri runtime package."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("tobkiri-runtime")
except PackageNotFoundError:
    # Stacked source-layout upgrades can run against Phase 3A/3B editable metadata.
    __version__ = version("rumi-ai")
