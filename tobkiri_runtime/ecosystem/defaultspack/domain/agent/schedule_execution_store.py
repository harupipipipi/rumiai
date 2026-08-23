"""Durable, pack-local storage for scheduled agent executions.

The scheduler deliberately owns the decision *when* to run a schedule.  This
module owns the small durable state machine around a run.  Keeping that
boundary here makes a trigger safe to retry, safe to resume after approval,
and safe to recover after a process restart without importing host or core
runtime state.

Only the Python standard library is used.  Every mutating operation is a
short ``BEGIN IMMEDIATE`` SQLite transaction and the database is opened in
WAL mode.  The same rules therefore hold for threads in one process and for
two scheduler processes sharing the pack-local database.
"""

from __future__ import annotations

import hashlib
import builtins
import json
import os
import re
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping


QUEUED = "queued"
RUNNING = "running"
WAITING_APPROVAL = "waiting_approval"
COMPLETED = "completed"
FAILED = "failed"
CANCELLED = "cancelled"
TIMED_OUT = "timed_out"

SCHEDULE_EXECUTION_STATES = frozenset(
    {
        QUEUED,
        RUNNING,
        WAITING_APPROVAL,
        COMPLETED,
        FAILED,
        CANCELLED,
        TIMED_OUT,
    }
)
ACTIVE_SCHEDULE_EXECUTION_STATES = frozenset(
    {QUEUED, RUNNING, WAITING_APPROVAL}
)
TERMINAL_SCHEDULE_EXECUTION_STATES = frozenset(
    {COMPLETED, FAILED, CANCELLED, TIMED_OUT}
)

# This is the one source of truth for lifecycle legality.  In particular,
# terminal states have no outgoing edges and approval resumes the original
# record rather than creating another record.
LEGAL_SCHEDULE_EXECUTION_TRANSITIONS: dict[str, frozenset[str]] = {
    QUEUED: frozenset({RUNNING, WAITING_APPROVAL, FAILED, CANCELLED, TIMED_OUT}),
    RUNNING: frozenset(
        {WAITING_APPROVAL, COMPLETED, FAILED, CANCELLED, TIMED_OUT}
    ),
    WAITING_APPROVAL: frozenset({RUNNING, FAILED, CANCELLED, TIMED_OUT}),
    COMPLETED: frozenset(),
    FAILED: frozenset(),
    CANCELLED: frozenset(),
    TIMED_OUT: frozenset(),
}

_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$")
_FINGERPRINT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,255}$")
_MISSING = object()

_PATH_LOCK_GUARD = threading.Lock()
_PATH_LOCKS: dict[str, threading.RLock] = {}


def _path_lock(path: Path) -> threading.RLock:
    """Return the process-wide initialization/transaction lock for ``path``."""

    key = str(path)
    with _PATH_LOCK_GUARD:
        return _PATH_LOCKS.setdefault(key, threading.RLock())


def default_schedule_execution_db_path() -> Path:
    """Return the default database path owned by defaultspack.

    Environment overrides are intentionally pack-scoped.  There is no
    fallback to a Core or host store: a standalone defaultspack checkout can
    create and use this database with only the Python standard library.
    """

    for variable in (
        "RUMI_DEFAULTSPACK_SCHEDULE_EXECUTION_DB_PATH",
        "RUMI_DEFAULTSPACK_AGENT_SCHEDULE_EXECUTION_DB_PATH",
    ):
        override = os.environ.get(variable, "").strip()
        if override:
            return Path(override).expanduser()

    schedules_dir = os.environ.get(
        "RUMI_DEFAULTSPACK_AGENT_SCHEDULES_DIR", ""
    ).strip()
    if schedules_dir:
        return Path(schedules_dir).expanduser() / "schedule_executions.sqlite3"

    runtime_dir = os.environ.get("RUMI_DEFAULTSPACK_AGENT_RUNTIME_DIR", "").strip()
    if runtime_dir:
        return Path(runtime_dir).expanduser() / "schedule_executions.sqlite3"

    user_data = os.environ.get("RUMI_USER_DATA", "").strip()
    if user_data:
        return (
            Path(user_data).expanduser()
            / "defaultspack"
            / "shared"
            / "schedules"
            / "schedule_executions.sqlite3"
        )

    pack_root = Path(__file__).resolve().parents[2]
    return pack_root / "user_data" / "shared" / "schedules" / "schedule_executions.sqlite3"


def _validate_identifier(value: Any, field: str) -> str:
    """Validate a schedule/execution/idempotency identifier."""

    if not isinstance(value, str):
        raise ValueError(f"{field} must be a string")
    cleaned = value.strip()
    if not cleaned or not _ID_RE.fullmatch(cleaned):
        raise ValueError(
            f"{field} must be 1-256 characters using letters, numbers, "
            ". _ : or -"
        )
    return cleaned


def _validate_fingerprint(value: Any) -> str:
    """Validate a caller-supplied input fingerprint."""

    if not isinstance(value, str):
        raise ValueError("input_fingerprint must be a string")
    cleaned = value.strip()
    if not cleaned or not _FINGERPRINT_RE.fullmatch(cleaned):
        raise ValueError(
            "input_fingerprint must be 1-256 characters using letters, "
            "numbers, . _ : or -"
        )
    return cleaned


def _validate_revision(value: Any) -> int:
    """Validate a non-negative schedule revision."""

    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError("expected_revision must be a non-negative integer")
    return value


def _json_text(value: Any, field: str) -> str:
    """Encode a JSON value deterministically, rejecting unsafe values."""

    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be JSON serializable") from exc


def _json_value(value: str | None, fallback: Any = None) -> Any:
    """Decode a stored JSON value without allowing malformed data to escape."""

    if value is None:
        return fallback
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return fallback


def _fingerprint_for_input(value: Any) -> str:
    """Return a stable SHA-256 fingerprint for a JSON input value."""

    encoded = _json_text(value, "input_data").encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _timestamp(value: Any = None) -> str:
    """Normalize a timestamp value to an explicit UTC-ish string."""

    if value is None:
        return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    if isinstance(value, datetime):
        current = (
            value
            if value.tzinfo is not None
            else value.replace(tzinfo=timezone.utc)
        )
        return current.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return datetime.fromtimestamp(value, tz=timezone.utc).isoformat().replace(
            "+00:00", "Z"
        )
    if isinstance(value, str):
        cleaned = value.strip()
        if cleaned:
            return cleaned
    raise ValueError("timestamp must be a non-empty string, datetime, or number")


def _error_text(value: Any) -> str | None:
    """Normalize an error payload for durable, readable storage."""

    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, (dict, list, tuple)):
        return _json_text(value, "error")
    return str(value)


class ScheduleExecutionError(ValueError):
    """Base class for caller-visible schedule execution errors."""


class ScheduleExecutionNotFoundError(LookupError):
    """Raised when a requested execution does not exist."""


class ScheduleExecutionConflictError(ScheduleExecutionError):
    """Raised when a reservation conflicts with a durable execution."""


class ScheduleExecutionIdempotencyConflict(ScheduleExecutionConflictError):
    """A key was reused with a different revision or input fingerprint."""


class ScheduleExecutionAlreadyActive(ScheduleExecutionConflictError):
    """A different active execution already owns the schedule."""


class ScheduleExecutionTransitionError(ScheduleExecutionError):
    """Raised when a requested lifecycle transition is not legal."""


# More explicit aliases make the small module pleasant to use from adapters
# while retaining short names for callers that prefer them.
DuplicateScheduleExecutionError = ScheduleExecutionIdempotencyConflict
ActiveScheduleExecutionError = ScheduleExecutionAlreadyActive
InvalidScheduleExecutionTransition = ScheduleExecutionTransitionError


class ScheduleExecutionStore:
    """Thread-safe SQLite WAL ledger for scheduled agent executions."""

    def __init__(
        self,
        db_path: str | Path | None = None,
        *,
        path: str | Path | None = None,
        clock: Callable[[], Any] | None = None,
    ) -> None:
        if db_path is not None and path is not None:
            raise ValueError("provide either db_path or path, not both")
        selected = db_path if db_path is not None else path
        target = (
            Path(selected).expanduser()
            if selected is not None
            else default_schedule_execution_db_path()
        )
        if "\x00" in str(target):
            raise ValueError("database path must not contain NUL")
        target = target.absolute()
        if target.exists() and target.is_dir():
            raise ValueError("database path must name a file, not a directory")
        if target.parent.exists() and not target.parent.is_dir():
            raise ValueError("database path parent must be a directory")
        self.db_path = target
        self.path = target
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._lock = _path_lock(target)
        self._ensure_schema()

    def _now(self, value: Any = None) -> str:
        """Return a normalized explicit timestamp from the configured clock."""

        return _timestamp(self._clock() if value is None else value)

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        """Open one short-lived WAL connection for an operation."""

        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(
            str(self.db_path),
            timeout=30.0,
            isolation_level=None,
            check_same_thread=False,
        )
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA busy_timeout=30000")
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA synchronous=NORMAL")
            yield connection
        finally:
            connection.close()

    def _ensure_schema(self) -> None:
        """Create the schema and invariants once per database path."""

        with self._lock, self._connection() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS schedule_execution_ledger(
                  execution_id TEXT PRIMARY KEY,
                  schedule_id TEXT NOT NULL,
                  idempotency_key TEXT NOT NULL,
                  expected_revision INTEGER NOT NULL,
                  input_fingerprint TEXT NOT NULL,
                  input_json TEXT,
                  metadata_json TEXT,
                  status TEXT NOT NULL CHECK (
                    status IN (
                      'queued', 'running', 'waiting_approval', 'completed',
                      'failed', 'cancelled', 'timed_out'
                    )
                  ),
                  result_json TEXT,
                  error TEXT,
                  created_at TEXT NOT NULL,
                  updated_at TEXT NOT NULL,
                  started_at TEXT,
                  completed_at TEXT
                );

                CREATE UNIQUE INDEX IF NOT EXISTS
                  idx_schedule_execution_request
                  ON schedule_execution_ledger(schedule_id, idempotency_key);

                CREATE UNIQUE INDEX IF NOT EXISTS
                  idx_schedule_execution_active_schedule
                  ON schedule_execution_ledger(schedule_id)
                  WHERE status IN ('queued', 'running', 'waiting_approval');

                CREATE INDEX IF NOT EXISTS idx_schedule_execution_status
                  ON schedule_execution_ledger(status, updated_at);
                CREATE INDEX IF NOT EXISTS idx_schedule_execution_schedule
                  ON schedule_execution_ledger(schedule_id, created_at);
                """
            )

    @staticmethod
    def _decode_row(row: sqlite3.Row | Mapping[str, Any] | None) -> dict[str, Any] | None:
        """Convert a SQLite row into the public dictionary representation."""

        if row is None:
            return None
        data = dict(row)
        data["expected_revision"] = int(data["expected_revision"])
        data["input"] = _json_value(data.pop("input_json", None), None)
        data["metadata"] = _json_value(data.pop("metadata_json", None), {})
        data["result"] = _json_value(data.pop("result_json", None), None)
        return data

    @staticmethod
    def _request_tuple(record: Mapping[str, Any]) -> tuple[int, str]:
        """Return the revision/fingerprint identity of a record."""

        return int(record["expected_revision"]), str(record["input_fingerprint"])

    @staticmethod
    def _validate_status(status: Any, field: str = "status") -> str:
        """Validate a lifecycle status."""

        if not isinstance(status, str) or status not in SCHEDULE_EXECUTION_STATES:
            allowed = ", ".join(sorted(SCHEDULE_EXECUTION_STATES))
            raise ValueError(f"{field} must be one of: {allowed}")
        return status

    @staticmethod
    def _check_request_identity(
        record: Mapping[str, Any],
        expected_revision: int,
        input_fingerprint: str,
    ) -> None:
        """Raise if a duplicate key carries a different request identity."""

        if ScheduleExecutionStore._request_tuple(record) != (
            expected_revision,
            input_fingerprint,
        ):
            raise ScheduleExecutionIdempotencyConflict(
                "idempotency_key was already used for a different schedule input"
            )

    @staticmethod
    def _new_execution_id() -> str:
        """Generate an execution identifier compatible with scheduler records."""

        return "sexec_" + str(uuid.uuid4())

    def reserve(
        self,
        schedule_id: str | Mapping[str, Any],
        idempotency_key: str | None = None,
        expected_revision: int | None = None,
        input_fingerprint: Any = None,
        *,
        execution_id: str | None = None,
        input_data: Any = _MISSING,
        input_payload: Any = _MISSING,
        metadata: Mapping[str, Any] | None = None,
        initial_status: str = QUEUED,
        status: str | None = None,
        now: Any = None,
    ) -> dict[str, Any]:
        """Atomically reserve one execution or replay its exact reservation.

        ``schedule_id`` may also be a request mapping containing
        ``schedule_id``, ``idempotency_key``, ``expected_revision`` and
        ``input_fingerprint``.  A repeated exact request returns the original
        row, including when that row is waiting for approval.  A different
        request with the same idempotency key raises
        :class:`ScheduleExecutionIdempotencyConflict`; a different key cannot
        reserve a schedule while any active row exists.
        """

        if isinstance(schedule_id, Mapping):
            request = dict(schedule_id)
            schedule_id = str(
                request.get("schedule_id", request.get("id")) or ""
            )
            idempotency_key = request.get("idempotency_key", idempotency_key)
            expected_revision = request.get("expected_revision", expected_revision)
            if input_fingerprint is None:
                input_fingerprint = request.get("input_fingerprint")
            if input_data is _MISSING:
                input_data = request.get("input_data", request.get("input", _MISSING))
            if input_payload is _MISSING:
                input_payload = request.get("input_payload", _MISSING)
            if metadata is None and isinstance(request.get("metadata"), Mapping):
                metadata = request["metadata"]
            execution_id = execution_id or request.get("execution_id")
            initial_status = str(
                request.get("initial_status", request.get("status", initial_status))
            )

        clean_schedule_id = _validate_identifier(schedule_id, "schedule_id")
        clean_key = _validate_identifier(idempotency_key, "idempotency_key")
        clean_revision = _validate_revision(expected_revision)
        clean_status = self._validate_status(
            status if status is not None else initial_status, "initial_status"
        )
        if clean_status not in ACTIVE_SCHEDULE_EXECUTION_STATES:
            raise ValueError("initial_status must be an active schedule execution state")
        clean_execution_id = (
            _validate_identifier(execution_id, "execution_id")
            if execution_id is not None
            else self._new_execution_id()
        )

        payload = input_data if input_data is not _MISSING else input_payload
        if payload is not _MISSING:
            computed_fingerprint = _fingerprint_for_input(payload)
            if input_fingerprint is None:
                input_fingerprint = computed_fingerprint
            elif isinstance(input_fingerprint, str):
                supplied = _validate_fingerprint(input_fingerprint)
                if supplied != computed_fingerprint:
                    raise ValueError(
                        "input_fingerprint does not match input_data"
                    )
        if input_fingerprint is None:
            raise ValueError("input_fingerprint or input_data is required")
        if not isinstance(input_fingerprint, str):
            input_fingerprint = _fingerprint_for_input(input_fingerprint)
        clean_fingerprint = _validate_fingerprint(input_fingerprint)

        input_json = None if payload is _MISSING else _json_text(payload, "input_data")
        metadata_json = (
            None
            if metadata is None
            else _json_text(dict(metadata), "metadata")
        )
        created_at = self._now(now)

        with self._lock, self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                existing_row = connection.execute(
                    "SELECT * FROM schedule_execution_ledger "
                    "WHERE schedule_id = ? AND idempotency_key = ?",
                    (clean_schedule_id, clean_key),
                ).fetchone()
                if existing_row is not None:
                    existing = self._decode_row(existing_row)
                    assert existing is not None
                    self._check_request_identity(
                        existing, clean_revision, clean_fingerprint
                    )
                    connection.commit()
                    return existing

                active_row = connection.execute(
                    "SELECT * FROM schedule_execution_ledger "
                    "WHERE schedule_id = ? AND status IN (?, ?, ?) "
                    "ORDER BY created_at ASC LIMIT 1",
                    (
                        clean_schedule_id,
                        QUEUED,
                        RUNNING,
                        WAITING_APPROVAL,
                    ),
                ).fetchone()
                if active_row is not None:
                    active = self._decode_row(active_row)
                    assert active is not None
                    raise ScheduleExecutionAlreadyActive(
                        "schedule already has an active execution: "
                        + str(active["execution_id"])
                    )

                connection.execute(
                    """
                    INSERT INTO schedule_execution_ledger(
                      execution_id, schedule_id, idempotency_key,
                      expected_revision, input_fingerprint, input_json,
                      metadata_json, status, result_json, error,
                      created_at, updated_at, started_at, completed_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, ?, ?, NULL, NULL)
                    """,
                    (
                        clean_execution_id,
                        clean_schedule_id,
                        clean_key,
                        clean_revision,
                        clean_fingerprint,
                        input_json,
                        metadata_json,
                        clean_status,
                        created_at,
                        created_at,
                    ),
                )
                if clean_status == RUNNING:
                    connection.execute(
                        "UPDATE schedule_execution_ledger SET started_at = ? "
                        "WHERE execution_id = ?",
                        (created_at, clean_execution_id),
                    )
                created = connection.execute(
                    "SELECT * FROM schedule_execution_ledger WHERE execution_id = ?",
                    (clean_execution_id,),
                ).fetchone()
                connection.commit()
                result = self._decode_row(created)
                assert result is not None
                return result
            except BaseException:
                connection.rollback()
                raise

    def get(self, execution_id: str) -> dict[str, Any] | None:
        """Return one execution, or ``None`` when it is not present."""

        clean_id = _validate_identifier(execution_id, "execution_id")
        with self._lock, self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM schedule_execution_ledger WHERE execution_id = ?",
                (clean_id,),
            ).fetchone()
        return self._decode_row(row)

    def require(self, execution_id: str) -> dict[str, Any]:
        """Return one execution or raise :class:`ScheduleExecutionNotFoundError`."""

        result = self.get(execution_id)
        if result is None:
            raise ScheduleExecutionNotFoundError(
                f"schedule execution not found: {execution_id}"
            )
        return result

    def get_by_idempotency(
        self, schedule_id: str, idempotency_key: str
    ) -> dict[str, Any] | None:
        """Return the execution associated with one schedule request key."""

        clean_schedule_id = _validate_identifier(schedule_id, "schedule_id")
        clean_key = _validate_identifier(idempotency_key, "idempotency_key")
        with self._lock, self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM schedule_execution_ledger "
                "WHERE schedule_id = ? AND idempotency_key = ?",
                (clean_schedule_id, clean_key),
            ).fetchone()
        return self._decode_row(row)

    def list(
        self,
        *,
        schedule_id: str | None = None,
        status: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """List executions newest first, optionally scoped by schedule/status."""

        if schedule_id is not None:
            schedule_id = _validate_identifier(schedule_id, "schedule_id")
        if status is not None:
            status = self._validate_status(status)
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
            raise ValueError("limit must be a positive integer")
        if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
            raise ValueError("offset must be a non-negative integer")
        clean_limit = min(limit, 1000)

        clauses: list[str] = []
        params: list[Any] = []
        if schedule_id is not None:
            clauses.append("schedule_id = ?")
            params.append(schedule_id)
        if status is not None:
            clauses.append("status = ?")
            params.append(status)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        params.extend((clean_limit, offset))
        with self._lock, self._connection() as connection:
            rows = connection.execute(
                "SELECT * FROM schedule_execution_ledger"
                + where
                + " ORDER BY created_at DESC, execution_id DESC LIMIT ? OFFSET ?",
                params,
            ).fetchall()
        return [decoded for row in rows if (decoded := self._decode_row(row)) is not None]

    def list_executions(self, **kwargs: Any) -> builtins.list[dict[str, Any]]:
        """Compatibility alias for :meth:`list`."""

        return self.list(**kwargs)

    def list_active(
        self, *, schedule_id: str | None = None, limit: int = 100
    ) -> builtins.list[dict[str, Any]]:
        """List queued, running, and approval-waiting executions."""

        return self._list_active(schedule_id=schedule_id, limit=limit)

    def _list_active(
        self, *, schedule_id: str | None = None, limit: int = 100
    ) -> builtins.list[dict[str, Any]]:
        """Implementation for :meth:`list_active` using one SQL predicate."""

        if schedule_id is not None:
            schedule_id = _validate_identifier(schedule_id, "schedule_id")
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
            raise ValueError("limit must be a positive integer")
        clean_limit = min(limit, 1000)
        placeholders = ",".join("?" for _ in ACTIVE_SCHEDULE_EXECUTION_STATES)
        params: list[Any] = list(ACTIVE_SCHEDULE_EXECUTION_STATES)
        query = (
            "SELECT * FROM schedule_execution_ledger WHERE status IN ("
            + placeholders
            + ")"
        )
        if schedule_id is not None:
            query += " AND schedule_id = ?"
            params.append(schedule_id)
        query += " ORDER BY created_at ASC, execution_id ASC LIMIT ?"
        params.append(clean_limit)
        with self._lock, self._connection() as connection:
            rows = connection.execute(query, params).fetchall()
        return [decoded for row in rows if (decoded := self._decode_row(row)) is not None]

    def active_for_schedule(self, schedule_id: str) -> dict[str, Any] | None:
        """Return the one active execution projected for a schedule."""

        rows = self._list_active(schedule_id=schedule_id, limit=1)
        return rows[0] if rows else None

    get_active = active_for_schedule

    def project_active(
        self, schedule: str | Mapping[str, Any]
    ) -> dict[str, Any] | None:
        """Project durable active state onto an execution or schedule mapping.

        Passing a schedule ID returns the active execution (or ``None``).
        Passing a schedule mapping returns a copy with the legacy
        ``running_execution`` field updated, which lets existing schedule
        projections consume this ledger without writing a second state store.
        """

        if isinstance(schedule, Mapping):
            projected = dict(schedule)
            schedule_id = projected.get("schedule_id", projected.get("id"))
            if schedule_id is None:
                raise ValueError("schedule mapping must contain id or schedule_id")
            active = self.active_for_schedule(str(schedule_id))
            if active is None:
                projected.pop("running_execution", None)
            else:
                projected["running_execution"] = dict(active)
            return projected
        return self.active_for_schedule(schedule)

    project_schedule = project_active

    def transition(
        self,
        execution_id: str,
        to_status: str,
        *,
        result: Any = _MISSING,
        error: Any = _MISSING,
        completed_at: Any = _MISSING,
        expected_status: str | None = None,
        now: Any = None,
    ) -> dict[str, Any]:
        """Apply one legal lifecycle transition atomically.

        Terminal transitions set ``result``/``error`` and ``completed_at`` in
        the same SQLite update.  Callers may use ``expected_status`` to turn a
        stale worker into a deterministic conflict instead of overwriting a
        newer state.
        """

        clean_id = _validate_identifier(execution_id, "execution_id")
        target = self._validate_status(to_status, "to_status")
        if expected_status is not None:
            expected_status = self._validate_status(expected_status, "expected_status")
        timestamp = self._now(now)

        with self._lock, self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                row = connection.execute(
                    "SELECT * FROM schedule_execution_ledger WHERE execution_id = ?",
                    (clean_id,),
                ).fetchone()
                current = self._decode_row(row)
                if current is None:
                    raise ScheduleExecutionNotFoundError(
                        f"schedule execution not found: {execution_id}"
                    )
                source = str(current["status"])
                if expected_status is not None and source != expected_status:
                    raise ScheduleExecutionTransitionError(
                        f"expected status {expected_status}, found {source}"
                    )
                if target not in LEGAL_SCHEDULE_EXECUTION_TRANSITIONS[source]:
                    raise ScheduleExecutionTransitionError(
                        f"illegal schedule execution transition: {source} -> {target}"
                    )

                result_json = (
                    current["result"]
                    if result is _MISSING
                    else result
                )
                error_text = (
                    current["error"] if error is _MISSING else _error_text(error)
                )
                terminal_at = None
                if target in TERMINAL_SCHEDULE_EXECUTION_STATES:
                    terminal_at = (
                        timestamp
                        if completed_at is _MISSING
                        else _timestamp(completed_at)
                    )
                elif completed_at is not _MISSING:
                    raise ValueError("completed_at is only valid for terminal states")

                result_json_text = (
                    None
                    if result_json is None
                    else _json_text(result_json, "result")
                )
                started_at = current["started_at"]
                if target == RUNNING and started_at is None:
                    started_at = timestamp
                connection.execute(
                    """
                    UPDATE schedule_execution_ledger
                    SET status = ?, result_json = ?, error = ?,
                        updated_at = ?, started_at = ?, completed_at = ?
                    WHERE execution_id = ?
                    """,
                    (
                        target,
                        result_json_text,
                        error_text,
                        timestamp,
                        started_at,
                        terminal_at,
                        clean_id,
                    ),
                )
                updated_row = connection.execute(
                    "SELECT * FROM schedule_execution_ledger WHERE execution_id = ?",
                    (clean_id,),
                ).fetchone()
                connection.commit()
                updated = self._decode_row(updated_row)
                assert updated is not None
                return updated
            except BaseException:
                connection.rollback()
                raise

    def settle(
        self,
        execution_id: str,
        status: str = COMPLETED,
        *,
        result: Any = None,
        error: Any = None,
        completed_at: Any = _MISSING,
        expected_status: str | None = None,
        now: Any = None,
    ) -> dict[str, Any]:
        """Atomically settle an execution with its result or error."""

        clean_status = self._validate_status(status)
        if clean_status not in TERMINAL_SCHEDULE_EXECUTION_STATES:
            raise ValueError("settle status must be terminal")
        return self.transition(
            execution_id,
            clean_status,
            result=result,
            error=error,
            completed_at=completed_at,
            expected_status=expected_status,
            now=now,
        )

    def resume_after_approval(
        self,
        execution_id: str | None = None,
        *,
        schedule_id: str | None = None,
        idempotency_key: str | None = None,
        expected_revision: int | None = None,
        input_fingerprint: str | None = None,
        approved: bool = True,
        now: Any = None,
    ) -> dict[str, Any]:
        """Resume the original approval-waiting execution by its same ID.

        An approval resume never calls :meth:`reserve` and never allocates a
        second execution ID.  Supplying the original request tuple is
        optional, but when supplied it is checked against the persisted row.
        ``approved=False`` settles the same row as cancelled.
        """

        if execution_id is None:
            if schedule_id is None or idempotency_key is None:
                raise ValueError(
                    "execution_id or schedule_id plus idempotency_key is required"
                )
            record = self.get_by_idempotency(schedule_id, idempotency_key)
            if record is None:
                raise ScheduleExecutionNotFoundError(
                    "schedule execution not found for approval resume"
                )
            execution_id = str(record["execution_id"])
        record = self.require(execution_id)
        if schedule_id is not None and _validate_identifier(
            schedule_id, "schedule_id"
        ) != record["schedule_id"]:
            raise ScheduleExecutionIdempotencyConflict("schedule_id does not match execution")
        if idempotency_key is not None and _validate_identifier(
            idempotency_key, "idempotency_key"
        ) != record["idempotency_key"]:
            raise ScheduleExecutionIdempotencyConflict(
                "idempotency_key does not match execution"
            )
        if expected_revision is not None:
            if _validate_revision(expected_revision) != record["expected_revision"]:
                raise ScheduleExecutionIdempotencyConflict(
                    "expected_revision does not match execution"
                )
        if input_fingerprint is not None:
            if _validate_fingerprint(input_fingerprint) != record["input_fingerprint"]:
                raise ScheduleExecutionIdempotencyConflict(
                    "input_fingerprint does not match execution"
                )
        if not approved:
            return self.settle(
                execution_id,
                CANCELLED,
                error="approval denied",
                now=now,
                expected_status=WAITING_APPROVAL,
            )
        if record["status"] == RUNNING:
            return record
        return self.transition(
            execution_id,
            RUNNING,
            expected_status=WAITING_APPROVAL,
            now=now,
        )

    resume = resume_after_approval
    resume_approval = resume_after_approval

    def complete(
        self,
        execution_id: str,
        result: Any = None,
        *,
        now: Any = None,
        expected_status: str | None = None,
    ) -> dict[str, Any]:
        """Settle an execution as completed."""

        return self.settle(
            execution_id,
            COMPLETED,
            result=result,
            now=now,
            expected_status=expected_status,
        )

    def fail(
        self,
        execution_id: str,
        error: Any,
        *,
        result: Any = None,
        now: Any = None,
        expected_status: str | None = None,
    ) -> dict[str, Any]:
        """Settle an execution as failed."""

        return self.settle(
            execution_id,
            FAILED,
            result=result,
            error=error,
            now=now,
            expected_status=expected_status,
        )

    def cancel(
        self,
        execution_id: str,
        error: Any = "cancelled",
        *,
        now: Any = None,
        expected_status: str | None = None,
    ) -> dict[str, Any]:
        """Settle an execution as cancelled."""

        return self.settle(
            execution_id,
            CANCELLED,
            error=error,
            now=now,
            expected_status=expected_status,
        )

    def timeout(
        self,
        execution_id: str,
        error: Any = "timed out",
        *,
        now: Any = None,
        expected_status: str | None = None,
    ) -> dict[str, Any]:
        """Settle an execution as timed out."""

        return self.settle(
            execution_id,
            TIMED_OUT,
            error=error,
            now=now,
            expected_status=expected_status,
        )

    def close(self) -> None:
        """Close hook for callers that manage stores as resources.

        Connections are intentionally short-lived, so there is no connection
        to close.  The method exists to make lifecycle ownership explicit.
        """

    def __enter__(self) -> "ScheduleExecutionStore":
        """Return this store as a context manager."""

        return self

    def __exit__(self, *_args: Any) -> None:
        """Release the context-manager wrapper (connections are already closed)."""

        self.close()


# Public compatibility names used by small adapters.
ScheduleExecutionLedger = ScheduleExecutionStore
ExecutionStore = ScheduleExecutionStore


__all__ = [
    "ACTIVE_SCHEDULE_EXECUTION_STATES",
    "ActiveScheduleExecutionError",
    "CANCELLED",
    "COMPLETED",
    "DuplicateScheduleExecutionError",
    "ExecutionStore",
    "FAILED",
    "INVALID_SCHEDULE_EXECUTION_TRANSITIONS",
    "InvalidScheduleExecutionTransition",
    "LEGAL_SCHEDULE_EXECUTION_TRANSITIONS",
    "QUEUED",
    "RUNNING",
    "SCHEDULE_EXECUTION_STATES",
    "ScheduleExecutionAlreadyActive",
    "ScheduleExecutionConflictError",
    "ScheduleExecutionError",
    "ScheduleExecutionIdempotencyConflict",
    "ScheduleExecutionLedger",
    "ScheduleExecutionNotFoundError",
    "ScheduleExecutionStore",
    "ScheduleExecutionTransitionError",
    "TERMINAL_SCHEDULE_EXECUTION_STATES",
    "TIMED_OUT",
    "WAITING_APPROVAL",
    "default_schedule_execution_db_path",
]


# Kept as a named alias for callers that inspect the transition table using
# the plural form.
INVALID_SCHEDULE_EXECUTION_TRANSITIONS = LEGAL_SCHEDULE_EXECUTION_TRANSITIONS
