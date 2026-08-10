"""Durable Profile ceremony and frontend mutation reconciliation state."""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Mapping

from tobkiri_protocol.canonical import canonical_digest
from tobkiri_protocol.errors import CanonicalizationError


class ControlReconciliationError(RuntimeError):
    """Raised when durable control state is missing, stale, or inconsistent."""


class ControlReconciliationStore:
    """SQLite-backed exact-once state for Host control mutations."""

    def __init__(self, path: Path, *, instance_id: str = "") -> None:
        self.path = Path(path)
        self.instance_id = instance_id
        self._initialization_lock = threading.RLock()
        self._initialized = False
        self._operation_recovery_complete = False

    def _prepare_path(self) -> None:
        if self.path.is_symlink():
            raise ControlReconciliationError("control journal path cannot be a symlink")
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if self.path.parent.is_symlink():
            raise ControlReconciliationError("control journal parent cannot be a symlink")

    def _open_connection(self) -> sqlite3.Connection:
        connection: sqlite3.Connection | None = None
        try:
            connection = sqlite3.connect(
                str(self.path),
                timeout=30.0,
                isolation_level=None,
            )
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA synchronous=FULL")
            connection.execute("PRAGMA trusted_schema=OFF")
            connection.execute("PRAGMA foreign_keys=ON")
            return connection
        except (OSError, sqlite3.Error) as error:
            if connection is not None:
                connection.close()
            raise ControlReconciliationError("control journal is unavailable") from error

    def _connect(self) -> sqlite3.Connection:
        self._initialize()
        return self._open_connection()

    def _connect_existing(self) -> sqlite3.Connection:
        """Open existing durable state without creating files or sidecars."""

        if self.path.is_symlink() or self.path.parent.is_symlink():
            raise ControlReconciliationError("control journal path is unsafe")
        if not self.path.is_file():
            raise ControlReconciliationError("control journal is unavailable")
        connection: sqlite3.Connection | None = None
        try:
            uri = f"{self.path.absolute().as_uri()}?mode=ro"
            connection = sqlite3.connect(uri, timeout=30.0, uri=True)
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA query_only=ON")
            connection.execute("PRAGMA trusted_schema=OFF")
            connection.execute("PRAGMA foreign_keys=ON")
            return connection
        except (OSError, sqlite3.Error) as error:
            if connection is not None:
                connection.close()
            raise ControlReconciliationError("control journal is unavailable") from error

    def _initialize(self) -> None:
        if self._initialized:
            return
        with self._initialization_lock:
            if self._initialized:
                return
            self._prepare_path()
            try:
                with self._open_connection() as connection:
                    connection.execute("BEGIN IMMEDIATE")
                    connection.executescript(
                        """
                CREATE TABLE IF NOT EXISTS profile_ceremonies (
                    candidate_id TEXT PRIMARY KEY,
                    candidate_digest TEXT NOT NULL UNIQUE,
                    session_digest TEXT NOT NULL,
                    state TEXT NOT NULL,
                    expected_profile_revision TEXT NOT NULL,
                    expected_plan_digest TEXT NOT NULL,
                    profile_definition_digest TEXT NOT NULL,
                    profile_catalog_digest TEXT NOT NULL,
                    bundle_lock_digest TEXT NOT NULL,
                    authority_snapshot_digest TEXT NOT NULL,
                    security_epoch INTEGER NOT NULL,
                    review_json TEXT NOT NULL,
                    expires_at REAL NOT NULL,
                    approval_id TEXT UNIQUE,
                    approval_digest TEXT,
                    approval_decided_at REAL,
                    authority_record_json TEXT,
                    activation_json TEXT,
                    updated_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS profile_ceremony_state_idx
                    ON profile_ceremonies(state, expires_at);
                CREATE TABLE IF NOT EXISTS control_operations (
                    request_id TEXT PRIMARY KEY,
                    session_digest TEXT NOT NULL,
                    operation_id TEXT NOT NULL,
                    contract_id TEXT NOT NULL,
                    request_digest TEXT NOT NULL,
                    state TEXT NOT NULL,
                    owner_instance TEXT NOT NULL,
                    result_json TEXT,
                    result_digest TEXT,
                    record_refs_json TEXT NOT NULL,
                    safe_error_code TEXT,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS control_operation_state_idx
                    ON control_operations(state, updated_at);
                """
                    )
                    connection.commit()
                if os.name != "nt":
                    os.chmod(self.path, 0o600)
            except (OSError, sqlite3.Error) as error:
                raise ControlReconciliationError("control journal initialization failed") from error
            self._initialized = True

    def prepare_for_operation(self) -> None:
        """Initialize and recover once at an authorized mutation boundary."""

        with self._initialization_lock:
            if self._operation_recovery_complete:
                return
            self._initialize()
            self.recover_abandoned_operations()
            self._operation_recovery_complete = True

    @staticmethod
    def session_digest(session_id: str) -> str:
        """Return an opaque durable binding for one authenticated session."""

        if not session_id:
            raise ControlReconciliationError("session binding is missing")
        return canonical_digest({"session_id": session_id})

    def save_candidate(
        self,
        *,
        candidate_id: str,
        candidate_digest: str,
        session_id: str,
        review: Mapping[str, Any],
        expires_at: float,
    ) -> Mapping[str, Any]:
        """Persist a resolved candidate or return its exact prior record."""

        plan = _mapping(review.get("resolved_plan"), "resolved plan")
        profile = _mapping(review.get("profile"), "Profile")
        binding = _mapping(review.get("catalog_binding"), "catalog binding")
        predecessor = _mapping(review.get("predecessor"), "predecessor")
        now = time.time()
        values = (
            candidate_id,
            candidate_digest,
            self.session_digest(session_id),
            "resolved",
            _required(predecessor.get("profile_revision"), "Profile revision"),
            _required(predecessor.get("plan_digest"), "predecessor plan digest"),
            _required(binding.get("profile_definition_digest"), "definition digest"),
            _required(binding.get("profile_catalog_digest"), "catalog digest"),
            _required(binding.get("bundle_lock_digest"), "bundle lock digest"),
            _required(profile.get("profile_authority_snapshot_digest"), "Authority digest"),
            _integer(plan.get("security_epoch"), "SecurityEpoch"),
            _json(review),
            float(expires_at),
            now,
        )
        try:
            with self._connect() as connection:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute(
                    """
                    INSERT INTO profile_ceremonies(
                        candidate_id, candidate_digest, session_digest, state,
                        expected_profile_revision, expected_plan_digest,
                        profile_definition_digest, profile_catalog_digest,
                        bundle_lock_digest, authority_snapshot_digest,
                        security_epoch, review_json, expires_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    values,
                )
                connection.commit()
        except sqlite3.IntegrityError:
            existing = self.candidate_by_digest(candidate_digest, session_id=session_id)
            if existing is None:
                raise ControlReconciliationError(
                    "candidate digest is already bound to another ceremony"
                )
            return existing
        return self.require_candidate(candidate_id, candidate_digest, session_id=session_id)

    def require_candidate(
        self,
        candidate_id: str,
        candidate_digest: str,
        *,
        session_id: str,
        allowed_states: tuple[str, ...] = (
            "resolved",
            "reviewed",
            "approval_prepared",
            "approved",
            "activated",
        ),
    ) -> Mapping[str, Any]:
        """Load one exact session-bound ceremony record."""

        with self._connect_existing() as connection:
            row = connection.execute(
                "SELECT * FROM profile_ceremonies WHERE candidate_id = ?",
                (candidate_id,),
            ).fetchone()
        record = _ceremony_record(row)
        if record is None:
            raise ControlReconciliationError("Profile ceremony candidate is unknown")
        if record["candidate_digest"] != candidate_digest or record[
            "session_digest"
        ] != self.session_digest(session_id):
            raise ControlReconciliationError("Profile ceremony binding does not match")
        if record["state"] not in allowed_states:
            raise ControlReconciliationError("Profile ceremony state is invalid")
        return record

    def candidate_by_digest(
        self, candidate_digest: str, *, session_id: str
    ) -> Mapping[str, Any] | None:
        """Return the candidate uniquely bound to a digest and session."""

        with self._connect_existing() as connection:
            row = connection.execute(
                "SELECT * FROM profile_ceremonies WHERE candidate_digest = ?",
                (candidate_digest,),
            ).fetchone()
        record = _ceremony_record(row)
        if record is None:
            return None
        if record["session_digest"] != self.session_digest(session_id):
            raise ControlReconciliationError("candidate digest belongs to another session")
        return record

    def transition_reviewed(
        self, candidate_id: str, candidate_digest: str, *, session_id: str
    ) -> Mapping[str, Any]:
        """Atomically acknowledge one resolved candidate."""

        return self._transition(
            candidate_id,
            candidate_digest,
            session_id=session_id,
            from_states=("resolved", "reviewed"),
            to_state="reviewed",
        )

    def prepare_approval(
        self, candidate_id: str, candidate_digest: str, *, session_id: str
    ) -> Mapping[str, Any]:
        """Persist the deterministic Authority record identity before commit."""

        session_digest = self.session_digest(session_id)
        approval_id = (
            "approval.profile-change."
            + canonical_digest(
                {
                    "candidate_digest": candidate_digest,
                    "session_digest": session_digest,
                }
            ).removeprefix("sha256:")[:48]
        )
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM profile_ceremonies WHERE candidate_id = ?",
                (candidate_id,),
            ).fetchone()
            record = self._check_candidate(_ceremony_record(row), candidate_digest, session_digest)
            if record["state"] in {"approved", "activated", "approval_prepared"}:
                connection.commit()
                return record
            if record["state"] != "reviewed":
                raise ControlReconciliationError("candidate was not reviewed")
            decided_at = time.time()
            connection.execute(
                """
                UPDATE profile_ceremonies
                SET state='approval_prepared', approval_id=?,
                    approval_decided_at=?, updated_at=?
                WHERE candidate_id=? AND state='reviewed'
                """,
                (approval_id, decided_at, decided_at, candidate_id),
            )
            connection.commit()
        return self.require_candidate(
            candidate_id,
            candidate_digest,
            session_id=session_id,
            allowed_states=("approval_prepared",),
        )

    def mark_approved(
        self,
        candidate_id: str,
        candidate_digest: str,
        *,
        session_id: str,
        approval_digest: str,
        authority_record: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        """Persist the exact committed Authority receipt idempotently."""

        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM profile_ceremonies WHERE candidate_id = ?",
                (candidate_id,),
            ).fetchone()
            record = self._check_candidate(
                _ceremony_record(row),
                candidate_digest,
                self.session_digest(session_id),
            )
            if record["state"] in {"approved", "activated"}:
                if record["approval_digest"] != approval_digest or record[
                    "authority_record"
                ] != dict(authority_record):
                    raise ControlReconciliationError("approval receipt changed")
                connection.commit()
                return record
            if record["state"] != "approval_prepared":
                raise ControlReconciliationError("approval was not prepared")
            connection.execute(
                """
                UPDATE profile_ceremonies
                SET state='approved', approval_digest=?, authority_record_json=?,
                    updated_at=?
                WHERE candidate_id=? AND state='approval_prepared'
                """,
                (approval_digest, _json(authority_record), time.time(), candidate_id),
            )
            connection.commit()
        return self.require_candidate(
            candidate_id,
            candidate_digest,
            session_id=session_id,
            allowed_states=("approved",),
        )

    def require_approval(
        self, approval_id: str, approval_digest: str, *, session_id: str
    ) -> Mapping[str, Any]:
        """Load one durable approval without accepting client authority claims."""

        with self._connect_existing() as connection:
            row = connection.execute(
                "SELECT * FROM profile_ceremonies WHERE approval_id = ?",
                (approval_id,),
            ).fetchone()
        record = _ceremony_record(row)
        if record is None or record["state"] not in {"approved", "activated"}:
            raise ControlReconciliationError("Profile approval is unavailable")
        if (
            record["session_digest"] != self.session_digest(session_id)
            or record["approval_digest"] != approval_digest
        ):
            raise ControlReconciliationError("Profile approval binding does not match")
        return record

    def mark_activated(
        self,
        approval_id: str,
        approval_digest: str,
        *,
        session_id: str,
        activation: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        """Commit the activation receipt without deleting referenced history."""

        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM profile_ceremonies WHERE approval_id = ?",
                (approval_id,),
            ).fetchone()
            record = _ceremony_record(row)
            if record is None:
                raise ControlReconciliationError("Profile approval is unavailable")
            if (
                record["session_digest"] != self.session_digest(session_id)
                or record["approval_digest"] != approval_digest
            ):
                raise ControlReconciliationError("Profile approval binding does not match")
            if record["state"] == "activated":
                if record["activation"] != dict(activation):
                    raise ControlReconciliationError("activation receipt changed")
                connection.commit()
                return record
            if record["state"] != "approved":
                raise ControlReconciliationError("Profile approval is not activatable")
            connection.execute(
                """
                UPDATE profile_ceremonies
                SET state='activated', activation_json=?, updated_at=?
                WHERE approval_id=? AND state='approved'
                """,
                (_json(activation), time.time(), approval_id),
            )
            connection.commit()
        return self.require_approval(approval_id, approval_digest, session_id=session_id)

    def begin_operation(
        self,
        *,
        request_id: str,
        session_id: str,
        operation_id: str,
        contract_id: str,
        request_digest: str,
    ) -> tuple[Mapping[str, Any], bool]:
        """Reserve an unsafe frontend request or return its prior outcome."""

        now = time.time()
        session_digest = self.session_digest(session_id)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM control_operations WHERE request_id = ?",
                (request_id,),
            ).fetchone()
            record = _operation_record(row)
            if record is not None:
                self._check_operation(
                    record,
                    session_digest=session_digest,
                    operation_id=operation_id,
                    contract_id=contract_id,
                    request_digest=request_digest,
                )
                connection.commit()
                return self._operation_projection(record), False
            connection.execute(
                """
                INSERT INTO control_operations(
                    request_id, session_digest, operation_id, contract_id,
                    request_digest, state, owner_instance, record_refs_json,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, 'pending', ?, '[]', ?, ?)
                """,
                (
                    request_id,
                    session_digest,
                    operation_id,
                    contract_id,
                    request_digest,
                    self.instance_id,
                    now,
                    now,
                ),
            )
            connection.commit()
        return self.operation_status(request_id, session_id=session_id), True

    def finish_operation(
        self,
        request_id: str,
        *,
        session_id: str,
        state: str,
        result: Mapping[str, Any] | None,
        record_refs: list[Mapping[str, str]] | None = None,
        safe_error_code: str | None = None,
    ) -> Mapping[str, Any]:
        """Publish a terminal operation result exactly once."""

        if state not in {"succeeded", "failed", "indeterminate"}:
            raise ControlReconciliationError("operation terminal state is invalid")
        result_value = dict(result) if result is not None else None
        result_digest = canonical_digest(result_value) if result_value is not None else None
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM control_operations WHERE request_id = ?",
                (request_id,),
            ).fetchone()
            record = _operation_record(row)
            if record is None or record["session_digest"] != self.session_digest(session_id):
                raise ControlReconciliationError("operation binding does not match")
            if record["state"] != "pending":
                if (
                    record["state"] != state
                    or record["result_digest"] != result_digest
                    or record["result"] != result_value
                ):
                    raise ControlReconciliationError("operation outcome is immutable")
                connection.commit()
                return self._operation_projection(record)
            connection.execute(
                """
                UPDATE control_operations
                SET state=?, result_json=?, result_digest=?, record_refs_json=?,
                    safe_error_code=?, updated_at=?
                WHERE request_id=? AND state='pending'
                """,
                (
                    state,
                    _json(result_value) if result_value is not None else None,
                    result_digest,
                    _json(record_refs or []),
                    safe_error_code,
                    time.time(),
                    request_id,
                ),
            )
            connection.commit()
        return self.operation_status(request_id, session_id=session_id)

    def operation_status(self, request_id: str, *, session_id: str) -> Mapping[str, Any]:
        """Read one durable operation outcome for its originating session."""

        with self._connect_existing() as connection:
            row = connection.execute(
                "SELECT * FROM control_operations WHERE request_id = ?",
                (request_id,),
            ).fetchone()
        record = _operation_record(row)
        if record is None:
            raise ControlReconciliationError("operation request is unknown")
        if record["session_digest"] != self.session_digest(session_id):
            raise ControlReconciliationError("operation request belongs to another session")
        return self._operation_projection(record)

    def recover_abandoned_operations(self) -> int:
        """Mark another process's unresolved operations indeterminate, never delete them."""

        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            cursor = connection.execute(
                """
                UPDATE control_operations
                SET state='indeterminate', safe_error_code='PROCESS_RESTART',
                    updated_at=?
                WHERE state='pending' AND owner_instance != ?
                """,
                (time.time(), self.instance_id),
            )
            connection.commit()
            return int(cursor.rowcount)

    def _transition(
        self,
        candidate_id: str,
        candidate_digest: str,
        *,
        session_id: str,
        from_states: tuple[str, ...],
        to_state: str,
    ) -> Mapping[str, Any]:
        session_digest = self.session_digest(session_id)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM profile_ceremonies WHERE candidate_id = ?",
                (candidate_id,),
            ).fetchone()
            record = self._check_candidate(_ceremony_record(row), candidate_digest, session_digest)
            if record["state"] not in from_states:
                raise ControlReconciliationError("Profile ceremony transition is invalid")
            if record["state"] != to_state:
                connection.execute(
                    "UPDATE profile_ceremonies SET state=?, updated_at=? WHERE candidate_id=?",
                    (to_state, time.time(), candidate_id),
                )
            connection.commit()
        return self.require_candidate(
            candidate_id,
            candidate_digest,
            session_id=session_id,
            allowed_states=(to_state,),
        )

    @staticmethod
    def _check_candidate(
        record: Mapping[str, Any] | None,
        candidate_digest: str,
        session_digest: str,
    ) -> Mapping[str, Any]:
        if record is None:
            raise ControlReconciliationError("Profile ceremony candidate is unknown")
        if (
            record["candidate_digest"] != candidate_digest
            or record["session_digest"] != session_digest
        ):
            raise ControlReconciliationError("Profile ceremony binding does not match")
        return record

    @staticmethod
    def _check_operation(
        record: Mapping[str, Any],
        *,
        session_digest: str,
        operation_id: str,
        contract_id: str,
        request_digest: str,
    ) -> None:
        expected = (session_digest, operation_id, contract_id, request_digest)
        actual = (
            record["session_digest"],
            record["operation_id"],
            record["contract_id"],
            record["request_digest"],
        )
        if actual != expected:
            raise ControlReconciliationError("operation request binding changed")

    @staticmethod
    def _operation_projection(record: Mapping[str, Any]) -> Mapping[str, Any]:
        return {
            "runtime_surface_api_version": "io.tobkiri.launcher.runtime-surface.v4",
            "operation_status_api_version": "io.tobkiri.control-operation-status.v1",
            "request_id": record["request_id"],
            "operation_id": record["operation_id"],
            "contract_id": record["contract_id"],
            "request_digest": record["request_digest"],
            "state": record["state"],
            "result": record["result"],
            "result_digest": record["result_digest"],
            "record_refs": record["record_refs"],
            "safe_error_code": record["safe_error_code"],
            "created_at": record["created_at"],
            "updated_at": record["updated_at"],
        }


def _ceremony_record(row: sqlite3.Row | None) -> Mapping[str, Any] | None:
    if row is None:
        return None
    try:
        review = _mapping(json.loads(str(row["review_json"])), "review")
        authority_record = (
            json.loads(str(row["authority_record_json"]))
            if row["authority_record_json"] is not None
            else None
        )
        activation = (
            json.loads(str(row["activation_json"])) if row["activation_json"] is not None else None
        )
        predecessor = _mapping(review.get("predecessor"), "predecessor")
        binding = _mapping(review.get("catalog_binding"), "catalog binding")
        profile = _mapping(review.get("profile"), "Profile")
        plan = _mapping(review.get("resolved_plan"), "resolved plan")
    except (
        CanonicalizationError,
        ControlReconciliationError,
        json.JSONDecodeError,
        TypeError,
        ValueError,
    ) as error:
        raise ControlReconciliationError("Profile ceremony record is invalid") from error
    expected = (
        str(row["candidate_digest"]),
        str(row["expected_profile_revision"]),
        str(row["expected_plan_digest"]),
        str(row["profile_definition_digest"]),
        str(row["profile_catalog_digest"]),
        str(row["bundle_lock_digest"]),
        str(row["authority_snapshot_digest"]),
        int(row["security_epoch"]),
    )
    actual = (
        _record_digest(review),
        predecessor.get("profile_revision"),
        predecessor.get("plan_digest"),
        binding.get("profile_definition_digest"),
        binding.get("profile_catalog_digest"),
        binding.get("bundle_lock_digest"),
        profile.get("profile_authority_snapshot_digest"),
        plan.get("security_epoch"),
    )
    if actual != expected:
        raise ControlReconciliationError("Profile ceremony record digest changed")
    return {
        **dict(row),
        "review": review,
        "authority_record": authority_record,
        "activation": activation,
    }


def _operation_record(row: sqlite3.Row | None) -> Mapping[str, Any] | None:
    if row is None:
        return None
    try:
        result = json.loads(str(row["result_json"])) if row["result_json"] is not None else None
        record_refs = json.loads(str(row["record_refs_json"]))
    except (CanonicalizationError, json.JSONDecodeError, TypeError, ValueError) as error:
        raise ControlReconciliationError("operation record is invalid") from error
    if (
        row["state"] not in {"pending", "succeeded", "failed", "indeterminate"}
        or not isinstance(record_refs, list)
        or (result is None) != (row["result_digest"] is None)
        or (result is not None and _record_digest(result) != row["result_digest"])
    ):
        raise ControlReconciliationError("operation record digest changed")
    return {
        **dict(row),
        "result": result,
        "record_refs": record_refs,
    }


def _mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ControlReconciliationError(f"{label} is missing")
    return value


def _required(value: object, label: str) -> str:
    if not isinstance(value, str) or not value:
        raise ControlReconciliationError(f"{label} is missing")
    return value


def _integer(value: object, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ControlReconciliationError(f"{label} is invalid")
    return value


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _record_digest(value: object) -> str:
    try:
        return canonical_digest(value)
    except CanonicalizationError as error:
        raise ControlReconciliationError("durable control record is not canonical") from error


__all__ = ["ControlReconciliationError", "ControlReconciliationStore"]
