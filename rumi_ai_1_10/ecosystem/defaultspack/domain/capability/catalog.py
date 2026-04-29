from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


class CapabilityCatalog:
    """Load local-first defaultspack capability manifests."""

    def __init__(self, pack_root: Path | None = None) -> None:
        self._pack_root = pack_root or Path(__file__).resolve().parents[2]
        self._capabilities_dir = self._pack_root / "capabilities"

    def list_capabilities(
        self,
        *,
        local_only: bool | None = None,
        risk_level: str | None = None,
        requires_network: bool | None = None,
    ) -> list[dict[str, Any]]:
        capabilities = [self._normalize(path) for path in sorted(self._capabilities_dir.glob("*.capability.yaml"))]
        if local_only is not None:
            capabilities = [item for item in capabilities if bool(item.get("local_only")) is local_only]
        if risk_level:
            capabilities = [item for item in capabilities if item.get("risk_level") == risk_level]
        if requires_network is not None:
            capabilities = [item for item in capabilities if bool(item.get("requires_network")) is requires_network]
        return capabilities

    def get(self, capability_id: str) -> dict[str, Any] | None:
        for capability in self.list_capabilities():
            if capability.get("id") == capability_id:
                return capability
        return None

    def summary(self) -> dict[str, Any]:
        capabilities = self.list_capabilities()
        risk_counts: dict[str, int] = {}
        for capability in capabilities:
            risk = str(capability.get("risk_level", "low"))
            risk_counts[risk] = risk_counts.get(risk, 0) + 1
        return {
            "count": len(capabilities),
            "local_only_count": sum(1 for item in capabilities if item.get("local_only") is True),
            "network_optional_count": sum(1 for item in capabilities if item.get("requires_network") == "optional"),
            "requires_network_count": sum(1 for item in capabilities if item.get("requires_network") is True),
            "risk_counts": risk_counts,
        }

    def _normalize(self, path: Path) -> dict[str, Any]:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        permissions = list(raw.get("permissions", []))
        operations = list(raw.get("operations", []))
        approval = raw.get("approval", {}) or {}
        risk_level = raw.get("risk_level")
        if not risk_level:
            risk_level = "high" if any(approval.values()) else "low"
        return {
            **raw,
            "id": raw.get("id") or path.stem.replace(".capability", ""),
            "name": raw.get("name") or raw.get("id") or path.stem,
            "description": raw.get("description", ""),
            "permissions": permissions,
            "operations": operations,
            "requires_network": raw.get("requires_network", False),
            "requires_approval": bool(raw.get("requires_approval", False) or any(approval.values())),
            "local_only": raw.get("local_only", False),
            "risk_level": risk_level,
            "source_path": str(path.relative_to(self._pack_root)),
        }
