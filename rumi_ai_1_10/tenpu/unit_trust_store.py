"""
unit_trust_store.py - 実行系ユニットの sha256 trust allowlist

実行系ユニット（kind=python/binary）は Trust（sha256 allowlist）必須。
unit_id + version + sha256 を記録。

保存先: user_data/units/trust/trusted_units.json
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


DEFAULT_TRUST_DIR = "user_data/units/trust"
TRUST_FILE_NAME = "trusted_units.json"


@dataclass
class TrustedUnit:
    unit_id: str
    version: str
    sha256: str
    note: str = ""


@dataclass
class UnitTrustCheckResult:
    trusted: bool
    reason: str
    unit_id: str
    version: str
    expected_sha256: Optional[str] = None
    actual_sha256: Optional[str] = None


class UnitTrustStore:
    def __init__(self, trust_dir: Optional[str] = None):
        self._trust_dir = Path(trust_dir or DEFAULT_TRUST_DIR)
        self._trust_file = self._trust_dir / TRUST_FILE_NAME
        self._lock = threading.RLock()
        self._trusted: Dict[tuple, TrustedUnit] = {}
        self._loaded = False
        self._load_error: Optional[str] = None

    @staticmethod
    def _now_ts() -> str:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    def load(self) -> bool:
        with self._lock:
            self._trusted.clear()
            self._loaded = False
            self._load_error = None

            if not self._trust_file.exists():
                self._loaded = True
                return True

            try:
                with open(self._trust_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except (json.JSONDecodeError, OSError) as e:
                self._load_error = f"Failed to parse trust file: {e}"
                return False

            if not isinstance(data, dict):
                self._load_error = "Trust file must be a JSON object"
                return False

            for entry in data.get("trusted", []):
                if not isinstance(entry, dict):
                    continue
                uid = entry.get("unit_id", "")
                ver = entry.get("version", "")
                sha = entry.get("sha256", "")
                if uid and ver and sha:
                    self._trusted[(uid, ver)] = TrustedUnit(
                        unit_id=uid,
                        version=ver,
                        sha256=sha.lower(),
                        note=entry.get("note", ""),
                    )

            self._loaded = True
            return True

    def is_trusted(
        self,
        unit_id: str,
        version: str,
        actual_sha256: str,
    ) -> UnitTrustCheckResult:
        with self._lock:
            if not self._loaded:
                return UnitTrustCheckResult(
                    trusted=False,
                    reason="Unit trust store not loaded",
                    unit_id=unit_id,
                    version=version,
                    actual_sha256=actual_sha256,
                )
            entry = self._trusted.get((unit_id, version))
            if entry is None:
                return UnitTrustCheckResult(
                    trusted=False,
                    reason=f"Unit '{unit_id}' version '{version}' not in trust list",
                    unit_id=unit_id,
                    version=version,
                    actual_sha256=actual_sha256,
                )
            actual_lower = actual_sha256.lower()
            if entry.sha256 != actual_lower:
                return UnitTrustCheckResult(
                    trusted=False,
                    reason=f"SHA-256 mismatch for unit '{unit_id}' version '{version}'",
                    unit_id=unit_id,
                    version=version,
                    expected_sha256=entry.sha256,
                    actual_sha256=actual_lower,
                )
            return UnitTrustCheckResult(
                trusted=True,
                reason="Trusted",
                unit_id=unit_id,
                version=version,
                expected_sha256=entry.sha256,
                actual_sha256=actual_lower,
            )

    def add_trust(
        self,
        unit_id: str,
        version: str,
        sha256: str,
        note: str = "",
    ) -> bool:
        with self._lock:
            self._trusted[(unit_id, version)] = TrustedUnit(
                unit_id=unit_id,
                version=version,
                sha256=sha256.lower(),
                note=note,
            )
            return self._save()

    def remove_trust(self, unit_id: str, version: str) -> bool:
        with self._lock:
            key = (unit_id, version)
            if key not in self._trusted:
                return False
            del self._trusted[key]
            return self._save()

    def list_trusted(self) -> List[TrustedUnit]:
        with self._lock:
            return list(self._trusted.values())

    def is_loaded(self) -> bool:
        with self._lock:
            return self._loaded

    def _save(self) -> bool:
        try:
            self._trust_dir.mkdir(parents=True, exist_ok=True)
            data = {
                "version": "1.0",
                "updated_at": self._now_ts(),
                "trusted": [
                    {
                        "unit_id": t.unit_id,
                        "version": t.version,
                        "sha256": t.sha256,
                        "note": t.note,
                    }
                    for t in self._trusted.values()
                ],
            }
            with open(self._trust_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return True
        except Exception:
            return False


_global_unit_trust: Optional[UnitTrustStore] = None
_unit_trust_lock = threading.Lock()


def get_unit_trust_store() -> UnitTrustStore:
    global _global_unit_trust
    if _global_unit_trust is None:
        with _unit_trust_lock:
            if _global_unit_trust is None:
                _global_unit_trust = UnitTrustStore()
    return _global_unit_trust


def reset_unit_trust_store(trust_dir: str = None) -> UnitTrustStore:
    global _global_unit_trust
    with _unit_trust_lock:
        _global_unit_trust = UnitTrustStore(trust_dir)
    return _global_unit_trust
