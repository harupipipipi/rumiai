from __future__ import annotations

import json
import secrets
import tempfile
import time
from pathlib import Path
from typing import Any


DEFAULT_PORT = 8766
DEFAULT_STALE_SECONDS = 45


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _now_ts() -> float:
    return time.time()


def _safe_id(value: Any, *, fallback: str) -> str:
    raw = "".join(ch for ch in str(value or "").strip() if ch.isalnum() or ch in {"-", "_", "."})
    return (raw or fallback)[:80]


def _read_json(path: Path, default: Any) -> Any:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default
    return value if isinstance(value, type(default)) else default


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", delete=False, dir=str(path.parent), encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        temp_path = Path(handle.name)
    temp_path.replace(path)


class BrowserCompanionBridgeStore:
    """File-backed bridge state shared by tool subprocesses and HTTP routes."""

    def __init__(self, root: Path | None = None) -> None:
        pack_root = Path(__file__).resolve().parents[2]
        self._root = root or pack_root / "user_data" / "shared" / "browser_companion"
        self._config_path = self._root / "bridge_config.json"
        self._session_path = self._root / "session.json"
        self._clients_dir = self._root / "clients"
        self._commands_dir = self._root / "commands"
        self._root.mkdir(parents=True, exist_ok=True)
        self._clients_dir.mkdir(parents=True, exist_ok=True)
        self._commands_dir.mkdir(parents=True, exist_ok=True)

    @property
    def root_dir(self) -> Path:
        return self._root

    def ensure_pairing(self, *, rotate: bool = False) -> dict[str, Any]:
        config = _read_json(self._config_path, {})
        token = str(config.get("pairing_token") or "").strip()
        if rotate or not token:
            token = secrets.token_urlsafe(24)
            config = {
                "pairing_token": token,
                "created_at": config.get("created_at") or _now_iso(),
                "updated_at": _now_iso(),
            }
            _write_json(self._config_path, config)
        return dict(config)

    def pairing_token(self) -> str:
        return str(self.ensure_pairing().get("pairing_token") or "")

    def pairing_authorized(self, token: str) -> bool:
        expected = self.pairing_token()
        provided = str(token or "").strip()
        return bool(expected and provided and secrets.compare_digest(expected, provided))

    def session(self) -> dict[str, Any]:
        return _read_json(self._session_path, {})

    def set_active_client(self, client_id: str) -> dict[str, Any]:
        value = self.session()
        value["active_client_id"] = _safe_id(client_id, fallback="client")
        value["updated_at"] = _now_iso()
        _write_json(self._session_path, value)
        return value

    def active_client_id(self) -> str:
        return str(self.session().get("active_client_id") or "")

    def _client_path(self, client_id: str) -> Path:
        return self._clients_dir / f"{_safe_id(client_id, fallback='client')}.json"

    def _command_path(self, command_id: str) -> Path:
        return self._commands_dir / f"{_safe_id(command_id, fallback='command')}.json"

    def upsert_client(self, payload: dict[str, Any] | None) -> dict[str, Any]:
        payload = dict(payload or {})
        client_id = _safe_id(payload.get("client_id") or payload.get("id"), fallback="client")
        previous = _read_json(self._client_path(client_id), {})
        previous = previous if isinstance(previous, dict) else {}
        browser_profile_id = _safe_id(
            payload.get("browser_profile_id") or previous.get("browser_profile_id"),
            fallback=client_id,
        )
        installation_id = _safe_id(
            payload.get("installation_id") or previous.get("installation_id"),
            fallback=client_id,
        )
        profile_label = str(
            payload.get("profile_label") or payload.get("profileLabel") or previous.get("profile_label") or ""
        ).strip()
        tabs = payload.get("tabs")
        if not isinstance(tabs, list):
            tabs = payload.get("tabs_summary")
        if not isinstance(tabs, list):
            tabs = previous.get("tabs")
        active_tab_id = payload.get("active_tab_id")
        if active_tab_id is None:
            active_tab_id = previous.get("active_tab_id")
        if active_tab_id is None and isinstance(tabs, list):
            for tab in tabs:
                if isinstance(tab, dict) and tab.get("active"):
                    active_tab_id = tab.get("id")
                    break
        label = str(
            payload.get("label")
            or payload.get("browser_name")
            or previous.get("label")
            or client_id
        )
        browser_name = str(payload.get("browser_name") or payload.get("browser") or previous.get("browser_name") or "")
        browser_version = str(payload.get("browser_version") or payload.get("version") or previous.get("browser_version") or "")
        extension_id = str(payload.get("extension_id") or previous.get("extension_id") or "")
        extension_version = str(payload.get("extension_version") or previous.get("extension_version") or "")
        capabilities = payload.get("capabilities") if isinstance(payload.get("capabilities"), dict) else previous.get("capabilities")
        record = {
            "client_id": client_id,
            "label": label,
            "browser_profile_id": browser_profile_id,
            "profile_label": profile_label or label,
            "installation_id": installation_id,
            "client_profile": {
                "browser_profile_id": browser_profile_id,
                "profile_label": profile_label or label,
                "installation_id": installation_id,
                "extension_id": extension_id,
                "browser_name": browser_name,
                "browser_version": browser_version,
            },
            "browser_name": browser_name,
            "browser_version": browser_version,
            "extension_version": extension_version,
            "extension_id": extension_id,
            "user_agent": str(payload.get("user_agent") or previous.get("user_agent") or ""),
            "platform": str(payload.get("platform") or previous.get("platform") or ""),
            "tabs": tabs if isinstance(tabs, list) else [],
            "active_tab_id": active_tab_id,
            "capabilities": capabilities if isinstance(capabilities, dict) else {},
            "connected_at": payload.get("connected_at") or previous.get("connected_at") or _now_iso(),
            "last_seen": _now_iso(),
            "last_seen_ts": _now_ts(),
        }
        _write_json(self._client_path(client_id), record)
        if not self.active_client_id():
            self.set_active_client(client_id)
        return record

    def _client_records(self) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        for path in sorted(self._clients_dir.glob("*.json")):
            value = _read_json(path, {})
            if isinstance(value, dict) and value.get("client_id"):
                records.append(value)
        return records

    def list_clients(self, *, include_stale: bool = False, stale_after_seconds: int = DEFAULT_STALE_SECONDS) -> list[dict[str, Any]]:
        now = _now_ts()
        active_client_id = self.active_client_id()
        records: list[dict[str, Any]] = []
        for record in self._client_records():
            last_seen_ts = float(record.get("last_seen_ts") or 0.0)
            is_stale = (now - last_seen_ts) > stale_after_seconds
            if is_stale and not include_stale:
                continue
            item = dict(record)
            item["is_stale"] = is_stale
            item["is_active"] = record.get("client_id") == active_client_id
            records.append(item)
        records.sort(key=lambda item: float(item.get("last_seen_ts") or 0.0), reverse=True)
        return records

    def get_client(self, client_id: str) -> dict[str, Any] | None:
        value = _read_json(self._client_path(client_id), {})
        return value if isinstance(value, dict) and value.get("client_id") else None

    def resolve_client(
        self,
        *,
        client_id: str = "",
        browser_profile_id: str = "",
        installation_id: str = "",
        browser: str = "",
        label: str = "",
        profile_label: str = "",
    ) -> dict[str, Any] | None:
        candidates = self.list_clients()
        if client_id:
            normalized = _safe_id(client_id, fallback="client")
            for candidate in candidates:
                if candidate.get("client_id") == normalized:
                    return candidate
            return None
        if browser_profile_id:
            normalized = _safe_id(browser_profile_id, fallback="profile")
            for candidate in candidates:
                if candidate.get("browser_profile_id") == normalized:
                    return candidate
            return None
        if installation_id:
            normalized = _safe_id(installation_id, fallback="installation")
            for candidate in candidates:
                if candidate.get("installation_id") == normalized:
                    return candidate
            return None
        browser_lower = str(browser or "").strip().casefold()
        label_lower = str(label or "").strip().casefold()
        profile_label_lower = str(profile_label or "").strip().casefold()
        if browser_lower:
            candidates = [
                candidate
                for candidate in candidates
                if browser_lower in str(candidate.get("browser_name") or "").casefold()
            ]
        if label_lower:
            candidates = [
                candidate
                for candidate in candidates
                if label_lower in str(candidate.get("label") or "").casefold()
            ]
        if profile_label_lower:
            candidates = [
                candidate
                for candidate in candidates
                if profile_label_lower in str(candidate.get("profile_label") or "").casefold()
            ]
        if not candidates:
            return None
        for candidate in candidates:
            if candidate.get("is_active"):
                return candidate
        return candidates[0]

    def create_command(self, client_id: str, request: dict[str, Any]) -> dict[str, Any]:
        command_id = f"cmd_{secrets.token_hex(8)}"
        record = {
            "command_id": command_id,
            "client_id": _safe_id(client_id, fallback="client"),
            "request": dict(request or {}),
            "status": "pending",
            "created_at": _now_iso(),
            "created_at_ts": _now_ts(),
            "updated_at": _now_iso(),
        }
        _write_json(self._command_path(command_id), record)
        return record

    def claim_next_command(self, client_id: str) -> dict[str, Any] | None:
        normalized = _safe_id(client_id, fallback="client")
        pending: list[tuple[float, Path, dict[str, Any]]] = []
        for path in sorted(self._commands_dir.glob("*.json")):
            record = _read_json(path, {})
            if not isinstance(record, dict):
                continue
            if record.get("client_id") != normalized or record.get("status") != "pending":
                continue
            pending.append((float(record.get("created_at_ts") or 0.0), path, record))
        if not pending:
            return None
        _, path, record = min(pending, key=lambda item: item[0])
        record["status"] = "in_progress"
        record["claimed_at"] = _now_iso()
        record["claimed_by"] = normalized
        record["updated_at"] = _now_iso()
        _write_json(path, record)
        return record

    def complete_command(self, client_id: str, command_id: str, result: dict[str, Any]) -> dict[str, Any]:
        path = self._command_path(command_id)
        record = _read_json(path, {})
        if not isinstance(record, dict) or record.get("command_id") != command_id:
            raise KeyError(f"Unknown command_id: {command_id}")
        normalized = _safe_id(client_id, fallback="client")
        if record.get("client_id") != normalized:
            raise ValueError("Command client mismatch")
        record["status"] = "completed"
        record["updated_at"] = _now_iso()
        record["completed_at"] = _now_iso()
        record["result"] = dict(result or {})
        _write_json(path, record)
        return record

    def wait_for_command(self, command_id: str, *, timeout_seconds: float = 20.0, poll_interval: float = 0.2) -> dict[str, Any]:
        deadline = _now_ts() + max(timeout_seconds, 0.1)
        path = self._command_path(command_id)
        while _now_ts() <= deadline:
            record = _read_json(path, {})
            if isinstance(record, dict) and record.get("status") == "completed":
                return record
            time.sleep(max(poll_interval, 0.05))
        record = _read_json(path, {})
        if isinstance(record, dict):
            record["status"] = "timed_out"
            record["updated_at"] = _now_iso()
            _write_json(path, record)
            return record
        return {
            "command_id": command_id,
            "status": "timed_out",
            "updated_at": _now_iso(),
        }


def bearer_token_from_headers(headers: dict[str, Any] | None) -> str:
    if not isinstance(headers, dict):
        return ""
    raw = str(
        headers.get("Authorization")
        or headers.get("authorization")
        or ""
    ).strip()
    if raw.lower().startswith("bearer "):
        return raw[7:].strip()
    return ""


def candidate_base_urls(context: dict[str, Any] | None) -> list[str]:
    values: list[str] = []
    for candidate in (
        (context or {}).get("public_base_url") if isinstance(context, dict) else None,
        (context or {}).get("base_url") if isinstance(context, dict) else None,
    ):
        if isinstance(candidate, str) and candidate.strip():
            values.append(candidate.strip().rstrip("/"))
    for value in (
        "http://127.0.0.1:{port}".format(port=DEFAULT_PORT),
        "http://localhost:{port}".format(port=DEFAULT_PORT),
    ):
        if value not in values:
            values.append(value)
    return values
