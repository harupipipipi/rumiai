"""
unit_trust_store.py - 実行系 Unit の sha256 trust allowlist
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class UnitTrustEntry:
    unit_id: str
    version: str
    sha256: str
    added_at: str
    added_by: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "unit_id": self.unit_id,
            "version": self.version,
            "sha256": self.sha256,
            "added_at": self.added_at,
            "added_by": self.added_by,
        }


class UnitTrustStore:
    DEFAULT_TRUST_FILE = "user_data/units/trust/trusted_units.json"

    def __init__(self, trust_file: str = None):
        self._trust_file = Path(trust_file) if trust_file else Path(self.DEFAULT_TRUST_FILE)
        self._trust_file.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._entries: List[UnitTrustEntry] = []
        self.load()

    def _now_ts(self) -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    def load(self) -> None:
        with self._lock:
            self._entries = []
            if not self._trust_file.exists():
                return
            try:
                data = json.loads(self._trust_file.read_text(encoding="utf-8"))
                for item in data.get("entries", []):
                    self._entries.append(UnitTrustEntry(
                        unit_id=item.get("unit_id", ""),
                        version=item.get("version", ""),
                        sha256=item.get("sha256", ""),
                        added_at=item.get("added_at", ""),
                        added_by=item.get("added_by", ""),
                    ))
            except Exception:
                self._entries = []

    def save(self) -> None:
        with self._lock:
            data = {"entries": [entry.to_dict() for entry in self._entries]}
            self._trust_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def add_trust(self, unit_id: str, version: str, sha256: str, actor: str = "system") -> None:
        with self._lock:
            self._entries.append(UnitTrustEntry(
                unit_id=unit_id,
                version=version,
                sha256=sha256,
                added_at=self._now_ts(),
                added_by=actor,
            ))
            self.save()

    def is_trusted(self, unit_id: str, version: str, sha256: str) -> bool:
        with self._lock:
            for entry in self._entries:
                if entry.unit_id == unit_id and entry.version == version and entry.sha256 == sha256:
                    return True
            return False

    def list_trusted(self) -> List[Dict[str, Any]]:
        with self._lock:
            return [entry.to_dict() for entry in self._entries]


_global_trust_store: Optional[UnitTrustStore] = None
_trust_lock = threading.Lock()


def get_unit_trust_store() -> UnitTrustStore:
    global _global_trust_store
    if _global_trust_store is None:
        with _trust_lock:
            if _global_trust_store is None:
                _global_trust_store = UnitTrustStore()
    return _global_trust_store


def reset_unit_trust_store(trust_file: str = None) -> UnitTrustStore:
    global _global_trust_store
    with _trust_lock:
        _global_trust_store = UnitTrustStore(trust_file)
    return _global_trust_store
