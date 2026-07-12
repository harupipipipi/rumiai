from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


_TRUE_VALUES = {"1", "true", "yes", "on", "enabled"}


def default_pack_root() -> Path:
    return Path(__file__).resolve().parents[2]


def default_store_path() -> Path:
    override = os.environ.get("RUMI_DEFAULTSPACK_P2P_STORE_PATH", "").strip()
    if override:
        return Path(override).expanduser()
    return default_pack_root() / "user_data" / "shared" / "p2p"


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in _TRUE_VALUES


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or str(raw).strip() == "":
        return default
    try:
        return int(str(raw).strip())
    except ValueError:
        return default


@dataclass
class P2PSettings:
    enabled: bool = False
    bind_host: str = "127.0.0.1"
    bind_port: int = 0
    lan_discovery: bool = False
    internet_relay: bool = False
    store_path: Path = field(default_factory=default_store_path)
    envelope_ttl_seconds: int = 300
    replay_ttl_seconds: int = 600
    pairing_ttl_seconds: int = 300

    @classmethod
    def from_env(cls, overrides: dict[str, Any] | None = None) -> "P2PSettings":
        overrides = overrides if isinstance(overrides, dict) else {}
        bind_host = str(
            overrides.get("bind_host")
            or os.environ.get("RUMI_DEFAULTSPACK_P2P_BIND_HOST")
            or "127.0.0.1"
        ).strip() or "127.0.0.1"
        store_path = overrides.get("store_path") or default_store_path()
        settings = cls(
            enabled=_coerce_bool(overrides.get("enabled"), _env_bool("RUMI_DEFAULTSPACK_P2P_ENABLED", False)),
            bind_host=bind_host,
            bind_port=int(overrides.get("bind_port") or _env_int("RUMI_DEFAULTSPACK_P2P_BIND_PORT", 0)),
            lan_discovery=_coerce_bool(
                overrides.get("lan_discovery"),
                _env_bool("RUMI_DEFAULTSPACK_P2P_LAN_DISCOVERY", False),
            ),
            internet_relay=False,
            store_path=Path(store_path).expanduser(),
            envelope_ttl_seconds=int(
                overrides.get("envelope_ttl_seconds")
                or _env_int("RUMI_DEFAULTSPACK_P2P_ENVELOPE_TTL_SECONDS", 300)
            ),
            replay_ttl_seconds=int(
                overrides.get("replay_ttl_seconds")
                or _env_int("RUMI_DEFAULTSPACK_P2P_REPLAY_TTL_SECONDS", 600)
            ),
            pairing_ttl_seconds=int(
                overrides.get("pairing_ttl_seconds")
                or _env_int("RUMI_DEFAULTSPACK_P2P_PAIRING_TTL_SECONDS", 300)
            ),
        )
        return settings.hardened()

    def hardened(self) -> "P2PSettings":
        self.internet_relay = False
        if not self.bind_host:
            self.bind_host = "127.0.0.1"
        return self

    def as_dict(self) -> dict[str, Any]:
        return {
            "enabled": bool(self.enabled),
            "bind_host": self.bind_host,
            "bind_port": int(self.bind_port),
            "lan_discovery": bool(self.lan_discovery),
            "internet_relay": False,
            "store_path": str(self.store_path),
            "envelope_ttl_seconds": int(self.envelope_ttl_seconds),
            "replay_ttl_seconds": int(self.replay_ttl_seconds),
            "pairing_ttl_seconds": int(self.pairing_ttl_seconds),
        }


def _coerce_bool(value: Any, default: bool) -> bool:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in _TRUE_VALUES
