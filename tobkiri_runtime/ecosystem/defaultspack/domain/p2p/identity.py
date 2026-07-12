from __future__ import annotations

import hashlib
import json
import secrets
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .settings import default_store_path


def _now_ms() -> int:
    return int(time.time() * 1000)


def _identity_file(store_path: Path | None = None) -> Path:
    root = Path(store_path).expanduser() if store_path is not None else default_store_path()
    if root.suffix == ".json":
        return root
    return root / "identity.json"


def _canonical_json(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def fingerprint_for(node_id: str, public_key: str) -> str:
    digest = hashlib.sha256(
        _canonical_json(
            {
                "node_id": str(node_id or ""),
                "public_key": str(public_key or ""),
                "version": "rumi-p2p-node-v1",
            }
        ).encode("utf-8")
    ).hexdigest()
    return ":".join(digest[index : index + 4] for index in range(0, 32, 4))


@dataclass
class NodeIdentity:
    node_id: str
    public_key: str
    node_secret: str
    fingerprint: str
    created_at: int
    updated_at: int
    label: str = ""

    @classmethod
    def create(cls, *, label: str = "") -> "NodeIdentity":
        node_id = "p2p-node-" + uuid.uuid4().hex
        public_key = secrets.token_urlsafe(32)
        now = _now_ms()
        return cls(
            node_id=node_id,
            public_key=public_key,
            node_secret=secrets.token_urlsafe(48),
            fingerprint=fingerprint_for(node_id, public_key),
            created_at=now,
            updated_at=now,
            label=str(label or ""),
        )

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "NodeIdentity":
        node_id = str(value.get("node_id") or "")
        public_key = str(value.get("public_key") or "")
        fingerprint = str(value.get("fingerprint") or "") or fingerprint_for(node_id, public_key)
        return cls(
            node_id=node_id,
            public_key=public_key,
            node_secret=str(value.get("node_secret") or ""),
            fingerprint=fingerprint,
            created_at=int(value.get("created_at") or _now_ms()),
            updated_at=int(value.get("updated_at") or value.get("created_at") or _now_ms()),
            label=str(value.get("label") or ""),
        )

    def as_dict(self, *, redact: bool = True) -> dict[str, Any]:
        data = {
            "node_id": self.node_id,
            "public_key": self.public_key,
            "fingerprint": self.fingerprint,
            "created_at": int(self.created_at),
            "updated_at": int(self.updated_at),
            "label": self.label,
        }
        data["node_secret"] = "***" if redact else self.node_secret
        return data


def load_or_create_identity(*, store_path: Path | None = None, label: str = "") -> NodeIdentity:
    path = _identity_file(store_path)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            identity = NodeIdentity.from_dict(raw)
            if identity.node_id and identity.public_key and identity.node_secret:
                return identity
    except (OSError, json.JSONDecodeError, ValueError):
        pass

    identity = NodeIdentity.create(label=label)
    save_identity(identity, store_path=store_path)
    return identity


def rotate_identity(*, store_path: Path | None = None, label: str | None = None) -> NodeIdentity:
    if label is None:
        path = _identity_file(store_path)
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            label = str(raw.get("label") or "") if isinstance(raw, dict) else ""
        except (OSError, json.JSONDecodeError, ValueError):
            label = ""

    identity = NodeIdentity.create(label=str(label or ""))
    save_identity(identity, store_path=store_path)
    return identity


def save_identity(identity: NodeIdentity, *, store_path: Path | None = None) -> None:
    path = _identity_file(store_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    identity.updated_at = _now_ms()
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(
        json.dumps(identity.as_dict(redact=False), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    tmp.replace(path)
