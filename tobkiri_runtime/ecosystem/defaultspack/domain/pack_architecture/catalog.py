"""Read-only catalog loading for defaultspack-owned v4 pack assets."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from .errors import CatalogError
from .model import PackDefinition


DEFAULT_ASSETS_ROOT = Path(__file__).resolve().parent / "assets"


class PackCatalog:
    """A deterministic catalog of verified, non-executable pack descriptors."""

    def __init__(self, packs: Iterable[PackDefinition]) -> None:
        ordered = sorted(packs, key=lambda pack: pack.pack_id)
        by_id = {pack.pack_id: pack for pack in ordered}
        if len(by_id) != len(ordered):
            raise CatalogError("pack catalog contains duplicate pack IDs")
        self._packs = by_id

    @classmethod
    def from_assets_root(cls, assets_root: Path | None = None) -> "PackCatalog":
        """Load every ``pack.json`` below the architecture asset root."""
        root = (assets_root or DEFAULT_ASSETS_ROOT).resolve()
        packs_root = root / "packs"
        if not packs_root.is_dir():
            raise CatalogError(f"pack asset directory is missing: {packs_root}")
        manifest_paths = sorted(packs_root.glob("*/pack.json"))
        if not manifest_paths:
            raise CatalogError(f"no pack manifests found below {packs_root}")
        return cls(PackDefinition.from_file(path) for path in manifest_paths)

    def get(self, pack_id: str) -> PackDefinition | None:
        """Return a pack by exact ID, or ``None`` when it is not cataloged."""
        return self._packs.get(pack_id)

    def require(self, pack_id: str) -> PackDefinition:
        """Return a pack by exact ID or fail closed."""
        pack = self.get(pack_id)
        if pack is None:
            raise CatalogError(f"pack is not cataloged: {pack_id!r}")
        return pack

    def all(self) -> tuple[PackDefinition, ...]:
        """Return packs in stable ID order."""
        return tuple(self._packs.values())

    def shell_providers(self) -> tuple[PackDefinition, ...]:
        """Return all shell packs in stable ID order."""
        return tuple(pack for pack in self.all() if pack.is_shell)
