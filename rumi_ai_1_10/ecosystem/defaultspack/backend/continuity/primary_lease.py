from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from .errors import ContinuityError, PRIMARY_LEASE_CONFLICT, STALE_GENERATION
from .store import JsonFileStore, default_continuity_dir


class PrimaryLeaseService:
    def __init__(self, root: str | Path | None = None) -> None:
        self.root = Path(root) if root is not None else default_continuity_dir()
        self.store = JsonFileStore(self.root / "primary_leases.json")

    def acquire(self, sandbox_id: str, owner_node_id: str, *, generation: int, ttl_seconds: int = 120) -> dict[str, Any]:
        sandbox_id = str(sandbox_id or "").strip()
        owner_node_id = str(owner_node_id or "").strip()
        now = time.time()
        generation = max(1, int(generation or 1))

        def _update(data: dict[str, Any]):
            leases = data.setdefault("leases", {})
            current = leases.get(sandbox_id) if isinstance(leases, dict) else None
            if isinstance(current, dict):
                expires_at = float(current.get("expires_at_epoch") or 0)
                current_generation = int(current.get("generation") or 0)
                if current_generation > generation:
                    raise ContinuityError("Stale generation cannot acquire primary lease.", STALE_GENERATION, 409)
                if expires_at > now and str(current.get("owner_node_id") or "") != owner_node_id:
                    raise ContinuityError("Primary lease is held by another node.", PRIMARY_LEASE_CONFLICT, 409, {"current": self._public(current)})
            next_lease = {
                "sandbox_id": sandbox_id,
                "owner_node_id": owner_node_id,
                "generation": generation,
                "fencing_token": f"{sandbox_id}:{generation}:{int(now * 1000)}",
                "acquired_at_epoch": now,
                "expires_at_epoch": now + ttl_seconds,
            }
            leases[sandbox_id] = next_lease
            return data, self._public(next_lease)

        return self.store.update(_update)

    def validate(self, sandbox_id: str, owner_node_id: str, generation: int) -> bool:
        lease = self.get(sandbox_id)
        if not lease:
            return False
        return (
            str(lease.get("owner_node_id") or "") == str(owner_node_id or "")
            and int(lease.get("generation") or 0) == int(generation or 0)
            and float(lease.get("expires_at_epoch") or 0) > time.time()
        )

    def get(self, sandbox_id: str) -> dict[str, Any] | None:
        data = self.store.read()
        leases = data.get("leases") if isinstance(data.get("leases"), dict) else {}
        lease = leases.get(str(sandbox_id))
        return dict(lease) if isinstance(lease, dict) else None

    @staticmethod
    def _public(lease: dict[str, Any]) -> dict[str, Any]:
        return {
            "sandbox_id": lease.get("sandbox_id"),
            "owner_node_id": lease.get("owner_node_id"),
            "generation": lease.get("generation"),
            "fencing_token": lease.get("fencing_token"),
            "expires_at_epoch": lease.get("expires_at_epoch"),
        }
