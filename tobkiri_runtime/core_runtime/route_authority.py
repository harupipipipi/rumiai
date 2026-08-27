"""Shared server-owned route retirement authority."""

from __future__ import annotations

from typing import Final


RETIRED_API_ROOTS: Final[frozenset[str]] = frozenset(
    {
        "auth",
        "authority",
        "blocks",
        "capabilities",
        "containers",
        "desktop",
        "flows",
        "executors",
        "functions",
        "graphs",
        "integrations",
        "mobile",
        "network",
        "nodes",
        "packs",
        "panel",
        "pip",
        "privileges",
        "profiles",
        "routes",
        "runtime",
        "secrets",
        "stores",
        "units",
        "viewer",
        "webhooks",
    }
)

RETIRED_FRONTEND_ROUTES: Final[tuple[str, ...]] = (
    "/api/authority/events",
    "/api/packs/scan",
    "/api/routes/reload",
    "/api/runtime/available",
)


def is_retired_api_path(path: str) -> bool:
    """Return whether *path* belongs to the server-owned retired API roots."""

    parts = str(path or "").strip("/").split("/")
    return (
        len(parts) >= 2
        and parts[0] == "api"
        and parts[1] in RETIRED_API_ROOTS
    )


__all__ = [
    "RETIRED_API_ROOTS",
    "RETIRED_FRONTEND_ROUTES",
    "is_retired_api_path",
]
