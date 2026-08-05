"""Captured Host control plane for Pack v4 catalog/profile mutations."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping

from tobkiri_host.errors import HostCoreError

from .pack_boundary import load_pack_catalog, resolve_pack_root
from .paths import USER_DATA_DIR


PACK_CONTROL_CONTRACT = "tobkiri.host.pack-control.v4"
PACK_CONTROL_OPERATIONS = frozenset(
    {
        "catalog.read",
        "pack.install",
        "approval.candidate",
        "approval.approve",
        "pack.enable",
        "pack.disable",
        "pack.status",
        "profile.reload",
        "runtime.restart",
    }
)
_CANDIDATE_TTL_SECONDS = 120.0


class PackControlDenied(HostCoreError):
    """A Pack control request failed its captured authority boundary."""

    code = "pack_control_denied"


@dataclass(frozen=True)
class _Binding:
    profile_id: str
    workspace_id: str
    profile_revision: str
    plan_digest: str
    catalog_revision: str


@dataclass(frozen=True)
class _ApprovalCandidate:
    candidate_id: str
    session_id: str
    pack_id: str
    snapshot_digest: str
    profile_revision: str
    catalog_revision: str
    expires_at: float


class CapturedPackControlSession:
    """One immutable-v4-profile control session with explicit recapture points."""

    def __init__(self, binding: _Binding) -> None:
        self._binding = binding
        self._lock = threading.RLock()
        self._candidates: dict[str, _ApprovalCandidate] = {}

    @classmethod
    def capture(cls) -> "CapturedPackControlSession":
        """Capture the active Profile and canonical catalog revisions."""
        return cls(_capture_binding())

    @property
    def profile_id(self) -> str:
        return self._binding.profile_id

    @property
    def plan_digest(self) -> str:
        return self._binding.plan_digest

    def provider_metadata(self, contract_id: str) -> tuple[Mapping[str, Any], ...]:
        """Expose only this Host-owned qualified control provider."""
        if contract_id != PACK_CONTROL_CONTRACT:
            return ()
        return (
            {
                "provider_id": "tobkiri.host.pack-control",
                "contract_id": PACK_CONTROL_CONTRACT,
                "operations": sorted(PACK_CONTROL_OPERATIONS),
                "profile_id": self.profile_id,
                "plan_digest": self.plan_digest,
            },
        )

    def invoke(
        self,
        contract_id: str,
        operation_id: str,
        payload: Mapping[str, Any],
        *,
        version_range: str = ">=4,<5",
    ) -> Mapping[str, Any]:
        """Invoke one qualified operation after exact session/profile checks."""
        del version_range
        if contract_id != PACK_CONTROL_CONTRACT:
            raise PackControlDenied("contract is absent from the captured Host session")
        if operation_id not in PACK_CONTROL_OPERATIONS:
            raise PackControlDenied("operation is absent from the captured Host session")
        arguments = dict(payload)
        session_id = _required(arguments.pop("_session_id", None), "session binding")
        self._reject_identity_override(arguments)
        with self._lock:
            if operation_id == "profile.reload":
                self._recapture()
                return self._status(arguments)
            self._require_current_binding()
            if operation_id == "catalog.read":
                return self._catalog_payload()
            if operation_id == "pack.install":
                return self._install(arguments)
            if operation_id == "approval.candidate":
                return self._approval_candidate(arguments, session_id)
            if operation_id == "approval.approve":
                return self._approve(arguments, session_id)
            if operation_id == "pack.enable":
                return self._set_enabled(arguments, True)
            if operation_id == "pack.disable":
                return self._set_enabled(arguments, False)
            if operation_id == "pack.status":
                return self._status(arguments)
            if operation_id == "runtime.restart":
                from .api.control_panel_handlers import request_kernel_restart

                request_kernel_restart()
                return {"restart_requested": True, **self._binding_payload()}
        raise PackControlDenied("qualified operation is unavailable")

    def _reject_identity_override(self, arguments: Mapping[str, Any]) -> None:
        expected = {
            "profile_id": self._binding.profile_id,
            "workspace_id": self._binding.workspace_id,
            "profile_revision": self._binding.profile_revision,
            "plan_digest": self._binding.plan_digest,
            "catalog_revision": self._binding.catalog_revision,
        }
        for key, value in expected.items():
            supplied = arguments.get(key)
            if supplied is not None and not hmac.compare_digest(str(supplied), value):
                raise PackControlDenied(f"captured {key} does not match")

    def _require_current_binding(self) -> None:
        current = _capture_binding()
        if current != self._binding:
            raise PackControlDenied("captured Profile session is stale")

    def _recapture(self) -> None:
        self._binding = _capture_binding()
        self._candidates.clear()

    def _catalog_payload(self) -> dict[str, Any]:
        return _catalog_payload(self._binding)

    def _install(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        pack_id, record, root = _pack(arguments)
        _pack_snapshot(pack_id, root)
        state = _read_control_state(self._binding.profile_id)
        state[pack_id] = {
            "artifact_digest": _record_digest(record),
            "catalog_revision": self._binding.catalog_revision,
        }
        _write_control_state(self._binding.profile_id, state)
        return {"pack_id": pack_id, "installed": True, **self._binding_payload()}

    def _approval_candidate(self, arguments: Mapping[str, Any], session_id: str) -> dict[str, Any]:
        pack_id = _installed_pack(arguments, self._binding)
        snapshot_digest = _pack_snapshot(pack_id, resolve_pack_root(pack_id))
        candidate_id = secrets.token_urlsafe(32)
        candidate = _ApprovalCandidate(
            candidate_id=candidate_id,
            session_id=session_id,
            pack_id=pack_id,
            snapshot_digest=snapshot_digest,
            profile_revision=self._binding.profile_revision,
            catalog_revision=self._binding.catalog_revision,
            expires_at=time.time() + _CANDIDATE_TTL_SECONDS,
        )
        self._candidates[candidate_id] = candidate
        return {
            "candidate_id": candidate_id,
            "pack_id": pack_id,
            "snapshot_digest": candidate.snapshot_digest,
            "expires_in": int(_CANDIDATE_TTL_SECONDS),
            **self._binding_payload(),
        }

    def _approve(self, arguments: Mapping[str, Any], session_id: str) -> dict[str, Any]:
        pack_id = _installed_pack(arguments, self._binding)
        candidate_id = _required(arguments.get("candidate_id"), "approval candidate")
        candidate = self._candidates.pop(candidate_id, None)
        if candidate is None:
            raise PackControlDenied("approval candidate is missing or already used")
        if (
            candidate.expires_at <= time.time()
            or candidate.session_id != session_id
            or candidate.pack_id != pack_id
            or candidate.profile_revision != self._binding.profile_revision
            or candidate.catalog_revision != self._binding.catalog_revision
        ):
            raise PackControlDenied("approval candidate binding is invalid or stale")
        current_digest = _pack_snapshot(pack_id, resolve_pack_root(pack_id))
        if not hmac.compare_digest(current_digest, candidate.snapshot_digest):
            raise PackControlDenied("Pack contents changed after approval was requested")
        _persist_approval(pack_id, current_digest, self._binding)
        self._recapture()
        return {
            "pack_id": pack_id,
            "approved": True,
            "approval_status": "approved",
            **self._binding_payload(),
        }

    def _set_enabled(self, arguments: Mapping[str, Any], enabled: bool) -> dict[str, Any]:
        pack_id = _installed_pack(arguments, self._binding)
        record = load_pack_catalog()[pack_id]
        approved, reason = _approval_status(pack_id, record, self._binding)
        if enabled and not approved:
            raise PackControlDenied(reason or "Pack approval is required")
        state, profile = _active_profile()
        packs = [str(item) for item in profile.get("packs") or []]
        if enabled and pack_id not in packs:
            packs.append(pack_id)
        if not enabled and pack_id in packs:
            if pack_id == str(profile.get("base_pack") or ""):
                raise PackControlDenied("the active Base Pack cannot be disabled")
            packs.remove(pack_id)
        profile["packs"] = packs
        profile["updated_at"] = int(time.time())
        _save_active_profile(state, profile)
        self._recapture()
        return {"pack_id": pack_id, "enabled": enabled, **self._binding_payload()}

    def _status(self, arguments: Mapping[str, Any]) -> dict[str, Any]:
        pack_id = str(arguments.get("pack_id") or "").strip()
        catalog = self._catalog_payload()
        if not pack_id:
            return catalog
        match = next((item for item in catalog["packs"] if item["pack_id"] == pack_id), None)
        if match is None:
            raise PackControlDenied("Pack is absent from the canonical v4 catalog")
        return match

    def _binding_payload(self) -> dict[str, str]:
        return {
            "profile_id": self._binding.profile_id,
            "workspace_id": self._binding.workspace_id,
            "profile_revision": self._binding.profile_revision,
            "plan_digest": self._binding.plan_digest,
            "catalog_revision": self._binding.catalog_revision,
        }


def capture_pack_control_session() -> CapturedPackControlSession:
    """Capture the Pack control session used by the production HTTP surface."""
    return CapturedPackControlSession.capture()


class CapturedPackCatalogReader:
    """Finite read-only Pack catalog provider bound to one active Profile."""

    def __init__(self, binding: _Binding) -> None:
        self._binding = binding

    @classmethod
    def capture(cls) -> "CapturedPackCatalogReader":
        """Capture the current committed Profile and catalog revisions."""

        return cls(_capture_binding())

    @property
    def binding(self) -> _Binding:
        """Return the immutable captured binding for Host authority wiring."""

        return self._binding

    def read(self) -> dict[str, Any]:
        """Read the catalog only while the committed snapshot remains current."""

        if _capture_binding() != self._binding:
            raise PackControlDenied("captured Profile session is stale")
        return _catalog_payload(self._binding)


def capture_pack_catalog_reader() -> CapturedPackCatalogReader:
    """Capture the finite catalog Provider used by production dispatch."""

    return CapturedPackCatalogReader.capture()


def _binding_payload(binding: _Binding) -> dict[str, str]:
    return {
        "profile_id": binding.profile_id,
        "workspace_id": binding.workspace_id,
        "profile_revision": binding.profile_revision,
        "plan_digest": binding.plan_digest,
        "catalog_revision": binding.catalog_revision,
    }


def _catalog_payload(binding: _Binding) -> dict[str, Any]:
    installed = _read_control_state(binding.profile_id)
    active = set(_active_profile()[1].get("packs") or [])
    packs = []
    for pack_id, record in sorted(load_pack_catalog().items()):
        is_installed = pack_id in installed or pack_id in active
        if pack_id in installed:
            _require_install_binding(pack_id, record, installed[pack_id], binding)
        approved, reason = _approval_status(pack_id, record, binding)
        status = "approved" if approved else "installed"
        packs.append(
            {
                "pack_id": pack_id,
                "name": str(record.get("display_name") or pack_id),
                "version": str(record.get("version") or "0.0.0"),
                "description": str(record.get("description") or ""),
                "is_core": record.get("kind") == "base",
                "installed": is_installed,
                "enabled": pack_id in active and approved,
                "approved": bool(approved),
                "approval_status": status,
                "approval_reason": reason,
                "hash_valid": True if approved else None,
                "critical_changed": reason == "hash_mismatch",
                "approval_issues": [] if approved else [reason or "approval_required"],
                "artifact_digest": _record_digest(record),
                **_binding_payload(binding),
            }
        )
    return {"packs": packs, "count": len(packs), **_binding_payload(binding)}


def _capture_binding() -> _Binding:
    state, profile = _active_profile()
    resolved_profile = state["resolved_profile"]
    catalog_revision = str(resolved_profile["catalog_revision"])
    profile_revision = "sha256:" + _digest(resolved_profile)
    catalog = load_pack_catalog()
    selected = tuple(str(item or "").strip() for item in profile.get("packs") or [])
    if not selected or len(selected) != len(set(selected)):
        raise PackControlDenied("active v4 Profile effective set is empty or duplicated")
    if any(pack_id not in catalog for pack_id in selected):
        raise PackControlDenied("active v4 Profile contains an unknown Pack")
    for pack_id in selected:
        resolve_pack_root(pack_id)
    return _Binding(
        profile_id=str(profile["profile_id"]),
        workspace_id=str(profile.get("workspace_id") or profile["profile_id"]),
        profile_revision=profile_revision,
        plan_digest=str(state["resolved_plan"]["plan_digest"]),
        catalog_revision=catalog_revision,
    )


def _active_profile() -> tuple[dict[str, Any], dict[str, Any]]:
    try:
        from .bootstrap.profile_capture import capture_default_profile

        active = capture_default_profile()
    except Exception as error:
        raise PackControlDenied("active v4 Profile session is missing or invalid") from error
    resolved = active.resolved.profile
    installable_pack_ids = frozenset(load_pack_catalog())
    profile = {
        "profile_id": resolved["profile_id"],
        "workspace_id": resolved["profile_id"],
        "base_pack": resolved["base"]["pack_id"],
        "packs": [
            str(item["pack_id"])
            for item in resolved["packs"]
            if item.get("role") != "application" and str(item["pack_id"]) in installable_pack_ids
        ],
    }
    _safe_identity(profile.get("profile_id"), "Profile ID")
    _safe_identity(
        profile.get("workspace_id") or profile.get("profile_id"),
        "workspace ID",
    )
    return {
        "resolved_profile": dict(resolved),
        "resolved_plan": dict(active.resolved.plan),
        "activation": dict(active.activation),
    }, profile


def _save_active_profile(state: dict[str, Any], profile: dict[str, Any]) -> None:
    del state, profile
    raise PackControlDenied("active Profile is immutable; submit a finite v4 Profile transaction")


def _control_state_path(profile_id: str) -> Path:
    _safe_identity(profile_id, "Profile ID")
    return Path(USER_DATA_DIR) / "pack_control" / f"{profile_id}.v4.json"


def _read_control_state(profile_id: str) -> dict[str, Any]:
    path = _control_state_path(profile_id)
    if path.is_symlink():
        raise PackControlDenied("Pack control state cannot be a symlink")
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise PackControlDenied("Pack control state is unreadable") from error
    if not isinstance(value, Mapping) or not isinstance(value.get("installed"), Mapping):
        raise PackControlDenied("Pack control state is invalid")
    installed = dict(value["installed"])
    if any(pack_id not in load_pack_catalog() for pack_id in installed):
        raise PackControlDenied("Pack control state contains an unknown Pack")
    return installed


def _write_control_state(profile_id: str, installed: Mapping[str, Any]) -> None:
    _atomic_json(
        _control_state_path(profile_id),
        {
            "version": "io.tobkiri.pack-control-state.v4",
            "profile_id": profile_id,
            "installed": dict(installed),
        },
    )


def _atomic_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.parent.is_symlink() or path.is_symlink():
        raise PackControlDenied("Pack control persistence boundary is symlinked")
    descriptor, temporary = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(
                dict(value), handle, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            )
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, 0o600)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _pack(arguments: Mapping[str, Any]) -> tuple[str, Mapping[str, Any], Path]:
    pack_id = _required(arguments.get("pack_id"), "Pack ID")
    record = load_pack_catalog().get(pack_id)
    if record is None:
        raise PackControlDenied("Pack is absent from the canonical v4 catalog")
    root = resolve_pack_root(pack_id)
    return pack_id, record, root


def _installed_pack(arguments: Mapping[str, Any], binding: _Binding) -> str:
    pack_id, record, _root = _pack(arguments)
    active = set(_active_profile()[1].get("packs") or [])
    installed = _read_control_state(binding.profile_id)
    if pack_id not in active and pack_id not in installed:
        raise PackControlDenied("Pack must be installed before this operation")
    entry = installed.get(pack_id)
    if entry is not None:
        _require_install_binding(pack_id, record, entry, binding)
    return pack_id


def _require_install_binding(
    pack_id: str,
    record: Mapping[str, Any],
    entry: object,
    binding: _Binding,
) -> None:
    if not isinstance(entry, Mapping) or (
        entry.get("artifact_digest") != _record_digest(record)
        or entry.get("catalog_revision") != binding.catalog_revision
    ):
        raise PackControlDenied(f"installed Pack binding is stale or tampered: {pack_id}")


def _approval_path(profile_id: str, pack_id: str) -> Path:
    _safe_identity(profile_id, "Profile ID")
    _safe_identity(pack_id, "Pack ID")
    return Path(USER_DATA_DIR) / "pack_control" / "approvals" / profile_id / f"{pack_id}.json"


def _authority_key() -> bytes:
    from .hmac_key_manager import generate_or_load_signing_key

    return generate_or_load_signing_key(Path(USER_DATA_DIR) / "pack_control" / ".authority_key")


def _persist_approval(pack_id: str, content_digest: str, binding: _Binding) -> None:
    record = load_pack_catalog()[pack_id]
    payload = {
        "version": "io.tobkiri.pack-approval.v4",
        "pack_id": pack_id,
        "owner": str(record.get("pack_id") or ""),
        "profile_id": binding.profile_id,
        "workspace_id": binding.workspace_id,
        "catalog_revision": binding.catalog_revision,
        "artifact_digest": _record_digest(record),
        "content_digest": content_digest,
        "captured_profile_revision": binding.profile_revision,
        "approved_at": int(time.time()),
    }
    payload["approval_revision"] = "sha256:" + _digest(
        {
            key: payload[key]
            for key in (
                "pack_id",
                "owner",
                "profile_id",
                "workspace_id",
                "catalog_revision",
                "artifact_digest",
                "content_digest",
            )
        }
    )
    payload["signature"] = hmac.new(
        _authority_key(),
        _canonical_bytes(payload),
        hashlib.sha256,
    ).hexdigest()
    _atomic_json(_approval_path(binding.profile_id, pack_id), payload)


def _approval_status(
    pack_id: str, record: Mapping[str, Any], binding: _Binding
) -> tuple[bool, str | None]:
    active_packs = set(_active_profile()[1].get("packs") or [])
    if pack_id in active_packs:
        return True, None
    path = _approval_path(binding.profile_id, pack_id)
    if path.is_symlink():
        return False, "approval_symlinked"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return False, "approval_required"
    except (OSError, json.JSONDecodeError):
        return False, "approval_unreadable"
    if not isinstance(payload, dict):
        return False, "approval_invalid"
    signature = str(payload.pop("signature", ""))
    expected_signature = hmac.new(
        _authority_key(),
        _canonical_bytes(payload),
        hashlib.sha256,
    ).hexdigest()
    if not signature or not hmac.compare_digest(signature, expected_signature):
        return False, "approval_signature_invalid"
    expected = {
        "version": "io.tobkiri.pack-approval.v4",
        "pack_id": pack_id,
        "owner": pack_id,
        "profile_id": binding.profile_id,
        "workspace_id": binding.workspace_id,
        "catalog_revision": binding.catalog_revision,
        "artifact_digest": _record_digest(record),
    }
    if any(payload.get(key) != value for key, value in expected.items()):
        return False, "approval_binding_invalid"
    revision = "sha256:" + _digest(
        {
            key: payload.get(key)
            for key in (
                "pack_id",
                "owner",
                "profile_id",
                "workspace_id",
                "catalog_revision",
                "artifact_digest",
                "content_digest",
            )
        }
    )
    if payload.get("approval_revision") != revision:
        return False, "approval_revision_invalid"
    try:
        current = _pack_snapshot(pack_id, resolve_pack_root(pack_id))
    except PackControlDenied:
        return False, "pack_integrity_invalid"
    if not hmac.compare_digest(str(payload.get("content_digest") or ""), current):
        return False, "hash_mismatch"
    return True, None


def _pack_snapshot(pack_id: str, root: Path) -> str:
    if root.is_symlink() or not root.is_dir():
        raise PackControlDenied("cataloged Pack root is missing or symlinked")
    resolved_root = root.resolve(strict=True)
    files: dict[str, str] = {}
    pending = [root]
    while pending:
        directory = pending.pop()
        with os.scandir(directory) as scan:
            entries = sorted(scan, key=lambda entry: entry.name)
        for entry in entries:
            path = Path(entry.path)
            if entry.is_symlink():
                raise PackControlDenied("cataloged Pack contains a symlink")
            if entry.is_dir(follow_symlinks=False):
                pending.append(path)
                continue
            if not entry.is_file(follow_symlinks=False):
                continue
            resolved = path.resolve(strict=True)
            if not resolved.is_relative_to(resolved_root):
                raise PackControlDenied("cataloged Pack path escapes its boundary")
            relative = path.relative_to(root).as_posix()
            if "__pycache__" in path.parts or path.suffix in {".pyc", ".pyo"}:
                continue
            files[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
    if not files:
        raise PackControlDenied("cataloged Pack has no verifiable artifacts")
    return "sha256:" + _digest({"pack_id": pack_id, "files": files})


def _canonical_bytes(value: Mapping[str, Any]) -> bytes:
    return json.dumps(
        dict(value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _required(value: object, label: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise PackControlDenied(f"{label} is required")
    return normalized


def _safe_identity(value: object, label: str) -> str:
    normalized = _required(value, label)
    allowed = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_.-")
    if (
        len(normalized) > 128
        or normalized in {".", ".."}
        or any(character not in allowed for character in normalized)
    ):
        raise PackControlDenied(f"{label} is invalid")
    return normalized


def _record_digest(record: Mapping[str, Any]) -> str:
    return "sha256:" + _digest(record)


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
    ).hexdigest()


__all__ = [
    "CapturedPackCatalogReader",
    "CapturedPackControlSession",
    "PACK_CONTROL_CONTRACT",
    "PACK_CONTROL_OPERATIONS",
    "PackControlDenied",
    "capture_pack_catalog_reader",
    "capture_pack_control_session",
]
