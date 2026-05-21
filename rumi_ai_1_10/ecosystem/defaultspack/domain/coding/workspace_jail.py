from __future__ import annotations

import ntpath
import os
from pathlib import Path
from typing import Any


PROTECTED_PATH_PARTS = frozenset({".git", ".rumi_snapshots"})
SECRET_PATH_PARTS = frozenset({
    ".aws",
    ".azure",
    ".docker",
    ".gnupg",
    ".kube",
    ".ssh",
    "secrets",
})
SECRET_FILE_NAMES = frozenset({
    ".dockercfg",
    ".git-credentials",
    ".npmrc",
    ".pypirc",
    ".netrc",
    "credentials",
    "credentials.json",
    "id_dsa",
    "id_ecdsa",
    "id_ed25519",
    "id_rsa",
    "kubeconfig",
    "token",
    "tokens.json",
})
SECRET_SUFFIXES = (".key", ".pem", ".p12", ".pfx", ".crt")
SAFE_ENV_EXAMPLES = (".example", ".sample", ".template")


class WorkspacePathViolation(ValueError):
    """Raised when a caller-provided path escapes or bypasses the workspace jail."""


class WorkspaceRestrictedPath(PermissionError):
    """Raised when a path is inside the workspace but is intentionally hidden."""


class WorkspaceJail:
    """Resolve caller paths through a single workspace boundary and secret filter."""

    def __init__(self, root: str | os.PathLike[str]) -> None:
        self.root = Path(root).expanduser().resolve()

    def resolve(self, path: Any, *, allow_absolute: bool = False) -> Path:
        text = self._path_text(path)
        if not allow_absolute:
            self._require_relative_user_path(text)
            candidate = self.root / text
        else:
            candidate = self._absolute_or_root_relative(text)
        resolved = candidate.resolve(strict=False)
        try:
            resolved.relative_to(self.root)
        except ValueError as exc:
            raise WorkspacePathViolation(
                f"Path traversal detected: '{text}' resolves outside workspace root"
            ) from exc
        return resolved

    def resolve_user_path(self, path: Any) -> Path:
        return self.resolve(path, allow_absolute=False)

    def relative(self, path: str | os.PathLike[str]) -> str:
        return os.path.relpath(path, self.root).replace(os.sep, "/")

    def ensure_allowed(self, rel: Any, *, operation: str = "access") -> None:
        reason = self.restriction_reason(rel)
        if reason:
            raise WorkspaceRestrictedPath(
                f"Restricted workspace path cannot be used for {operation}: {rel} ({reason})"
            )

    def restriction_reason(self, rel: Any) -> str | None:
        parts = self._relative_parts(rel)
        if not parts:
            return None
        if any(part in PROTECTED_PATH_PARTS for part in parts):
            return "protected_path"
        if any(part in SECRET_PATH_PARTS for part in parts):
            return "secret_directory"
        name = parts[-1]
        lower_name = name.lower()
        if self._is_env_file(lower_name):
            return "env_file"
        if lower_name in SECRET_FILE_NAMES:
            return "secret_file"
        if lower_name.endswith(SECRET_SUFFIXES):
            return "secret_file"
        return None

    @staticmethod
    def _path_text(path: Any) -> str:
        text = str(path if path is not None else "")
        if text == "":
            raise WorkspacePathViolation("Path must not be empty")
        return text

    @staticmethod
    def _relative_parts(rel: Any) -> tuple[str, ...]:
        text = str(rel or "").replace("\\", "/").strip("/")
        if not text or text == ".":
            return ()
        return tuple(part for part in text.split("/") if part and part != ".")

    @staticmethod
    def _is_env_file(lower_name: str) -> bool:
        if lower_name == ".env":
            return True
        if not lower_name.startswith(".env."):
            return False
        return not lower_name.endswith(SAFE_ENV_EXAMPLES)

    @staticmethod
    def _is_absolute(text: str) -> bool:
        return os.path.isabs(os.path.expanduser(text)) or ntpath.isabs(text)

    def _absolute_or_root_relative(self, text: str) -> Path:
        drive, _ = ntpath.splitdrive(text)
        if drive and not ntpath.isabs(text):
            raise WorkspacePathViolation("Drive-qualified paths are not accepted")
        expanded = Path(text).expanduser()
        if expanded.is_absolute():
            return expanded
        if ntpath.isabs(text):
            raise WorkspacePathViolation("Windows absolute paths are not accepted")
        return self.root / expanded

    def _require_relative_user_path(self, text: str) -> None:
        if text.startswith("~"):
            raise WorkspacePathViolation("Home-relative paths are not accepted")
        drive, _ = ntpath.splitdrive(text)
        if drive:
            raise WorkspacePathViolation("Drive-qualified paths are not accepted")
        if self._is_absolute(text):
            raise WorkspacePathViolation("Absolute paths are not accepted")
        parts = self._relative_parts(text)
        if any(part == ".." for part in parts):
            raise WorkspacePathViolation(
                "Parent-directory traversal is not accepted outside workspace root"
            )
