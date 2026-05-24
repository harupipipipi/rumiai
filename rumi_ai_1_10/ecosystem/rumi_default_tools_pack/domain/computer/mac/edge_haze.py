from __future__ import annotations

import contextlib
import json
import os
import platform
import re
import shutil
import signal
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator


_HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")
_LEASE_SCHEMA = "rumi.edge_haze_lease.v1"
_STANDALONE_SEQUENCE_ID = "standalone"
_SEQUENCE_IDLE_SECONDS = 120.0


@dataclass(frozen=True)
class EdgeHazeSettings:
    enabled: bool = True
    preset: str = "aurora"
    start_color: str = "#6EE7F9"
    end_color: str = "#A78BFA"
    accent_color: str = "#F0ABFC"
    opacity: float = 0.36
    edge_width: int = 150
    animation_speed: float = 1.0
    linger_seconds: float = 3.0


class ComputerUseEdgeHazeManager:
    """Starts the macOS click-through edge haze helper around visible actions."""

    def __init__(
        self,
        *,
        pack_root: Path | None = None,
        settings_path: Path | None = None,
        source_path: Path | None = None,
        binary_path: Path | None = None,
        settings: EdgeHazeSettings | None = None,
    ) -> None:
        self._pack_root = pack_root or Path(__file__).resolve().parents[3]
        self._source_path = source_path or Path(__file__).with_name("EdgeHaze.swift")
        self._binary_path = binary_path or self._pack_root / "user_data" / "shared" / "helpers" / "edge_haze" / "edge_haze"
        self._settings_path = settings_path or self._default_settings_path(self._pack_root)
        self._settings = settings
        self._process: subprocess.Popen[Any] | None = None
        self._sequence_id = _STANDALONE_SEQUENCE_ID
        self._lease_path = self._default_lease_path(self._binary_path)

    @classmethod
    def from_pack_root(cls, pack_root: Path) -> "ComputerUseEdgeHazeManager":
        return cls(pack_root=pack_root)

    @contextlib.contextmanager
    def active(self, *, action: str = "", payload: dict[str, Any] | None = None) -> Iterator[None]:
        self.start(action=action, payload=payload)
        try:
            yield
        finally:
            self.stop()

    def start(self, *, action: str = "", payload: dict[str, Any] | None = None) -> bool:
        payload = payload or {}
        settings = self.settings()
        if not settings.enabled:
            return False
        if os.environ.get("PYTEST_CURRENT_TEST") and "RUMI_COMPUTER_USE_HAZE" not in os.environ:
            return False
        if platform.system() != "Darwin":
            return False
        binary = self._ensure_binary()
        if binary is None:
            return False
        self._sequence_id = self._sequence_id_from_payload(payload)
        self._lease_path = self._default_lease_path(binary)
        existing = self._read_lease(self._lease_path)
        existing_pid = self._lease_pid(existing)
        if existing_pid and existing.get("sequence_id") == self._sequence_id and self._pid_alive(existing_pid):
            self._write_lease_for_pid(existing_pid, action=action, active=True)
            return True
        if existing_pid and existing.get("sequence_id") != self._sequence_id and self._pid_alive(existing_pid):
            self._terminate_pid(existing_pid)
        env = os.environ.copy()
        env.update(
            {
                "RUMI_EDGE_HAZE_PRESET": settings.preset,
                "RUMI_EDGE_HAZE_START_COLOR": settings.start_color,
                "RUMI_EDGE_HAZE_END_COLOR": settings.end_color,
                "RUMI_EDGE_HAZE_ACCENT_COLOR": settings.accent_color,
                "RUMI_EDGE_HAZE_OPACITY": str(settings.opacity),
                "RUMI_EDGE_HAZE_EDGE_WIDTH": str(settings.edge_width),
                "RUMI_EDGE_HAZE_SPEED": str(settings.animation_speed),
                "RUMI_EDGE_HAZE_ACTION": action,
                "RUMI_EDGE_HAZE_LEASE_PATH": str(self._lease_path),
                "RUMI_EDGE_HAZE_SEQUENCE_ID": self._sequence_id,
            }
        )
        try:
            process = subprocess.Popen(
                [str(binary)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                env=env,
                start_new_session=True,
            )
            self._process = process
            self._write_lease_for_pid(int(process.pid), action=action, active=True)
            return True
        except Exception:
            self._process = None
            return False

    def stop(self) -> None:
        process = self._process
        self._process = None
        pid = int(process.pid) if process is not None else self._lease_pid(self._read_lease(self._lease_path))
        if not pid:
            return
        if self._sequence_id != _STANDALONE_SEQUENCE_ID:
            self._write_lease_for_pid(pid, action="", active=False)
            return
        linger_seconds = max(0.0, float(self.settings().linger_seconds))
        if linger_seconds > 0:
            self._write_lease_for_pid(pid, action="", active=False)
            return
        self._terminate_process(process)
        self._remove_lease_if_matches(pid=pid, sequence_id=self._sequence_id)

    def end_sequence(self, sequence_id: str) -> None:
        sequence_id = str(sequence_id or "").strip()
        if not sequence_id:
            return
        lease = self._read_lease(self._lease_path)
        if lease.get("sequence_id") != sequence_id:
            return
        pid = self._lease_pid(lease)
        if pid:
            self._terminate_pid(pid)
        self._remove_lease_if_matches(pid=pid, sequence_id=sequence_id)

    @staticmethod
    def _terminate_process(process: subprocess.Popen[Any] | None) -> None:
        if process is None:
            return
        try:
            if process.poll() is not None:
                return
            process.terminate()
            process.wait(timeout=1)
        except Exception:
            try:
                process.kill()
            except Exception:
                pass

    @classmethod
    def _terminate_pid(cls, pid: int) -> None:
        if pid <= 0:
            return
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            return
        except Exception:
            return
        deadline = time.time() + 1.0
        while time.time() < deadline:
            if not cls._pid_alive(pid):
                return
            time.sleep(0.05)
        try:
            os.kill(pid, signal.SIGKILL)
        except Exception:
            pass

    def settings(self) -> EdgeHazeSettings:
        if self._settings is None:
            self._settings = self._load_settings()
        return self._settings

    def _load_settings(self) -> EdgeHazeSettings:
        values: dict[str, Any] = {}
        try:
            raw = json.loads(self._settings_path.read_text(encoding="utf-8"))
            section = raw.get("computer_use_haze") if isinstance(raw, dict) else None
            if isinstance(section, dict):
                values = dict(section)
        except Exception:
            values = {}
        env_enabled = os.environ.get("RUMI_COMPUTER_USE_HAZE")
        enabled = self._truthy(values.get("enabled", True))
        if env_enabled is not None:
            enabled = self._truthy(env_enabled)
        return EdgeHazeSettings(
            enabled=enabled,
            preset=self._choice(values.get("preset"), {"aurora", "ocean", "ember", "custom"}, "aurora"),
            start_color=self._hex_color(values.get("start_color"), "#6EE7F9"),
            end_color=self._hex_color(values.get("end_color"), "#A78BFA"),
            accent_color=self._hex_color(values.get("accent_color"), "#F0ABFC"),
            opacity=self._clamped_float(values.get("opacity"), 0.36, 0.05, 0.9),
            edge_width=int(self._clamped_float(values.get("edge_width"), 150, 40, 420)),
            animation_speed=self._clamped_float(values.get("animation_speed"), 1.0, 0.1, 4.0),
            linger_seconds=self._clamped_float(values.get("linger_seconds"), 3.0, 0.0, 30.0),
        )

    def _ensure_binary(self) -> Path | None:
        if not self._source_path.exists():
            return None
        swiftc = shutil.which("swiftc")
        if not swiftc:
            return None
        try:
            if self._binary_path.exists() and self._binary_path.stat().st_mtime >= self._source_path.stat().st_mtime:
                return self._binary_path
            self._binary_path.parent.mkdir(parents=True, exist_ok=True)
            completed = subprocess.run(
                [swiftc, str(self._source_path), "-o", str(self._binary_path)],
                capture_output=True,
                timeout=25,
                check=False,
            )
            if completed.returncode != 0 or not self._binary_path.exists():
                return None
            return self._binary_path
        except Exception:
            return None

    @staticmethod
    def _default_settings_path(pack_root: Path) -> Path:
        override = os.environ.get("RUMI_DEFAULTSPACK_FRONTEND_SETTINGS_PATH", "").strip()
        if override:
            return Path(override)
        ecosystem_root = pack_root.parent
        return ecosystem_root / "defaultspack" / "user_data" / "shared" / "frontend_settings.json"

    @staticmethod
    def _default_lease_path(binary_path: Path) -> Path:
        return binary_path.with_name(binary_path.name + ".lease.json")

    @staticmethod
    def _sequence_id_from_payload(payload: dict[str, Any]) -> str:
        for key in ("computer_use_haze_sequence_id", "computer_use_sequence_id", "run_id", "request_id"):
            value = str(payload.get(key) or "").strip()
            if value:
                return value
        return _STANDALONE_SEQUENCE_ID

    def _deadline_seconds(self, *, active: bool) -> float:
        if self._sequence_id != _STANDALONE_SEQUENCE_ID:
            return _SEQUENCE_IDLE_SECONDS
        if active:
            return max(1.0, float(self.settings().linger_seconds))
        return max(0.0, float(self.settings().linger_seconds))

    def _write_lease_for_pid(self, pid: int, *, action: str, active: bool) -> None:
        now = time.time()
        self._write_lease(
            self._lease_path,
            {
                "schema": _LEASE_SCHEMA,
                "pid": int(pid),
                "sequence_id": self._sequence_id,
                "deadline_epoch": now + self._deadline_seconds(active=active),
                "updated_at_epoch": now,
                "action": action,
            },
        )

    @staticmethod
    def _write_lease(path: Path, value: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(json.dumps(value, sort_keys=True), encoding="utf-8")
        tmp.replace(path)

    @staticmethod
    def _read_lease(path: Path) -> dict[str, Any]:
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except Exception:
            return {}

    @staticmethod
    def _lease_pid(lease: dict[str, Any]) -> int:
        try:
            return int(lease.get("pid") or 0)
        except Exception:
            return 0

    @staticmethod
    def _pid_alive(pid: int) -> bool:
        if pid <= 0:
            return False
        try:
            os.kill(pid, 0)
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        except Exception:
            return False

    def _remove_lease_if_matches(self, *, pid: int, sequence_id: str) -> None:
        lease = self._read_lease(self._lease_path)
        if self._lease_pid(lease) != pid or lease.get("sequence_id") != sequence_id:
            return
        try:
            self._lease_path.unlink()
        except FileNotFoundError:
            pass
        except Exception:
            pass

    @staticmethod
    def _truthy(value: Any) -> bool:
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "y", "on"}
        return bool(value)

    @staticmethod
    def _choice(value: Any, allowed: set[str], default: str) -> str:
        candidate = str(value or "").strip().lower()
        return candidate if candidate in allowed else default

    @staticmethod
    def _hex_color(value: Any, default: str) -> str:
        candidate = str(value or "").strip()
        return candidate.upper() if _HEX_RE.match(candidate) else default

    @staticmethod
    def _clamped_float(value: Any, default: float, minimum: float, maximum: float) -> float:
        try:
            return max(minimum, min(maximum, float(value)))
        except (TypeError, ValueError):
            return default
