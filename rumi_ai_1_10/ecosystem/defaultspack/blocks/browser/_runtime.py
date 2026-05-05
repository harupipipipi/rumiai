from __future__ import annotations

from pathlib import Path
from typing import Any

from domain.browser.profiles import BrowserProfileManager
from domain.browser.sessions import BrowserSessionManager
from domain.browser.snapshots import SnapshotRefStore


def browser_root(input_data: dict[str, Any] | None = None, context: dict[str, Any] | None = None) -> Path | None:
    input_data = input_data if isinstance(input_data, dict) else {}
    context = context if isinstance(context, dict) else {}
    value = input_data.get("browser_root") or context.get("browser_root") or context.get("_browser_root")
    return Path(value) if value else None


def profile_manager(input_data: dict[str, Any] | None = None, context: dict[str, Any] | None = None) -> BrowserProfileManager:
    return BrowserProfileManager(browser_root(input_data, context))


def session_manager(input_data: dict[str, Any] | None = None, context: dict[str, Any] | None = None) -> BrowserSessionManager:
    root = browser_root(input_data, context)
    return BrowserSessionManager(root, profile_manager=BrowserProfileManager(root))


def ref_store(input_data: dict[str, Any] | None = None, context: dict[str, Any] | None = None) -> SnapshotRefStore:
    return SnapshotRefStore(browser_root(input_data, context))
