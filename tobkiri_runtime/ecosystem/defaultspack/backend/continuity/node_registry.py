from __future__ import annotations

import base64
import os
import platform
import secrets
import socket
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519, x25519

from .errors import ContinuityError, NODE_NOT_FOUND, PAIRING_CODE_INVALID
from .models import RumiNodeDescriptor
from .store import JsonFileStore, default_continuity_dir


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _unb64(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode((data + padding).encode("ascii"))


def _raw_private(private_key: x25519.X25519PrivateKey | ed25519.Ed25519PrivateKey) -> str:
    return _b64(
        private_key.private_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PrivateFormat.Raw,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )


def _raw_public(public_key: x25519.X25519PublicKey | ed25519.Ed25519PublicKey) -> str:
    return _b64(
        public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
    )


@dataclass(frozen=True)
class NodeKeyMaterial:
    encryption_private_key: str
    encryption_public_key: str
    signing_private_key: str
    signing_public_key: str


def generate_node_keys() -> NodeKeyMaterial:
    encryption_private = x25519.X25519PrivateKey.generate()
    signing_private = ed25519.Ed25519PrivateKey.generate()
    return NodeKeyMaterial(
        encryption_private_key=_raw_private(encryption_private),
        encryption_public_key=_raw_public(encryption_private.public_key()),
        signing_private_key=_raw_private(signing_private),
        signing_public_key=_raw_public(signing_private.public_key()),
    )


def load_x25519_private(value: str) -> x25519.X25519PrivateKey:
    return x25519.X25519PrivateKey.from_private_bytes(_unb64(value))


def load_x25519_public(value: str) -> x25519.X25519PublicKey:
    return x25519.X25519PublicKey.from_public_bytes(_unb64(value))


def load_ed25519_private(value: str) -> ed25519.Ed25519PrivateKey:
    return ed25519.Ed25519PrivateKey.from_private_bytes(_unb64(value))


def load_ed25519_public(value: str) -> ed25519.Ed25519PublicKey:
    return ed25519.Ed25519PublicKey.from_public_bytes(_unb64(value))


class NodeRegistry:
    def __init__(self, root: str | Path | None = None) -> None:
        self.root = Path(root) if root is not None else default_continuity_dir()
        self.store = JsonFileStore(self.root / "nodes.json")
        self._ensure_local_node()

    def local_node(self) -> dict[str, Any]:
        data = self.store.read()
        local = data.get("local_node") if isinstance(data.get("local_node"), dict) else {}
        return self._public_node(local)

    def local_key_material(self) -> dict[str, str]:
        data = self.store.read()
        local = data.get("local_node") if isinstance(data.get("local_node"), dict) else {}
        return {
            "encryption_private_key": str(local.get("encryption_private_key") or ""),
            "signing_private_key": str(local.get("signing_private_key") or ""),
            "device_public_key": str(local.get("device_public_key") or ""),
            "signing_public_key": str(local.get("signing_public_key") or ""),
        }

    def list_nodes(self) -> list[dict[str, Any]]:
        data = self.store.read()
        nodes = [self.local_node()]
        paired = data.get("paired_nodes") if isinstance(data.get("paired_nodes"), dict) else {}
        for node in paired.values():
            if isinstance(node, dict):
                nodes.append(self._public_node(node))
        return nodes

    def get(self, node_id: str) -> dict[str, Any]:
        node_id = str(node_id or "").strip()
        for node in self._raw_nodes().values():
            if str(node.get("node_id") or "") == node_id:
                return dict(node)
        raise ContinuityError(f"Continuity node not found: {node_id}", NODE_NOT_FOUND, 404)

    def remove(self, node_id: str) -> dict[str, Any]:
        node_id = str(node_id or "").strip()

        def _update(data: dict[str, Any]):
            paired = data.setdefault("paired_nodes", {})
            removed = paired.pop(node_id, None) if isinstance(paired, dict) else None
            return data, {"removed": bool(removed), "node_id": node_id}

        return self.store.update(_update)

    def start_pairing(self, *, display_name: str = "") -> dict[str, Any]:
        code = "-".join(secrets.token_hex(2) for _ in range(3)).upper()
        request_id = "pair-" + uuid.uuid4().hex[:12]

        def _update(data: dict[str, Any]):
            pending = data.setdefault("pending_pairings", {})
            pending[request_id] = {
                "request_id": request_id,
                "code": code,
                "display_name": str(display_name or "").strip(),
                "created_at": utc_now(),
            }
            return data, dict(pending[request_id])

        return self.store.update(_update)

    def accept_pairing(self, payload: dict[str, Any]) -> dict[str, Any]:
        request_id = str(payload.get("request_id") or "").strip()
        code = str(payload.get("code") or "").strip().upper()
        descriptor = payload.get("descriptor") if isinstance(payload.get("descriptor"), dict) else None
        simulate = payload.get("simulate_local_destination", True) is not False

        def _update(data: dict[str, Any]):
            pending = data.setdefault("pending_pairings", {})
            current = pending.get(request_id) if isinstance(pending, dict) else None
            if not isinstance(current, dict) or str(current.get("code") or "").upper() != code:
                raise ContinuityError("Pairing code is invalid or expired.", PAIRING_CODE_INVALID, 403)
            node = self._node_from_descriptor(
                descriptor,
                fallback_name=str(payload.get("display_name") or current.get("display_name") or "Rumi Node").strip(),
                include_private=simulate,
                destination_kind=str(payload.get("destination_kind") or "rumi_node"),
            )
            paired = data.setdefault("paired_nodes", {})
            paired[node["node_id"]] = node
            pending.pop(request_id, None)
            return data, self._public_node(node)

        return self.store.update(_update)

    def register_destination(
        self,
        *,
        display_name: str,
        destination_kind: str = "rumi_node",
        include_private: bool = True,
        runtime_providers: tuple[str, ...] = ("linux_native", "docker"),
        sandbox_capabilities: tuple[str, ...] = ("sandbox.exec", "sandbox.files", "sandbox.desktop", "sandbox.snapshot"),
        network_reachability_classes: tuple[str, ...] = ("public_https", "private_network"),
    ) -> dict[str, Any]:
        node = self._node_from_descriptor(
            None,
            fallback_name=display_name,
            include_private=include_private,
            destination_kind=destination_kind,
            runtime_providers=runtime_providers,
            sandbox_capabilities=sandbox_capabilities,
            network_reachability_classes=network_reachability_classes,
        )

        def _update(data: dict[str, Any]):
            paired = data.setdefault("paired_nodes", {})
            paired[node["node_id"]] = node
            return data, self._public_node(node)

        return self.store.update(_update)

    def private_key_for(self, node_id: str) -> str:
        node = self.get(node_id)
        return str(node.get("encryption_private_key") or "")

    def signing_public_for(self, node_id: str) -> str:
        node = self.get(node_id)
        return str(node.get("signing_public_key") or "")

    def descriptor_for(self, node_id: str) -> RumiNodeDescriptor:
        return RumiNodeDescriptor(**self._descriptor_payload(self.get(node_id)))

    def _ensure_local_node(self) -> None:
        def _update(data: dict[str, Any]):
            local = data.get("local_node") if isinstance(data.get("local_node"), dict) else None
            if isinstance(local, dict) and local.get("node_id") and local.get("encryption_private_key"):
                local["online"] = True
                local["last_seen_at"] = utc_now()
                return data, None
            keys = generate_node_keys()
            node_id = "rumi-node-" + uuid.uuid4().hex[:12]
            data["local_node"] = {
                "node_id": node_id,
                "display_name": socket.gethostname() or "This PC",
                "device_public_key": keys.encryption_public_key,
                "encryption_private_key": keys.encryption_private_key,
                "signing_public_key": keys.signing_public_key,
                "signing_private_key": keys.signing_private_key,
                "platform": platform.system() or os.name,
                "architecture": platform.machine() or "unknown",
                "online": True,
                "last_seen_at": utc_now(),
                "app_version": "local",
                "protocol_version": 1,
                "runtime_providers": [],
                "sandbox_capabilities": [],
                "available_cpu": os.cpu_count() or 1,
                "available_memory_mb": None,
                "available_disk_mb": None,
                "desktop_capacity": 1,
                "network_reachability_classes": ["public_https", "private_network"],
                "provider_extension_digests": [],
                "destination_kind": "source",
            }
            return data, None

        self.store.update(_update)

    def _raw_nodes(self) -> dict[str, dict[str, Any]]:
        data = self.store.read()
        nodes: dict[str, dict[str, Any]] = {}
        local = data.get("local_node") if isinstance(data.get("local_node"), dict) else None
        if isinstance(local, dict):
            nodes[str(local.get("node_id") or "local")] = dict(local)
        paired = data.get("paired_nodes") if isinstance(data.get("paired_nodes"), dict) else {}
        for node_id, node in paired.items():
            if isinstance(node, dict):
                nodes[str(node.get("node_id") or node_id)] = dict(node)
        return nodes

    def _node_from_descriptor(
        self,
        descriptor: dict[str, Any] | None,
        *,
        fallback_name: str,
        include_private: bool,
        destination_kind: str,
        runtime_providers: tuple[str, ...] = ("linux_native", "docker"),
        sandbox_capabilities: tuple[str, ...] = ("sandbox.exec", "sandbox.files", "sandbox.desktop", "sandbox.snapshot"),
        network_reachability_classes: tuple[str, ...] = ("public_https", "private_network"),
    ) -> dict[str, Any]:
        keys = generate_node_keys() if descriptor is None or include_private else None
        node_id = str((descriptor or {}).get("node_id") or "rumi-node-" + uuid.uuid4().hex[:12])
        device_public_key = str((descriptor or {}).get("device_public_key") or (keys.encryption_public_key if keys else ""))
        signing_public_key = str((descriptor or {}).get("signing_public_key") or (keys.signing_public_key if keys else ""))
        node = {
            "node_id": node_id,
            "display_name": str((descriptor or {}).get("display_name") or fallback_name or node_id),
            "device_public_key": device_public_key,
            "signing_public_key": signing_public_key,
            "platform": str((descriptor or {}).get("platform") or platform.system() or os.name),
            "architecture": str((descriptor or {}).get("architecture") or platform.machine() or "unknown"),
            "online": bool((descriptor or {}).get("online", True)),
            "last_seen_at": utc_now(),
            "app_version": str((descriptor or {}).get("app_version") or "paired"),
            "protocol_version": int((descriptor or {}).get("protocol_version") or 1),
            "runtime_providers": list((descriptor or {}).get("runtime_providers") or runtime_providers),
            "sandbox_capabilities": list((descriptor or {}).get("sandbox_capabilities") or sandbox_capabilities),
            "available_cpu": (descriptor or {}).get("available_cpu", os.cpu_count() or 1),
            "available_memory_mb": (descriptor or {}).get("available_memory_mb", 8192),
            "available_disk_mb": (descriptor or {}).get("available_disk_mb", 32768),
            "desktop_capacity": int((descriptor or {}).get("desktop_capacity") or 1),
            "network_reachability_classes": list((descriptor or {}).get("network_reachability_classes") or network_reachability_classes),
            "provider_extension_digests": list((descriptor or {}).get("provider_extension_digests") or []),
            "destination_kind": destination_kind,
        }
        if include_private and keys is not None:
            node["encryption_private_key"] = keys.encryption_private_key
            node["signing_private_key"] = keys.signing_private_key
        return node

    @staticmethod
    def _descriptor_payload(node: dict[str, Any]) -> dict[str, Any]:
        return {
            "node_id": str(node.get("node_id") or ""),
            "display_name": str(node.get("display_name") or ""),
            "device_public_key": str(node.get("device_public_key") or ""),
            "signing_public_key": str(node.get("signing_public_key") or ""),
            "platform": str(node.get("platform") or ""),
            "architecture": str(node.get("architecture") or ""),
            "online": bool(node.get("online")),
            "last_seen_at": str(node.get("last_seen_at") or ""),
            "app_version": str(node.get("app_version") or ""),
            "protocol_version": int(node.get("protocol_version") or 1),
            "runtime_providers": tuple(str(item) for item in node.get("runtime_providers") or []),
            "sandbox_capabilities": tuple(str(item) for item in node.get("sandbox_capabilities") or []),
            "available_cpu": node.get("available_cpu"),
            "available_memory_mb": node.get("available_memory_mb"),
            "available_disk_mb": node.get("available_disk_mb"),
            "desktop_capacity": int(node.get("desktop_capacity") or 0),
            "network_reachability_classes": tuple(str(item) for item in node.get("network_reachability_classes") or []),
            "provider_extension_digests": tuple(str(item) for item in node.get("provider_extension_digests") or []),
            "destination_kind": str(node.get("destination_kind") or "rumi_node"),
        }

    def _public_node(self, node: dict[str, Any]) -> dict[str, Any]:
        return self._descriptor_payload(node)
