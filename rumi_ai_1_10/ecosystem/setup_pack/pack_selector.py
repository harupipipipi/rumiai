from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class PackCandidate:
    pack_id: str = ""
    pack_identity: str = ""
    display_name: str = ""
    description: str = ""
    version: str = ""
    recommended: bool = False
    risk_level: str = "normal"
    all_ok_eligible: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pack_id": self.pack_id,
            "pack_identity": self.pack_identity,
            "display_name": self.display_name,
            "description": self.description,
            "version": self.version,
            "recommended": self.recommended,
            "risk_level": self.risk_level,
            "all_ok_eligible": self.all_ok_eligible,
        }


class PackSelector:
    def __init__(self, setup_pack_dir: Optional[Path] = None) -> None:
        self._setup_pack_dir = setup_pack_dir
        self._audit_log: List[Dict[str, Any]] = []

    def _resolve_setup_pack_root(self) -> Optional[Path]:
        if not self._setup_pack_dir:
            return None
        if not self._setup_pack_dir.exists():
            return None
        # 互換: ecosystem/ を渡された場合は ecosystem/setup_pack を優先
        nested = self._setup_pack_dir / "setup_pack"
        if nested.is_dir():
            return nested
        return self._setup_pack_dir

    @staticmethod
    def _read_pack_identity(ecosystem_root: Path, target_pack_id: str) -> str:
        if not target_pack_id:
            return ""
        ecosystem_json = ecosystem_root / target_pack_id / "ecosystem.json"
        if not ecosystem_json.is_file():
            return ""
        try:
            data = json.loads(ecosystem_json.read_text(encoding="utf-8"))
        except Exception:
            return ""
        return str(data.get("pack_identity", ""))

    def scan_candidates(self) -> List[PackCandidate]:
        candidates: List[PackCandidate] = []
        setup_pack_root = self._resolve_setup_pack_root()
        if setup_pack_root is None:
            return candidates
        ecosystem_root = setup_pack_root.parent
        for pack_json in sorted(setup_pack_root.glob("*/pack.json")):
            try:
                data = json.loads(pack_json.read_text(encoding="utf-8"))
            except Exception:
                continue
            setup_pack_id = str(data.get("pack_id") or pack_json.parent.name)
            target_pack_id = str(data.get("target_pack_id") or setup_pack_id)
            identity = self._read_pack_identity(ecosystem_root, target_pack_id)
            candidates.append(
                PackCandidate(
                    pack_id=setup_pack_id,
                    pack_identity=identity,
                    display_name=str(data.get("display_name", setup_pack_id)),
                    description=str(data.get("description", "")),
                    version=str(data.get("version", "")),
                    recommended=bool(data.get("recommended", False)),
                    risk_level=str(data.get("risk_level", "medium")),
                    all_ok_eligible=bool(
                        data.get(
                            "supports_all_ok",
                            data.get("all_ok_eligible", False),
                        )
                    ),
                )
            )
        return candidates

    def select_and_grant(self, pack_id: str) -> Dict[str, Any]:
        candidates = {c.pack_id: c for c in self.scan_candidates()}
        candidate = candidates.get(pack_id)
        if candidate is None:
            return {"error": f"pack {pack_id} not found", "granted": False}
        result = {
            "pack_id": pack_id,
            "granted": True,
            "all_ok": bool(candidate.all_ok_eligible),
        }
        self._audit_log.append(
            {
                "action": "select_and_grant",
                "pack_id": pack_id,
                "all_ok": result["all_ok"],
                "timestamp": time.time(),
            }
        )
        return result

    def revoke(self, pack_id: str) -> Dict[str, Any]:
        self._audit_log.append({"action": "revoke", "pack_id": pack_id, "timestamp": time.time()})
        return {"revoked": True, "pack_id": pack_id}

    def get_audit_log(self) -> List[Dict[str, Any]]:
        return list(self._audit_log)
