"""Typed Host-owned lifecycle for the explicitly provisioned v4 PackVM."""

from __future__ import annotations

import secrets
import threading
import hashlib
import hmac
import json
import os
import re
import stat
import tempfile
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any, Mapping

from core_runtime.hmac_key_manager import generate_or_load_signing_key
from ecosystem.defaultspack.backend.sandbox.isolation.lima_runtime import (
    PACKVM_CLEANUP_PREFIX,
    PackVMLimaProvisioner,
    PackVMProvisioningPlan,
    PackVMProvisioningRequest,
)


class PackVMLifecycleV4:
    """Enforce prepare, explicit consent, and one-shot provision ceremonies."""

    def __init__(self, provisioner: PackVMLimaProvisioner | None = None) -> None:
        self._provisioner = provisioner or PackVMLimaProvisioner()
        self._lock = threading.RLock()
        self._plans: dict[str, PackVMProvisioningPlan] = {}
        self._consents: dict[str, PackVMProvisioningRequest] = {}
        self._operations_path = self._provisioner.state_path.parent / "packvm-operations.json"
        self._operations_key_path = self._provisioner.state_path.parent / "packvm-operations.key"
        self._operations = self._load_operations()
        if self._operations:
            self._persist_operations()

    def prepare(self) -> Mapping[str, Any]:
        """Return pinned download and runtime facts without provisioning."""

        with self._lock:
            plan = self._provisioner.prepare()
            self._plans.clear()
            self._plans[plan.ceremony_nonce] = plan
            return asdict(plan)

    def consent(self, payload: Mapping[str, object]) -> Mapping[str, Any]:
        """Capture explicit consent for one exact, previously displayed plan."""

        expected_keys = {
            "plan_digest",
            "ceremony_nonce",
            "confirmation",
            "approve_image_download",
        }
        if set(payload) != expected_keys:
            raise ValueError("PackVM consent payload does not match the typed contract")
        plan_digest = payload.get("plan_digest")
        ceremony_nonce = payload.get("ceremony_nonce")
        confirmation = payload.get("confirmation")
        approve_download = payload.get("approve_image_download")
        if (
            not isinstance(plan_digest, str)
            or not isinstance(ceremony_nonce, str)
            or not isinstance(confirmation, str)
            or not isinstance(approve_download, bool)
        ):
            raise ValueError("PackVM consent payload types are invalid")
        with self._lock:
            plan = self._plans.pop(ceremony_nonce, None)
            if (
                plan is None
                or not secrets.compare_digest(plan.plan_digest, plan_digest)
                or not secrets.compare_digest(plan.confirmation, confirmation)
            ):
                raise ValueError("PackVM consent does not match a pending plan")
            if plan.image_download_required and not approve_download:
                raise ValueError(
                    "PackVM image download requires explicit consent for the displayed source, size, and digest"
                )
            consent_id = "packvm-consent." + secrets.token_hex(24)
            self._consents.clear()
            self._consents[consent_id] = PackVMProvisioningRequest(
                plan_digest=plan_digest,
                ceremony_nonce=ceremony_nonce,
                confirmation=confirmation,
                approve_image_download=approve_download,
            )
            return {
                "consent_id": consent_id,
                "plan_digest": plan.plan_digest,
                "image_source": plan.image_source,
                "image_digest": plan.image_digest,
                "image_size_bytes": plan.image_size_bytes,
                "image_download_approved": approve_download,
            }

    def provision(self, payload: Mapping[str, object]) -> Mapping[str, Any]:
        """Start one idempotent background provisioning operation."""

        if set(payload) != {"consent_id", "operation_id"} or not all(
            isinstance(payload.get(field), str) for field in ("consent_id", "operation_id")
        ):
            raise ValueError("PackVM provision payload does not match the typed contract")
        consent_id = str(payload["consent_id"])
        operation_id = str(payload["operation_id"])
        if re.fullmatch(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", operation_id) is None:
            raise ValueError("PackVM operation_id must be a canonical UUID")
        with self._lock:
            existing = self._operations.get(operation_id)
            if existing is not None:
                if existing.get("consent_digest") != _digest_text(consent_id):
                    raise ValueError("PackVM operation_id is already bound to another consent")
                return dict(existing)
            if len(self._operations) >= 128:
                raise ValueError("PackVM operation journal capacity is exhausted")
            request = self._consents.pop(consent_id, None)
            if request is None:
                raise ValueError("PackVM consent is missing or already consumed")
            record: dict[str, Any] = {
                "operation_id": operation_id,
                "consent_digest": _digest_text(consent_id),
                "state": "queued",
                "plan_digest": request.plan_digest,
                "updated_unix": int(time.time()),
            }
            self._operations[operation_id] = record
            self._persist_operations()
            worker = threading.Thread(
                target=self._run_provision,
                args=(operation_id, request),
                daemon=True,
                name=f"packvm-provision-{operation_id[:8]}",
            )
            worker.start()
            return dict(record)

    def progress(self, operation_id: str) -> Mapping[str, Any]:
        """Return one persisted operation state across process restarts."""

        with self._lock:
            record = self._operations.get(operation_id)
            if record is None:
                raise ValueError("PackVM operation_id is unknown")
            return dict(record)

    def cancel(self, payload: Mapping[str, object]) -> Mapping[str, Any]:
        """Cancel only a queued operation; running provisioning is fenced."""

        if set(payload) != {"operation_id"} or not isinstance(payload.get("operation_id"), str):
            raise ValueError("PackVM cancel payload does not match the typed contract")
        operation_id = str(payload["operation_id"])
        with self._lock:
            record = self._operations.get(operation_id)
            if record is None:
                raise ValueError("PackVM operation_id is unknown")
            if record.get("state") == "queued":
                record["state"] = "cancelled"
                record["updated_unix"] = int(time.time())
                self._persist_operations()
            elif record.get("state") not in {"cancelled", "succeeded", "failed"}:
                raise ValueError("PackVM provisioning cannot be cancelled after it starts")
            return dict(record)

    def doctor(self) -> Mapping[str, Any]:
        """Return authenticated health without mutating the VM."""

        with self._lock:
            return asdict(self._provisioner.doctor())

    def stop(self, payload: Mapping[str, object]) -> Mapping[str, Any]:
        """Stop only the authenticated v4 instance after exact confirmation."""

        if set(payload) != {"confirmation"} or not isinstance(payload.get("confirmation"), str):
            raise ValueError("PackVM stop payload does not match the typed contract")
        with self._lock:
            self._provisioner.stop(str(payload["confirmation"]))
            return asdict(self._provisioner.doctor())

    def cleanup(self, payload: Mapping[str, object]) -> Mapping[str, Any]:
        """Delete only the authenticated v4 instance after exact confirmation."""

        if set(payload) != {"confirmation"} or not isinstance(payload.get("confirmation"), str):
            raise ValueError("PackVM cleanup payload does not match the typed contract")
        with self._lock:
            instance = str(self._provisioner.doctor().instance)
            self._provisioner.cleanup(str(payload["confirmation"]))
            return {
                "ready": False,
                "instance": instance,
                "cleanup_confirmation": f"{PACKVM_CLEANUP_PREFIX} {instance}",
            }

    def _run_provision(
        self,
        operation_id: str,
        request: PackVMProvisioningRequest,
    ) -> None:
        with self._lock:
            record = self._operations[operation_id]
            if record.get("state") == "cancelled":
                return
            record["state"] = "running"
            record["updated_unix"] = int(time.time())
            self._persist_operations()
        try:
            doctor = asdict(self._provisioner.provision(request))
        except Exception as error:
            with self._lock:
                record = self._operations[operation_id]
                record.update(
                    {
                        "state": "failed",
                        "error": str(error),
                        "error_type": type(error).__name__,
                        "updated_unix": int(time.time()),
                    }
                )
                self._persist_operations()
            return
        with self._lock:
            record = self._operations[operation_id]
            record.update(
                {
                    "state": "succeeded",
                    "doctor": doctor,
                    "updated_unix": int(time.time()),
                }
            )
            self._persist_operations()

    def _load_operations(self) -> dict[str, dict[str, Any]]:
        path = self._operations_path
        try:
            metadata = path.lstat()
        except FileNotFoundError:
            return {}
        if (
            path.is_symlink()
            or not stat.S_ISREG(metadata.st_mode)
            or metadata.st_size > 1024 * 1024
            or metadata.st_mode & 0o077
            or (hasattr(os, "getuid") and metadata.st_uid != os.getuid())
        ):
            raise ValueError("PackVM operation state is unsafe")
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or payload.get("version") != 1:
            raise ValueError("PackVM operation state is invalid")
        authentication = payload.pop("authentication", None)
        if not isinstance(authentication, str):
            raise ValueError("PackVM operation state is unauthenticated")
        key = _read_private_key(self._operations_key_path)
        expected = hmac.new(
            key,
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode(),
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(authentication, expected):
            raise ValueError("PackVM operation state authentication failed")
        raw_operations = payload.get("operations")
        if not isinstance(raw_operations, dict):
            raise ValueError("PackVM operation state is invalid")
        operations: dict[str, dict[str, Any]] = {}
        health = self._provisioner.doctor()
        for operation_id, raw in raw_operations.items():
            if not isinstance(operation_id, str) or not isinstance(raw, dict):
                raise ValueError("PackVM operation state is invalid")
            record = dict(raw)
            if record.get("state") in {"queued", "running"}:
                if health.ready:
                    record["state"] = "succeeded"
                    record["doctor"] = asdict(health)
                else:
                    record["state"] = "interrupted"
                    record["error"] = "Host restart interrupted provisioning; run doctor"
                record["updated_unix"] = int(time.time())
            operations[operation_id] = record
        return operations

    def _persist_operations(self) -> None:
        path = self._operations_path
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        unsigned = {"version": 1, "operations": self._operations}
        canonical = json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode()
        key = generate_or_load_signing_key(self._operations_key_path)
        payload = (
            json.dumps(
                {
                    **unsigned,
                    "authentication": hmac.new(key, canonical, hashlib.sha256).hexdigest(),
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
            + b"\n"
        )
        descriptor, temporary = tempfile.mkstemp(prefix=".packvm-operations-", dir=path.parent)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.chmod(temporary, 0o600)
            os.replace(temporary, path)
        finally:
            try:
                os.unlink(temporary)
            except OSError:
                pass


def _digest_text(value: str) -> str:
    return "sha256:" + hashlib.sha256(value.encode()).hexdigest()


def _read_private_key(path: Path) -> bytes:
    metadata = path.lstat()
    if (
        path.is_symlink()
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_size > 64
        or metadata.st_mode & 0o077
        or (hasattr(os, "getuid") and metadata.st_uid != os.getuid())
    ):
        raise ValueError("PackVM operation key is unsafe")
    return path.read_bytes()


__all__ = ["PackVMLifecycleV4"]
