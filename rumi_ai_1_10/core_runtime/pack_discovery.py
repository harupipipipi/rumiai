"""Compatibility wrapper for managed pack discovery."""

from __future__ import annotations

from .paths import PackLocation, discover_pack_locations, find_ecosystem_json

__all__ = ["PackLocation", "discover_pack_locations", "find_ecosystem_json"]
