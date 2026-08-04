"""Authoritative Pack-manifest classification shared by production loaders."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Literal

ManifestAuthority = Literal[
    "legacy-authoritative",
    "v3-authoritative",
    "modern-only",
]

CATALOG_PATH = (
    Path(__file__).parents[1] / "schemas" / "manifest_authority.v1.json"
)
_VALID_AUTHORITIES = {
    "legacy-authoritative",
    "v3-authoritative",
    "modern-only",
}


class ManifestAuthorityError(ValueError):
    """Raised when Pack authority metadata is missing or inconsistent."""


@lru_cache(maxsize=1)
def load_manifest_authority_catalog() -> dict[str, ManifestAuthority]:
    """Load and validate the repository Pack authority catalog."""
    try:
        payload = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ManifestAuthorityError(
            f"manifest authority catalog is unreadable: {exc}"
        ) from exc
    if not isinstance(payload, dict) or payload.get("version") != 1:
        raise ManifestAuthorityError("manifest authority catalog version must be 1")
    packs = payload.get("packs")
    if not isinstance(packs, dict):
        raise ManifestAuthorityError("manifest authority catalog packs must be an object")
    result: dict[str, ManifestAuthority] = {}
    for pack_id, authority in packs.items():
        if not isinstance(pack_id, str) or authority not in _VALID_AUTHORITIES:
            raise ManifestAuthorityError(
                f"invalid manifest authority classification: {pack_id!r}={authority!r}"
            )
        result[pack_id] = authority
    return result


def repository_manifest_authority(pack_id: str) -> ManifestAuthority:
    """Return the explicit authority for a shipped Pack or fail closed."""
    authority = load_manifest_authority_catalog().get(pack_id)
    if authority is None:
        raise ManifestAuthorityError(
            f"Pack '{pack_id}' is not classified in manifest authority catalog"
        )
    return authority


def validate_repository_manifest_authority(ecosystem_dir: Path) -> None:
    """Require an exact one-to-one classification for shipped Pack roots."""
    from .paths import discover_pack_locations

    discovered = {
        location.pack_id
        for location in discover_pack_locations(str(ecosystem_dir))
    }
    classified = set(load_manifest_authority_catalog())
    missing = sorted(discovered - classified)
    stale = sorted(classified - discovered)
    if missing or stale:
        raise ManifestAuthorityError(
            f"manifest authority catalog mismatch: missing={missing}, stale={stale}"
        )

