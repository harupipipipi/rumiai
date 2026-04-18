from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

DEFAULTSPACK_IDENTITY = "rumi.defaults"


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
    def __init__(self, ecosystem_dir: Optional[Path] = None) -> None:
        self._ecosystem_dir = ecosystem_dir
        self._audit_log: List[Dict[str, Any]] = []

    def scan_candidates(self) -> List[PackCandidate]:
        candidates: List[PackCandidate] = []
        if not self._ecosystem_dir or not self._ecosystem_dir.exists():
            return candidates
        for child in sorted(self._ecosystem_dir.iterdir()):
            if not child.is_dir() or child.name.startswith("."):
                continue
            eco_json = child / "ecosystem.json"
            if not eco_json.is_file():
                continue
            try:
                data = json.loads(eco_json.read_text(encoding="utf-8"))
            except Exception:
                continue
            identity = str(data.get("pack_identity", ""))
            candidates.append(
                PackCandidate(
                    pack_id=str(data.get("pack_id", child.name)),
                    pack_identity=identity,
                    display_name=str(data.get("display_name", data.get("pack_id", child.name))),
                    description=str(data.get("description", "")),
                    version=str(data.get("version", "")),
                    recommended=bool(data.get("recommended", False)),
                    risk_level=str(data.get("risk_level", "normal")),
                    all_ok_eligible=bool(
                        data.get(
                            "all_ok_eligible",
                            data.get("supports_all_ok", False),
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
