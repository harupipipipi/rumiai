from __future__ import annotations

import contextlib
import json
import os
import platform
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator


_HEX_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


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
            }
        )
        try:
            self._process = subprocess.Popen(
                [str(binary)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                env=env,
                start_new_session=True,
            )
            return True
        except Exception:
            self._process = None
            return False

    def stop(self) -> None:
        process = self._process
        self._process = None
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
