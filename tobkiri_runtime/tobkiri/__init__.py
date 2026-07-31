"""Canonical Tobkiri runtime package."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("tobkiri-runtime")
except PackageNotFoundError:
    try:
        # Stacked source-layout upgrades can run against Phase 3A/3B editable metadata.
        __version__ = version("rumi-ai")
    except PackageNotFoundError:
        # Keep source-tree CLI execution usable before editable installation.
        __version__ = "1.10.0"
