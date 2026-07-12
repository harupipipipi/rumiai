"""macOS Swift host bridge for Computer Use.

The Swift helper owns macOS desktop primitives. Python stays as the policy,
approval, artifact, and fallback orchestration layer.
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
from pathlib import Path
from typing import Any


_HELPER_BINARY_NAME = "mac_computer_use_host"
_HELPER_TIMEOUT_SECONDS = 30
_COMPILE_TIMEOUT_SECONDS = 30


class MacSwiftHostError(RuntimeError):
    """Raised when the Swift host could not complete a request."""


class MacSwiftComputerHost:
    def __init__(
        self,
        *,
        pack_root: Path | None = None,
        source_path: Path | None = None,
        binary_path: Path | None = None,
    ) -> None:
        self._pack_root = pack_root or Path(__file__).resolve().parents[3]
        self._source_path = source_path or Path(__file__).with_name("ComputerUseHost.swift")
        helper_dir = self._default_helper_dir(self._pack_root)
        self._binary_path = binary_path or helper_dir / _HELPER_BINARY_NAME

    def available(self) -> bool:
        if platform.system() != "Darwin":
            return False
        if os.environ.get("PYTEST_CURRENT_TEST") and not os.environ.get("RUMI_MAC_COMPUTER_USE_HOST"):
            return False
        override = self._env_binary_path()
        if override is not None:
            return True
        if self._usable_binary(self._binary_path):
            return True
        return self._source_path.exists() and shutil.which("swiftc") is not None

    def run(
        self,
        action: str,
        args: dict[str, Any] | None = None,
        *,
        timeout: float = _HELPER_TIMEOUT_SECONDS,
    ) -> dict[str, Any]:
        if platform.system() != "Darwin":
            raise MacSwiftHostError("macOS Swift host is only available on macOS.")
        binary = self._ensure_binary()
        if binary is None:
            raise MacSwiftHostError("macOS Swift host binary is unavailable.")
        request = {"action": str(action or ""), "args": dict(args or {})}
        completed = subprocess.run(
            [str(binary)],
            input=json.dumps(request, ensure_ascii=False),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        if completed.returncode != 0:
            stderr = completed.stderr.strip()
            raise MacSwiftHostError(f"macOS Swift host exited with status {completed.returncode}: {stderr}")
        try:
            response = json.loads(completed.stdout.strip() or "{}")
        except json.JSONDecodeError as exc:
            raise MacSwiftHostError("macOS Swift host returned invalid JSON.") from exc
        if not isinstance(response, dict):
            raise MacSwiftHostError("macOS Swift host returned a non-object response.")
        if response.get("ok") is True and isinstance(response.get("result"), dict):
            return dict(response["result"])
        message = str(response.get("error") or "macOS Swift host request failed.")
        code = str(response.get("error_code") or "MAC_SWIFT_HOST_FAILED")
        result = response.get("result") if isinstance(response.get("result"), dict) else {}
        payload = dict(result)
        payload.update({"is_error": True, "error_code": code, "reason": message})
        return payload

    def _ensure_binary(self) -> Path | None:
        override = self._env_binary_path()
        if override is not None:
            return override
        if self._usable_binary(self._binary_path) and self._binary_is_current():
            return self._binary_path
        swiftc = shutil.which("swiftc")
        if swiftc is None or not self._source_path.exists():
            return self._binary_path if self._usable_binary(self._binary_path) else None
        self._binary_path.parent.mkdir(parents=True, exist_ok=True)
        completed = subprocess.run(
            [swiftc, str(self._source_path), "-o", str(self._binary_path)],
            capture_output=True,
            text=True,
            timeout=_COMPILE_TIMEOUT_SECONDS,
            check=False,
        )
        if self._usable_binary(self._binary_path):
            self._binary_path.chmod(self._binary_path.stat().st_mode | 0o755)
        if completed.returncode != 0 or not self._usable_binary(self._binary_path):
            return None
        return self._binary_path

    def _binary_is_current(self) -> bool:
        try:
            return self._binary_path.stat().st_mtime >= self._source_path.stat().st_mtime
        except OSError:
            return False

    @staticmethod
    def _default_helper_dir(pack_root: Path) -> Path:
        user_data = os.environ.get("RUMI_USER_DATA", "").strip()
        if user_data:
            return Path(user_data) / "shared" / "helpers" / "mac_computer_use"
        return pack_root / "user_data" / "shared" / "helpers" / "mac_computer_use"

    @staticmethod
    def _usable_binary(path: Path | None) -> bool:
        if path is None:
            return False
        try:
            return path.is_file() and os.access(path, os.X_OK)
        except OSError:
            return False

    def _env_binary_path(self) -> Path | None:
        override = os.environ.get("RUMI_MAC_COMPUTER_USE_HOST", "").strip()
        if not override:
            return None
        path = Path(override).expanduser()
        return path if self._usable_binary(path) else None


def run_swift_host(action: str, args: dict[str, Any] | None = None) -> dict[str, Any]:
    return MacSwiftComputerHost().run(action, args or {})
