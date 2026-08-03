"""Encrypted, crash-safe authority state and authoritative audit journal.

The store uses SQLite WAL transactions for atomic Grant-use, audit-reservation,
and InvocationLease issuance.  Authority payloads are encrypted at rest; indices
contain only opaque IDs and exact principal/domain digests needed for revocation.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import stat
import threading
import time
from collections.abc import Callable, Iterable, Mapping
from dataclasses import replace
from pathlib import Path
from typing import Any

from cryptography.fernet import Fernet, InvalidToken

from .v4_models import (
    ApprovalRecord,
    AuthorityDenied,
    AuthorityValidationError,
    DomainState,
    ExecutionDomain,
    GrantRecord,
    HostExtensionTrustRecord,
    InvocationLease,
    LeaseState,
    ProviderAuthorityRecord,
    SecurityEpoch,
    authority_digest,
    canonical_json,
)


class AuthorityStoreError(RuntimeError):
    """Raised when durable authority state cannot be read or committed."""


class AuditUnavailable(AuthorityStoreError):
    """Raised when an authoritative audit reservation cannot be committed."""


Record = (
    ProviderAuthorityRecord
    | ApprovalRecord
    | GrantRecord
    | ExecutionDomain
    | HostExtensionTrustRecord
)


def _fsync_directory(path: Path) -> None:
    try:
        descriptor = os.open(path, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


class AuthorityStore:
    """Host-owned authority database for ADR-014/015 state.

    Args:
        path: SQLite database path.
        key_path: Optional encryption/MAC key path.  Defaults next to the DB.
        clock: Injectable wall-clock function for deterministic tests.
        audit_fault: Optional fault-injection hook called before audit appends.
    """

    def __init__(
        self,
        path: str | Path,
        *,
        key_path: str | Path | None = None,
        clock: Callable[[], float] = time.time,
        audit_fault: Callable[[], None] | None = None,
    ) -> None:
        self.path = Path(path)
        parent_existed = self.path.parent.exists()
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.key_path = Path(key_path) if key_path is not None else self.path.with_suffix(".key")
        if self.path.is_symlink() or self.key_path.is_symlink():
            raise AuthorityStoreError("authority state paths cannot be symbolic links")
        if os.name != "nt" and not parent_existed:
            os.chmod(self.path.parent, 0o700)
        self._clock = clock
        self._audit_fault = audit_fault
        self._lock = threading.RLock()
        self._fernet_key = self._load_or_create_key()
        self._fernet = Fernet(self._fernet_key)
        self._mac_key = hashlib.sha256(self._fernet_key + b":lease-mac:v1").digest()
        self._initialize()
        if os.name != "nt":
            os.chmod(self.path, 0o600)

    def _load_or_create_key(self) -> bytes:
        try:
            key = self.key_path.read_bytes().strip()
            Fernet(key)
            if os.name != "nt":
                mode = stat.S_IMODE(self.key_path.stat().st_mode)
                if mode & 0o077:
                    raise AuthorityStoreError("authority encryption key permissions are too broad")
            return key
        except FileNotFoundError:
            pass
        except (OSError, ValueError) as exc:
            raise AuthorityStoreError("authority encryption key is invalid") from exc

        if self.path.exists() and self.path.stat().st_size > 0:
            raise AuthorityStoreError(
                "authority encryption key is missing for an existing database"
            )

        key = Fernet.generate_key()
        self.key_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.key_path.with_name(f".{self.key_path.name}.{secrets.token_hex(8)}.tmp")
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(key + b"\n")
                handle.flush()
                os.fsync(handle.fileno())
            try:
                os.link(temporary, self.key_path)
            except FileExistsError:
                existing = self.key_path.read_bytes().strip()
                Fernet(existing)
                return existing
            finally:
                temporary.unlink(missing_ok=True)
            _fsync_directory(self.key_path.parent)
        except (OSError, ValueError):
            temporary.unlink(missing_ok=True)
            raise
        return key

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            str(self.path),
            timeout=30.0,
            isolation_level=None,
            check_same_thread=False,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=FULL")
        connection.execute("PRAGMA trusted_schema=OFF")
        return connection

    def _initialize(self) -> None:
        with self._lock, self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS authority_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                ) STRICT;
                CREATE TABLE IF NOT EXISTS authority_records (
                    record_type TEXT NOT NULL,
                    record_id TEXT NOT NULL,
                    record_digest TEXT NOT NULL,
                    encrypted_payload BLOB NOT NULL,
                    created_at REAL NOT NULL,
                    PRIMARY KEY (record_type, record_id)
                ) STRICT;
                CREATE TABLE IF NOT EXISTS execution_sessions (
                    session_id TEXT PRIMARY KEY,
                    domain_id TEXT NOT NULL,
                    profile_id TEXT NOT NULL,
                    activation_id TEXT NOT NULL,
                    boot_epoch INTEGER NOT NULL,
                    channel_digest TEXT NOT NULL,
                    principal_id TEXT NOT NULL,
                    active INTEGER NOT NULL CHECK (active IN (0, 1)),
                    created_at REAL NOT NULL
                ) STRICT;
                CREATE TABLE IF NOT EXISTS grant_usage (
                    grant_id TEXT PRIMARY KEY,
                    reserved_uses INTEGER NOT NULL DEFAULT 0,
                    committed_uses INTEGER NOT NULL DEFAULT 0
                ) STRICT;
                CREATE TABLE IF NOT EXISTS invocation_leases (
                    lease_id TEXT PRIMARY KEY,
                    lease_digest TEXT NOT NULL,
                    encrypted_payload BLOB NOT NULL,
                    caller_principal_id TEXT NOT NULL,
                    target_principal_id TEXT NOT NULL,
                    caller_artifact_digest TEXT NOT NULL,
                    target_artifact_digest TEXT NOT NULL,
                    caller_publisher_lineage TEXT NOT NULL,
                    target_publisher_lineage TEXT NOT NULL,
                    host_extension_id TEXT NOT NULL,
                    caller_domain_id TEXT NOT NULL,
                    target_domain_id TEXT NOT NULL,
                    profile_id TEXT NOT NULL,
                    activation_id TEXT NOT NULL,
                    grant_id TEXT NOT NULL,
                    provider_authority_id TEXT NOT NULL,
                    audit_reservation_id TEXT NOT NULL,
                    security_epoch INTEGER NOT NULL,
                    expires_at REAL NOT NULL,
                    state TEXT NOT NULL,
                    outcome_digest TEXT
                ) STRICT;
                CREATE TABLE IF NOT EXISTS revocations (
                    revocation_id TEXT PRIMARY KEY,
                    target_kind TEXT NOT NULL,
                    target_id TEXT NOT NULL,
                    security_epoch INTEGER NOT NULL,
                    reason_digest TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    UNIQUE (target_kind, target_id)
                ) STRICT;
                CREATE INDEX IF NOT EXISTS revocations_target
                    ON revocations(target_kind, target_id);
                CREATE TABLE IF NOT EXISTS authority_audit (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT NOT NULL UNIQUE,
                    event_type TEXT NOT NULL,
                    event_state TEXT NOT NULL,
                    previous_digest TEXT NOT NULL,
                    event_digest TEXT NOT NULL,
                    encrypted_payload BLOB NOT NULL,
                    created_at REAL NOT NULL
                ) STRICT;
                """
            )
            connection.execute(
                "INSERT OR IGNORE INTO authority_meta(key, value) VALUES"
                " ('schema_version', '1'), ('security_epoch', '1')"
            )
            connection.execute(
                "INSERT OR IGNORE INTO authority_meta(key, value) VALUES (?, ?)",
                ("security_epoch_advanced_at", str(self._clock())),
            )
            connection.execute(
                "INSERT OR IGNORE INTO authority_meta(key, value) VALUES (?, ?)",
                (
                    "security_epoch_reason_digest",
                    authority_digest({"reason": "genesis"}),
                ),
            )

    def _encrypt(self, payload: Mapping[str, Any]) -> bytes:
        return self._fernet.encrypt(canonical_json(dict(payload)))

    def _decrypt(self, payload: bytes) -> dict[str, Any]:
        try:
            value = json.loads(self._fernet.decrypt(payload).decode("utf-8"))
        except (InvalidToken, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise AuthorityStoreError("authority record authentication failed") from exc
        if not isinstance(value, dict):
            raise AuthorityStoreError("authority record is not an object")
        return value

    @staticmethod
    def _record_type(record: Record) -> str:
        if isinstance(record, ProviderAuthorityRecord):
            return "provider_authority"
        if isinstance(record, ApprovalRecord):
            return "approval"
        if isinstance(record, GrantRecord):
            return "grant"
        if isinstance(record, ExecutionDomain):
            return "execution_domain"
        if isinstance(record, HostExtensionTrustRecord):
            return "host_extension_trust"
        raise TypeError(f"unsupported authority record: {type(record).__name__}")

    @staticmethod
    def _record_id(record: Record) -> str:
        if isinstance(record, ProviderAuthorityRecord):
            return record.record_id
        if isinstance(record, ApprovalRecord):
            return record.approval_id
        if isinstance(record, GrantRecord):
            return record.grant_id
        if isinstance(record, ExecutionDomain):
            return record.domain_id
        return record.trust_id

    def put_record(self, record: Record, *, replace: bool = False) -> None:
        """Persist an encrypted record, rejecting accidental mutation by default."""

        record_type = self._record_type(record)
        record_id = self._record_id(record)
        payload = record.to_dict()
        digest = authority_digest(payload)
        operation = "INSERT OR REPLACE" if replace else "INSERT"
        try:
            with self._lock, self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute(
                    f"{operation} INTO authority_records"
                    " (record_type, record_id, record_digest, encrypted_payload, created_at)"
                    " VALUES (?, ?, ?, ?, ?)",
                    (record_type, record_id, digest, self._encrypt(payload), self._clock()),
                )
                if isinstance(record, GrantRecord):
                    connection.execute(
                        "INSERT OR IGNORE INTO grant_usage(grant_id) VALUES (?)",
                        (record.grant_id,),
                    )
                connection.commit()
        except sqlite3.IntegrityError as exc:
            raise AuthorityStoreError("authority record is immutable") from exc
        except (sqlite3.Error, OSError) as exc:
            raise AuthorityStoreError("authority record commit failed") from exc

    def put_records_atomically(self, records: Iterable[Record]) -> None:
        """Commit an approval transaction without leaving partial authority."""

        pending = list(records)
        if not pending:
            raise ValueError("authority transaction cannot be empty")
        try:
            with self._lock, self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                for record in pending:
                    record_type = self._record_type(record)
                    record_id = self._record_id(record)
                    payload = record.to_dict()
                    connection.execute(
                        "INSERT INTO authority_records"
                        " (record_type, record_id, record_digest, encrypted_payload,"
                        " created_at) VALUES (?, ?, ?, ?, ?)",
                        (
                            record_type,
                            record_id,
                            authority_digest(payload),
                            self._encrypt(payload),
                            self._clock(),
                        ),
                    )
                    if isinstance(record, GrantRecord):
                        connection.execute(
                            "INSERT INTO grant_usage(grant_id) VALUES (?)",
                            (record.grant_id,),
                        )
                self._append_audit(
                    connection,
                    event_id="authority-txn-" + secrets.token_hex(16),
                    event_type="authority_records_committed",
                    event_state="committed",
                    payload={
                        "records": [
                            {
                                "record_type": self._record_type(record),
                                "record_id": self._record_id(record),
                                "record_digest": authority_digest(record.to_dict()),
                            }
                            for record in pending
                        ]
                    },
                )
                connection.commit()
        except AuditUnavailable:
            raise
        except sqlite3.IntegrityError as exc:
            raise AuthorityStoreError("authority transaction conflicts") from exc
        except sqlite3.Error as exc:
            raise AuthorityStoreError("authority transaction failed") from exc

    def get_provider_authority(self, record_id: str) -> ProviderAuthorityRecord | None:
        """Load and authenticate a ProviderAuthorityRecord."""

        value = self._get_record("provider_authority", record_id)
        return ProviderAuthorityRecord.from_dict(value) if value else None

    def get_approval(self, approval_id: str) -> ApprovalRecord | None:
        """Load and authenticate an ApprovalRecord."""

        value = self._get_record("approval", approval_id)
        return ApprovalRecord.from_dict(value) if value else None

    def get_grant(self, grant_id: str) -> GrantRecord | None:
        """Load and authenticate a GrantRecord."""

        value = self._get_record("grant", grant_id)
        return GrantRecord.from_dict(value) if value else None

    def get_domain(self, domain_id: str) -> ExecutionDomain | None:
        """Load and authenticate an ExecutionDomain."""

        value = self._get_record("execution_domain", domain_id)
        return ExecutionDomain.from_dict(value) if value else None

    def get_host_extension_trust(self, trust_id: str) -> HostExtensionTrustRecord | None:
        """Load and authenticate a HostExtensionTrustRecord."""

        value = self._get_record("host_extension_trust", trust_id)
        return HostExtensionTrustRecord.from_dict(value) if value else None

    def _get_record(self, record_type: str, record_id: str) -> dict[str, Any] | None:
        try:
            with self._lock, self._connect() as connection:
                row = connection.execute(
                    "SELECT record_digest, encrypted_payload FROM authority_records"
                    " WHERE record_type=? AND record_id=?",
                    (record_type, record_id),
                ).fetchone()
        except sqlite3.Error as exc:
            raise AuthorityStoreError("authority record read failed") from exc
        if row is None:
            return None
        value = self._decrypt(row["encrypted_payload"])
        if not hmac.compare_digest(str(row["record_digest"]), authority_digest(value)):
            raise AuthorityStoreError("authority record digest mismatch")
        return value

    def list_grants(self) -> list[GrantRecord]:
        """Return all authenticated Grants; callers must still filter exactly."""

        return [GrantRecord.from_dict(value) for value in self._list_records("grant")]

    def list_provider_authorities(self) -> list[ProviderAuthorityRecord]:
        """Return all authenticated Provider authority records."""

        return [
            ProviderAuthorityRecord.from_dict(value)
            for value in self._list_records("provider_authority")
        ]

    def list_domains(self) -> list[ExecutionDomain]:
        """Return all authenticated execution-domain records."""

        return [
            ExecutionDomain.from_dict(value) for value in self._list_records("execution_domain")
        ]

    def _list_records(self, record_type: str) -> list[dict[str, Any]]:
        try:
            with self._lock, self._connect() as connection:
                rows = connection.execute(
                    "SELECT record_digest, encrypted_payload FROM authority_records"
                    " WHERE record_type=? ORDER BY record_id",
                    (record_type,),
                ).fetchall()
        except sqlite3.Error as exc:
            raise AuthorityStoreError("authority record listing failed") from exc
        output: list[dict[str, Any]] = []
        for row in rows:
            value = self._decrypt(row["encrypted_payload"])
            if not hmac.compare_digest(str(row["record_digest"]), authority_digest(value)):
                raise AuthorityStoreError("authority record digest mismatch")
            output.append(value)
        return output

    @property
    def security_epoch(self) -> int:
        """Return the Host-owned monotonic SecurityEpoch."""

        try:
            with self._lock, self._connect() as connection:
                row = connection.execute(
                    "SELECT value FROM authority_meta WHERE key='security_epoch'"
                ).fetchone()
        except sqlite3.Error as exc:
            raise AuthorityStoreError("security epoch read failed") from exc
        if row is None or int(row["value"]) < 1:
            raise AuthorityStoreError("security epoch is unavailable")
        return int(row["value"])

    @property
    def security_epoch_record(self) -> SecurityEpoch:
        """Return the complete current SecurityEpoch metadata."""

        try:
            with self._lock, self._connect() as connection:
                rows = connection.execute(
                    "SELECT key, value FROM authority_meta WHERE key IN"
                    " ('security_epoch', 'security_epoch_advanced_at',"
                    " 'security_epoch_reason_digest')"
                ).fetchall()
        except sqlite3.Error as exc:
            raise AuthorityStoreError("security epoch metadata read failed") from exc
        values = {str(row["key"]): str(row["value"]) for row in rows}
        try:
            return SecurityEpoch(
                value=int(values["security_epoch"]),
                advanced_at=float(values["security_epoch_advanced_at"]),
                reason_digest=values["security_epoch_reason_digest"],
            )
        except (KeyError, TypeError, ValueError, AuthorityValidationError) as exc:
            raise AuthorityStoreError("security epoch metadata is invalid") from exc

    def advance_security_epoch(self, reason: str) -> int:
        """Atomically advance SecurityEpoch and fence all old domains and Leases."""

        reason_digest = authority_digest({"reason": str(reason)})
        try:
            with self._lock, self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                row = connection.execute(
                    "SELECT value FROM authority_meta WHERE key='security_epoch'"
                ).fetchone()
                if row is None:
                    raise AuthorityStoreError("security epoch is unavailable")
                next_epoch = int(row["value"]) + 1
                connection.execute(
                    "UPDATE authority_meta SET value=? WHERE key='security_epoch'",
                    (str(next_epoch),),
                )
                connection.execute(
                    "UPDATE authority_meta SET value=? WHERE key='security_epoch_advanced_at'",
                    (str(self._clock()),),
                )
                connection.execute(
                    "UPDATE authority_meta SET value=? WHERE key='security_epoch_reason_digest'",
                    (reason_digest,),
                )
                connection.execute(
                    "UPDATE invocation_leases SET state=? WHERE security_epoch < ?"
                    " AND state IN (?, ?)",
                    (
                        LeaseState.REVOKED.value,
                        next_epoch,
                        LeaseState.ISSUED.value,
                        LeaseState.DISPATCHED.value,
                    ),
                )
                connection.execute("UPDATE execution_sessions SET active=0")
                self._append_audit(
                    connection,
                    event_id=f"epoch-{next_epoch}",
                    event_type="security_epoch_advanced",
                    event_state="committed",
                    payload={
                        "security_epoch": next_epoch,
                        "reason_digest": reason_digest,
                    },
                )
                connection.commit()
                return next_epoch
        except AuditUnavailable:
            raise
        except (sqlite3.Error, OSError) as exc:
            raise AuthorityStoreError("security epoch advance failed") from exc

    def bind_authenticated_session(
        self,
        *,
        session_id: str,
        domain: ExecutionDomain,
        channel_digest: str,
        principal_id: str,
    ) -> None:
        """Bind an authenticated channel to a Host-spawned domain principal."""

        if domain.state.value != "active":
            raise AuthorityDenied("execution domain is not active", code="domain_inactive")
        if domain.security_epoch != self.security_epoch:
            raise AuthorityDenied("execution domain has a stale SecurityEpoch", code="stale_epoch")
        if channel_digest != domain.authenticated_channel_digest:
            raise AuthorityDenied("authenticated channel does not match domain")
        if principal_id not in domain.principal_ids:
            raise AuthorityDenied("principal is not assigned to execution domain")
        persisted = self.get_domain(domain.domain_id)
        if persisted is None or persisted.identity_digest != domain.identity_digest:
            raise AuthorityDenied("execution domain is not registered")
        try:
            with self._lock, self._connect() as connection:
                connection.execute(
                    "INSERT INTO execution_sessions"
                    " (session_id, domain_id, profile_id, activation_id, boot_epoch,"
                    " channel_digest, principal_id, active, created_at)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?)",
                    (
                        session_id,
                        domain.domain_id,
                        domain.profile_id,
                        domain.activation_id,
                        domain.boot_epoch,
                        channel_digest,
                        principal_id,
                        self._clock(),
                    ),
                )
        except sqlite3.IntegrityError as exc:
            raise AuthorityDenied("authenticated session cannot be replayed") from exc
        except sqlite3.Error as exc:
            raise AuthorityStoreError("session binding failed") from exc

    def transition_domain(
        self,
        domain_id: str,
        *,
        expected_boot_epoch: int,
        expected_state: DomainState,
        new_state: DomainState,
    ) -> ExecutionDomain:
        """Durably transition an ExecutionDomain with compare-and-swap semantics."""

        allowed = {
            DomainState.STARTING: {
                DomainState.ACTIVE,
                DomainState.REVOKED,
                DomainState.STOPPED,
            },
            DomainState.ACTIVE: {
                DomainState.DRAINING,
                DomainState.FENCED,
                DomainState.REVOKED,
                DomainState.STOPPED,
            },
            DomainState.DRAINING: {
                DomainState.FENCED,
                DomainState.REVOKED,
                DomainState.STOPPED,
            },
            DomainState.FENCED: {DomainState.REVOKED, DomainState.STOPPED},
            DomainState.REVOKED: {DomainState.STOPPED},
            DomainState.STOPPED: set(),
        }
        if new_state not in allowed[expected_state]:
            raise AuthorityDenied("invalid execution-domain lifecycle transition")
        try:
            with self._lock, self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                row = connection.execute(
                    "SELECT encrypted_payload FROM authority_records"
                    " WHERE record_type='execution_domain' AND record_id=?",
                    (domain_id,),
                ).fetchone()
                if row is None:
                    raise AuthorityDenied("execution domain is unavailable")
                current = ExecutionDomain.from_dict(self._decrypt(row["encrypted_payload"]))
                if current.boot_epoch != expected_boot_epoch or current.state is not expected_state:
                    raise AuthorityDenied("execution-domain lifecycle CAS failed")
                updated = replace(current, state=new_state)
                payload = updated.to_dict()
                connection.execute(
                    "UPDATE authority_records SET record_digest=?, encrypted_payload=?"
                    " WHERE record_type='execution_domain' AND record_id=?",
                    (authority_digest(payload), self._encrypt(payload), domain_id),
                )
                if new_state is not DomainState.ACTIVE:
                    connection.execute(
                        "UPDATE execution_sessions SET active=0 WHERE domain_id=?",
                        (domain_id,),
                    )
                if new_state in {
                    DomainState.FENCED,
                    DomainState.REVOKED,
                    DomainState.STOPPED,
                }:
                    connection.execute(
                        "UPDATE invocation_leases SET state=?"
                        " WHERE (caller_domain_id=? OR target_domain_id=?)"
                        " AND state IN (?, ?)",
                        (
                            LeaseState.REVOKED.value,
                            domain_id,
                            domain_id,
                            LeaseState.ISSUED.value,
                            LeaseState.DISPATCHED.value,
                        ),
                    )
                self._append_audit(
                    connection,
                    event_id="domain-transition-" + secrets.token_hex(16),
                    event_type="execution_domain_lifecycle",
                    event_state="committed",
                    payload={
                        "domain_id": domain_id,
                        "boot_epoch": expected_boot_epoch,
                        "old_state": expected_state.value,
                        "new_state": new_state.value,
                        "security_epoch": updated.security_epoch,
                    },
                )
                connection.commit()
                return updated
        except AuthorityDenied:
            raise
        except AuditUnavailable:
            raise
        except sqlite3.Error as exc:
            raise AuthorityStoreError("execution-domain transition failed") from exc

    def resolve_authenticated_session(self, session_id: str) -> tuple[ExecutionDomain, str]:
        """Resolve Host-authenticated caller identity; never use payload identity."""

        try:
            with self._lock, self._connect() as connection:
                row = connection.execute(
                    "SELECT domain_id, boot_epoch, channel_digest, principal_id, active"
                    " FROM execution_sessions WHERE session_id=?",
                    (session_id,),
                ).fetchone()
        except sqlite3.Error as exc:
            raise AuthorityStoreError("session lookup failed") from exc
        if row is None or not row["active"]:
            raise AuthorityDenied("caller session is unknown or inactive")
        domain = self.get_domain(str(row["domain_id"]))
        if domain is None:
            raise AuthorityDenied("caller execution domain is unavailable")
        if (
            domain.boot_epoch != int(row["boot_epoch"])
            or domain.authenticated_channel_digest != str(row["channel_digest"])
            or domain.state.value != "active"
            or domain.security_epoch != self.security_epoch
        ):
            raise AuthorityDenied("caller execution domain identity is stale")
        principal_id = str(row["principal_id"])
        if principal_id not in domain.principal_ids:
            raise AuthorityDenied("caller principal binding is invalid")
        return domain, principal_id

    def revoke(
        self,
        *,
        target_kind: str,
        target_id: str,
        reason: str,
    ) -> str:
        """Persist a revocation and immediately fence matching Lease/session state."""

        allowed_kinds = {
            "function_principal",
            "execution_domain",
            "pack_artifact",
            "publisher",
            "credential",
            "resource_root",
            "profile",
            "workflow",
            "host_extension",
            "grant",
            "provider_authority",
            "activation",
            "global",
        }
        if target_kind not in allowed_kinds:
            raise ValueError("unsupported revocation target")
        revocation_id = "rev-" + secrets.token_hex(16)
        reason_digest = authority_digest({"reason": str(reason)})
        epoch = self.security_epoch
        try:
            with self._lock, self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute(
                    "INSERT INTO revocations"
                    " (revocation_id, target_kind, target_id, security_epoch,"
                    " reason_digest, created_at) VALUES (?, ?, ?, ?, ?, ?)"
                    " ON CONFLICT(target_kind, target_id) DO NOTHING",
                    (
                        revocation_id,
                        target_kind,
                        target_id,
                        epoch,
                        reason_digest,
                        self._clock(),
                    ),
                )
                if target_kind == "execution_domain":
                    connection.execute(
                        "UPDATE execution_sessions SET active=0 WHERE domain_id=?",
                        (target_id,),
                    )
                    connection.execute(
                        "UPDATE invocation_leases SET state=?"
                        " WHERE (caller_domain_id=? OR target_domain_id=?)"
                        " AND state IN (?, ?)",
                        (
                            LeaseState.REVOKED.value,
                            target_id,
                            target_id,
                            LeaseState.ISSUED.value,
                            LeaseState.DISPATCHED.value,
                        ),
                    )
                elif target_kind == "function_principal":
                    connection.execute(
                        "UPDATE invocation_leases SET state=?"
                        " WHERE (caller_principal_id=? OR target_principal_id=?)"
                        " AND state IN (?, ?)",
                        (
                            LeaseState.REVOKED.value,
                            target_id,
                            target_id,
                            LeaseState.ISSUED.value,
                            LeaseState.DISPATCHED.value,
                        ),
                    )
                elif target_kind == "pack_artifact":
                    connection.execute(
                        "UPDATE invocation_leases SET state=?"
                        " WHERE (caller_artifact_digest=? OR target_artifact_digest=?)"
                        " AND state IN (?, ?)",
                        (
                            LeaseState.REVOKED.value,
                            target_id,
                            target_id,
                            LeaseState.ISSUED.value,
                            LeaseState.DISPATCHED.value,
                        ),
                    )
                elif target_kind == "publisher":
                    connection.execute(
                        "UPDATE invocation_leases SET state=?"
                        " WHERE (caller_publisher_lineage=?"
                        " OR target_publisher_lineage=?) AND state IN (?, ?)",
                        (
                            LeaseState.REVOKED.value,
                            target_id,
                            target_id,
                            LeaseState.ISSUED.value,
                            LeaseState.DISPATCHED.value,
                        ),
                    )
                elif target_kind == "host_extension":
                    connection.execute(
                        "UPDATE invocation_leases SET state=?"
                        " WHERE host_extension_id=? AND state IN (?, ?)",
                        (
                            LeaseState.REVOKED.value,
                            target_id,
                            LeaseState.ISSUED.value,
                            LeaseState.DISPATCHED.value,
                        ),
                    )
                elif target_kind == "profile":
                    connection.execute(
                        "UPDATE execution_sessions SET active=0 WHERE profile_id=?",
                        (target_id,),
                    )
                    connection.execute(
                        "UPDATE invocation_leases SET state=? WHERE profile_id=?"
                        " AND state IN (?, ?)",
                        (
                            LeaseState.REVOKED.value,
                            target_id,
                            LeaseState.ISSUED.value,
                            LeaseState.DISPATCHED.value,
                        ),
                    )
                elif target_kind == "grant":
                    connection.execute(
                        "UPDATE invocation_leases SET state=? WHERE grant_id=? AND state IN (?, ?)",
                        (
                            LeaseState.REVOKED.value,
                            target_id,
                            LeaseState.ISSUED.value,
                            LeaseState.DISPATCHED.value,
                        ),
                    )
                elif target_kind == "provider_authority":
                    connection.execute(
                        "UPDATE invocation_leases SET state=?"
                        " WHERE provider_authority_id=? AND state IN (?, ?)",
                        (
                            LeaseState.REVOKED.value,
                            target_id,
                            LeaseState.ISSUED.value,
                            LeaseState.DISPATCHED.value,
                        ),
                    )
                elif target_kind == "activation":
                    connection.execute(
                        "UPDATE execution_sessions SET active=0 WHERE activation_id=?",
                        (target_id,),
                    )
                    connection.execute(
                        "UPDATE invocation_leases SET state=?"
                        " WHERE activation_id=? AND state IN (?, ?)",
                        (
                            LeaseState.REVOKED.value,
                            target_id,
                            LeaseState.ISSUED.value,
                            LeaseState.DISPATCHED.value,
                        ),
                    )
                elif target_kind == "global":
                    connection.execute("UPDATE execution_sessions SET active=0")
                    connection.execute(
                        "UPDATE invocation_leases SET state=? WHERE state IN (?, ?)",
                        (
                            LeaseState.REVOKED.value,
                            LeaseState.ISSUED.value,
                            LeaseState.DISPATCHED.value,
                        ),
                    )
                self._append_audit(
                    connection,
                    event_id=revocation_id,
                    event_type="authority_revoked",
                    event_state="committed",
                    payload={
                        "target_kind": target_kind,
                        "target_id": target_id,
                        "security_epoch": epoch,
                        "reason_digest": reason_digest,
                    },
                )
                connection.commit()
        except AuditUnavailable:
            raise
        except sqlite3.Error as exc:
            raise AuthorityStoreError("revocation commit failed") from exc
        return revocation_id

    def is_revoked(self, target_kind: str, target_id: str) -> bool:
        """Return whether an exact target has an active Host revocation."""

        try:
            with self._lock, self._connect() as connection:
                return self._is_revoked(connection, target_kind, target_id)
        except sqlite3.Error as exc:
            raise AuthorityStoreError("revocation lookup failed") from exc

    @staticmethod
    def _is_revoked(connection: sqlite3.Connection, target_kind: str, target_id: str) -> bool:
        row = connection.execute(
            "SELECT 1 FROM revocations WHERE"
            " (target_kind=? AND target_id=?) OR target_kind='global' LIMIT 1",
            (target_kind, target_id),
        ).fetchone()
        return row is not None

    def issue_lease_with_audit(
        self,
        *,
        grant: GrantRecord,
        lease: InvocationLease,
        audit_payload: Mapping[str, Any],
        revocation_targets: Iterable[tuple[str, str]],
    ) -> str:
        """Atomically reserve Grant use, authoritative audit, and one Lease.

        If audit storage is unavailable every write is rolled back, including the
        Grant use.  This is the required fail-closed effect gate.
        """

        try:
            with self._lock, self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                epoch_row = connection.execute(
                    "SELECT value FROM authority_meta WHERE key='security_epoch'"
                ).fetchone()
                if epoch_row is None or int(epoch_row["value"]) != lease.security_epoch:
                    raise AuthorityDenied("SecurityEpoch changed", code="stale_epoch")
                for target_kind, target_id in revocation_targets:
                    if self._is_revoked(connection, target_kind, target_id):
                        raise AuthorityDenied(f"{target_kind} is revoked", code="revoked")
                grant_row = connection.execute(
                    "SELECT record_digest FROM authority_records"
                    " WHERE record_type='grant' AND record_id=?",
                    (grant.grant_id,),
                ).fetchone()
                if grant_row is None or not hmac.compare_digest(
                    str(grant_row["record_digest"]), grant.digest
                ):
                    raise AuthorityDenied("Grant definition changed or is unavailable")
                checked_domains: dict[str, ExecutionDomain] = {}
                for domain_id, boot_epoch, principal_id in (
                    (
                        lease.caller_domain_id,
                        lease.caller_boot_epoch,
                        lease.caller.principal_id,
                    ),
                    (
                        lease.target_domain_id,
                        lease.target_boot_epoch,
                        lease.target.principal_id,
                    ),
                ):
                    domain_row = connection.execute(
                        "SELECT encrypted_payload FROM authority_records"
                        " WHERE record_type='execution_domain' AND record_id=?",
                        (domain_id,),
                    ).fetchone()
                    if domain_row is None:
                        raise AuthorityDenied("execution domain is unavailable")
                    domain = ExecutionDomain.from_dict(
                        self._decrypt(domain_row["encrypted_payload"])
                    )
                    if (
                        domain.state is not DomainState.ACTIVE
                        or domain.boot_epoch != boot_epoch
                        or domain.security_epoch != lease.security_epoch
                        or domain.profile_id != lease.profile_id
                        or domain.activation_id != lease.activation_id
                        or domain.fencing_token != lease.fencing_token
                        or principal_id not in domain.principal_ids
                    ):
                        raise AuthorityDenied("execution domain changed before reservation")
                    checked_domains[domain_id] = domain
                target_domain = checked_domains[lease.target_domain_id]
                if target_domain.resource_namespace != lease.resource_namespace:
                    raise AuthorityDenied("ResourceHandle namespace changed")
                usage = connection.execute(
                    "SELECT reserved_uses, committed_uses FROM grant_usage WHERE grant_id=?",
                    (grant.grant_id,),
                ).fetchone()
                if usage is None:
                    raise AuthorityDenied("Grant is not registered")
                total_uses = int(usage["reserved_uses"]) + int(usage["committed_uses"])
                if grant.max_uses is not None and total_uses >= grant.max_uses:
                    raise AuthorityDenied("Grant use limit is exhausted")
                connection.execute(
                    "UPDATE grant_usage SET reserved_uses=reserved_uses+1 WHERE grant_id=?",
                    (grant.grant_id,),
                )
                self._append_audit(
                    connection,
                    event_id=lease.audit_reservation_id,
                    event_type="host_effect",
                    event_state="reserved",
                    payload=dict(audit_payload),
                )
                connection.execute(
                    "INSERT INTO invocation_leases"
                    " (lease_id, lease_digest, encrypted_payload, caller_principal_id,"
                    " target_principal_id, caller_artifact_digest, target_artifact_digest,"
                    " caller_publisher_lineage, target_publisher_lineage, host_extension_id,"
                    " caller_domain_id, target_domain_id, profile_id,"
                    " activation_id, grant_id, audit_reservation_id, security_epoch,"
                    " provider_authority_id, expires_at, state)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        lease.lease_id,
                        lease.digest,
                        self._encrypt(lease.to_dict()),
                        lease.caller.principal_id,
                        lease.target.principal_id,
                        lease.caller.parent_artifact_digest,
                        lease.target.parent_artifact_digest,
                        lease.caller_publisher_lineage,
                        lease.target_publisher_lineage,
                        lease.host_extension_id,
                        lease.caller_domain_id,
                        lease.target_domain_id,
                        lease.profile_id,
                        lease.activation_id,
                        lease.grant_id,
                        lease.audit_reservation_id,
                        lease.security_epoch,
                        lease.provider_authority_id,
                        lease.expires_at,
                        LeaseState.ISSUED.value,
                    ),
                )
                connection.commit()
        except AuthorityDenied:
            raise
        except AuditUnavailable:
            raise
        except (sqlite3.Error, OSError) as exc:
            raise AuditUnavailable("authority reservation could not be committed") from exc
        return self._encode_lease_token(lease)

    def _append_audit(
        self,
        connection: sqlite3.Connection,
        *,
        event_id: str,
        event_type: str,
        event_state: str,
        payload: Mapping[str, Any],
    ) -> str:
        if self._audit_fault is not None:
            try:
                self._audit_fault()
            except Exception as exc:
                raise AuditUnavailable("authoritative audit is unavailable") from exc
        previous = connection.execute(
            "SELECT event_digest FROM authority_audit ORDER BY sequence DESC LIMIT 1"
        ).fetchone()
        previous_digest = (
            str(previous["event_digest"]) if previous is not None else "sha256:" + "0" * 64
        )
        created_at = self._clock()
        event_digest = authority_digest(
            {
                "event_id": event_id,
                "event_type": event_type,
                "event_state": event_state,
                "previous_digest": previous_digest,
                "payload": dict(payload),
                "created_at": created_at,
            }
        )
        try:
            connection.execute(
                "INSERT INTO authority_audit"
                " (event_id, event_type, event_state, previous_digest, event_digest,"
                " encrypted_payload, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    event_id,
                    event_type,
                    event_state,
                    previous_digest,
                    event_digest,
                    self._encrypt(dict(payload)),
                    created_at,
                ),
            )
        except sqlite3.Error as exc:
            raise AuditUnavailable("authoritative audit append failed") from exc
        return event_digest

    def _encode_lease_token(self, lease: InvocationLease) -> str:
        payload = canonical_json({"lease_id": lease.lease_id, "digest": lease.digest})
        signature = hmac.new(self._mac_key, payload, hashlib.sha256).digest()
        encoded_payload = base64.urlsafe_b64encode(payload).decode("ascii")
        encoded_signature = base64.urlsafe_b64encode(signature).decode("ascii")
        return f"{encoded_payload}.{encoded_signature}"

    def _decode_lease_token(self, token: str) -> tuple[str, str]:
        try:
            encoded_payload, encoded_signature = token.split(".", 1)
            payload = base64.urlsafe_b64decode(encoded_payload.encode("ascii"))
            signature = base64.urlsafe_b64decode(encoded_signature.encode("ascii"))
            if not hmac.compare_digest(
                signature, hmac.new(self._mac_key, payload, hashlib.sha256).digest()
            ):
                raise AuthorityDenied("InvocationLease token is invalid")
            value = json.loads(payload.decode("utf-8"))
            return str(value["lease_id"]), str(value["digest"])
        except AuthorityDenied:
            raise
        except (ValueError, KeyError, UnicodeError, json.JSONDecodeError) as exc:
            raise AuthorityDenied("InvocationLease token is malformed") from exc

    def dispatch_lease(
        self,
        token: str,
        *,
        target_domain_id: str,
        target_boot_epoch: int,
        request_digest: str,
    ) -> InvocationLease:
        """Atomically consume a Lease immediately before the Provider effect."""

        self.expire_leases()
        lease_id, expected_digest = self._decode_lease_token(token)
        try:
            with self._lock, self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                row = connection.execute(
                    "SELECT encrypted_payload, lease_digest, state FROM invocation_leases"
                    " WHERE lease_id=?",
                    (lease_id,),
                ).fetchone()
                if row is None:
                    raise AuthorityDenied("InvocationLease is unknown")
                if row["state"] != LeaseState.ISSUED.value:
                    raise AuthorityDenied("InvocationLease was already used or revoked")
                value = self._decrypt(row["encrypted_payload"])
                lease = InvocationLease.from_dict(value)
                if not hmac.compare_digest(expected_digest, str(row["lease_digest"])):
                    raise AuthorityDenied("InvocationLease digest does not match")
                if lease.digest != expected_digest:
                    raise AuthorityDenied("InvocationLease payload was altered")
                if self._clock() >= lease.expires_at:
                    raise AuthorityDenied("InvocationLease expired")
                epoch_row = connection.execute(
                    "SELECT value FROM authority_meta WHERE key='security_epoch'"
                ).fetchone()
                if epoch_row is None or int(epoch_row["value"]) != lease.security_epoch:
                    raise AuthorityDenied("InvocationLease has a stale SecurityEpoch")
                if (
                    lease.target_domain_id != target_domain_id
                    or lease.target_boot_epoch != target_boot_epoch
                    or lease.request_digest != request_digest
                ):
                    raise AuthorityDenied("InvocationLease context does not match")
                for target_kind, target_id in (
                    ("function_principal", lease.caller.principal_id),
                    ("function_principal", lease.target.principal_id),
                    ("execution_domain", lease.caller_domain_id),
                    ("execution_domain", lease.target_domain_id),
                    ("profile", lease.profile_id),
                    ("activation", lease.activation_id),
                    ("grant", lease.grant_id),
                    ("provider_authority", lease.provider_authority_id),
                    ("pack_artifact", lease.caller.parent_artifact_digest),
                    ("pack_artifact", lease.target.parent_artifact_digest),
                    ("publisher", lease.caller_publisher_lineage),
                    ("publisher", lease.target_publisher_lineage),
                    ("host_extension", lease.host_extension_id),
                ):
                    if self._is_revoked(connection, target_kind, target_id):
                        raise AuthorityDenied("InvocationLease context was revoked")
                target_domain = self.get_domain(lease.target_domain_id)
                if (
                    target_domain is None
                    or target_domain.boot_epoch != lease.target_boot_epoch
                    or target_domain.state.value != "active"
                    or target_domain.security_epoch != lease.security_epoch
                    or lease.target.principal_id not in target_domain.principal_ids
                ):
                    raise AuthorityDenied("target execution domain is stale")
                updated = connection.execute(
                    "UPDATE invocation_leases SET state=? WHERE lease_id=? AND state=?",
                    (
                        LeaseState.DISPATCHED.value,
                        lease_id,
                        LeaseState.ISSUED.value,
                    ),
                )
                if updated.rowcount != 1:
                    raise AuthorityDenied("InvocationLease lost a dispatch race")
                self._append_audit(
                    connection,
                    event_id="dispatch-" + lease_id,
                    event_type="host_effect",
                    event_state="dispatched",
                    payload={
                        "lease_id": lease_id,
                        "reservation_id": lease.audit_reservation_id,
                        "request_digest": lease.request_digest,
                    },
                )
                connection.commit()
                return lease
        except AuthorityDenied:
            raise
        except AuditUnavailable:
            raise
        except sqlite3.Error as exc:
            raise AuthorityStoreError("InvocationLease dispatch failed") from exc

    def expire_leases(self) -> list[str]:
        """Expire unused Leases and release their Grant-use reservations."""

        expired: list[str] = []
        now = self._clock()
        try:
            with self._lock, self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                rows = connection.execute(
                    "SELECT lease_id, grant_id, audit_reservation_id"
                    " FROM invocation_leases WHERE state=? AND expires_at <= ?",
                    (LeaseState.ISSUED.value, now),
                ).fetchall()
                for row in rows:
                    lease_id = str(row["lease_id"])
                    connection.execute(
                        "UPDATE invocation_leases SET state=? WHERE lease_id=? AND state=?",
                        (
                            LeaseState.EXPIRED.value,
                            lease_id,
                            LeaseState.ISSUED.value,
                        ),
                    )
                    connection.execute(
                        "UPDATE grant_usage SET reserved_uses=reserved_uses-1"
                        " WHERE grant_id=? AND reserved_uses > 0",
                        (row["grant_id"],),
                    )
                    self._append_audit(
                        connection,
                        event_id=f"expire-{lease_id}",
                        event_type="host_effect",
                        event_state=LeaseState.EXPIRED.value,
                        payload={
                            "lease_id": lease_id,
                            "reservation_id": row["audit_reservation_id"],
                        },
                    )
                    expired.append(lease_id)
                connection.commit()
        except AuditUnavailable:
            raise
        except sqlite3.Error as exc:
            raise AuthorityStoreError("InvocationLease expiry failed") from exc
        return expired

    def get_lease(self, lease_id: str) -> tuple[InvocationLease, LeaseState] | None:
        """Load and authenticate a Lease for Host-side delegation checks."""

        try:
            with self._lock, self._connect() as connection:
                row = connection.execute(
                    "SELECT encrypted_payload, lease_digest, state"
                    " FROM invocation_leases WHERE lease_id=?",
                    (lease_id,),
                ).fetchone()
        except sqlite3.Error as exc:
            raise AuthorityStoreError("InvocationLease read failed") from exc
        if row is None:
            return None
        lease = InvocationLease.from_dict(self._decrypt(row["encrypted_payload"]))
        if not hmac.compare_digest(lease.digest, str(row["lease_digest"])):
            raise AuthorityStoreError("InvocationLease digest mismatch")
        return lease, LeaseState(str(row["state"]))

    def finish_lease(
        self,
        lease_id: str,
        *,
        state: LeaseState,
        outcome_digest: str,
    ) -> None:
        """Durably finish a dispatched effect and its Grant reservation."""

        if state not in {LeaseState.COMMITTED, LeaseState.FAILED, LeaseState.AMBIGUOUS}:
            raise ValueError("invalid final Lease state")
        try:
            with self._lock, self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                row = connection.execute(
                    "SELECT grant_id, audit_reservation_id, state"
                    " FROM invocation_leases WHERE lease_id=?",
                    (lease_id,),
                ).fetchone()
                if row is None or row["state"] != LeaseState.DISPATCHED.value:
                    raise AuthorityDenied("InvocationLease is not dispatched")
                updated = connection.execute(
                    "UPDATE invocation_leases SET state=?, outcome_digest=?"
                    " WHERE lease_id=? AND state=?",
                    (state.value, outcome_digest, lease_id, LeaseState.DISPATCHED.value),
                )
                if updated.rowcount != 1:
                    raise AuthorityDenied("InvocationLease finish lost a race")
                if state in {LeaseState.COMMITTED, LeaseState.AMBIGUOUS}:
                    connection.execute(
                        "UPDATE grant_usage SET reserved_uses=reserved_uses-1,"
                        " committed_uses=committed_uses+1 WHERE grant_id=?"
                        " AND reserved_uses > 0",
                        (row["grant_id"],),
                    )
                else:
                    connection.execute(
                        "UPDATE grant_usage SET reserved_uses=reserved_uses-1"
                        " WHERE grant_id=? AND reserved_uses > 0",
                        (row["grant_id"],),
                    )
                self._append_audit(
                    connection,
                    event_id=f"finish-{lease_id}",
                    event_type="host_effect",
                    event_state=state.value,
                    payload={
                        "lease_id": lease_id,
                        "reservation_id": row["audit_reservation_id"],
                        "outcome_digest": outcome_digest,
                    },
                )
                connection.commit()
        except AuthorityDenied:
            raise
        except AuditUnavailable:
            raise
        except sqlite3.Error as exc:
            raise AuthorityStoreError("InvocationLease finalization failed") from exc

    def recover_incomplete_effects(self) -> list[str]:
        """Mark crash-surviving dispatched effects ambiguous, never retrying them."""

        recovered: list[str] = []
        try:
            with self._lock, self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                rows = connection.execute(
                    "SELECT lease_id, grant_id, audit_reservation_id"
                    " FROM invocation_leases WHERE state=?",
                    (LeaseState.DISPATCHED.value,),
                ).fetchall()
                for row in rows:
                    lease_id = str(row["lease_id"])
                    outcome_digest = authority_digest(
                        {"status": "ambiguous_after_crash", "lease_id": lease_id}
                    )
                    connection.execute(
                        "UPDATE invocation_leases SET state=?, outcome_digest=?"
                        " WHERE lease_id=? AND state=?",
                        (
                            LeaseState.AMBIGUOUS.value,
                            outcome_digest,
                            lease_id,
                            LeaseState.DISPATCHED.value,
                        ),
                    )
                    connection.execute(
                        "UPDATE grant_usage SET reserved_uses=reserved_uses-1,"
                        " committed_uses=committed_uses+1 WHERE grant_id=?"
                        " AND reserved_uses > 0",
                        (row["grant_id"],),
                    )
                    self._append_audit(
                        connection,
                        event_id=f"recover-{lease_id}",
                        event_type="host_effect",
                        event_state=LeaseState.AMBIGUOUS.value,
                        payload={
                            "lease_id": lease_id,
                            "reservation_id": row["audit_reservation_id"],
                            "outcome_digest": outcome_digest,
                        },
                    )
                    recovered.append(lease_id)
                connection.commit()
        except AuditUnavailable:
            raise
        except sqlite3.Error as exc:
            raise AuthorityStoreError("effect recovery failed") from exc
        return recovered

    def audit_events(self) -> list[dict[str, Any]]:
        """Read and verify the complete authoritative audit hash chain."""

        try:
            with self._lock, self._connect() as connection:
                rows = connection.execute(
                    "SELECT * FROM authority_audit ORDER BY sequence"
                ).fetchall()
        except sqlite3.Error as exc:
            raise AuthorityStoreError("audit read failed") from exc
        previous_digest = "sha256:" + "0" * 64
        output: list[dict[str, Any]] = []
        for row in rows:
            payload = self._decrypt(row["encrypted_payload"])
            expected = authority_digest(
                {
                    "event_id": row["event_id"],
                    "event_type": row["event_type"],
                    "event_state": row["event_state"],
                    "previous_digest": previous_digest,
                    "payload": payload,
                    "created_at": row["created_at"],
                }
            )
            if row["previous_digest"] != previous_digest or not hmac.compare_digest(
                str(row["event_digest"]), expected
            ):
                raise AuthorityStoreError("authoritative audit chain is invalid")
            output.append(
                {
                    "sequence": row["sequence"],
                    "event_id": row["event_id"],
                    "event_type": row["event_type"],
                    "event_state": row["event_state"],
                    "previous_digest": row["previous_digest"],
                    "event_digest": row["event_digest"],
                    "payload": payload,
                    "created_at": row["created_at"],
                }
            )
            previous_digest = str(row["event_digest"])
        return output

    def grant_usage(self, grant_id: str) -> tuple[int, int]:
        """Return ``(reserved, committed)`` use counters for tests/operations."""

        with self._lock, self._connect() as connection:
            row = connection.execute(
                "SELECT reserved_uses, committed_uses FROM grant_usage WHERE grant_id=?",
                (grant_id,),
            ).fetchone()
        if row is None:
            raise AuthorityStoreError("Grant usage is unavailable")
        return int(row["reserved_uses"]), int(row["committed_uses"])
