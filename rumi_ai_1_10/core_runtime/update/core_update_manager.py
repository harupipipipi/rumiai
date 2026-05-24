"""Core update manager.

Core updates are intentionally manual by default.  They stage and validate a
bundle before applying files into the Python runtime, and they reject writes to
managed pack/user-data paths.
"""

from __future__ import annotations

import fnmatch
import json
import os
import shutil
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Mapping

from ..pack_seed import utc_now_iso
from ..paths import BASE_DIR, USER_DATA_DIR
from .download import download_to_file, safe_extract_zip, verify_sha256
from .models import CoreUpdateResult
from .stage_ids import make_stage_id, resolve_stage_dir
from .trust import (
    core_bundle_signature_payload,
    load_official_trust_roots,
    signature_string_from_entry,
    verify_index_signatures,
    verify_signature,
)
from .versioning import read_pyproject_version, version_newer

DEFAULT_CORE_INDEX_URL = (
    "https://github.com/harupipipipi/rumiai/releases/latest/download/core-index.stable.json"
)
CORE_PROTECTED_PATTERNS = (
    "user_data",
    "user_data/**",
    "packs",
    "packs/**",
    "pack_state",
    "pack_state/**",
    "logs",
    "logs/**",
    "settings",
    "settings/**",
    "update_state",
    "update_state/**",
    "ecosystem",
    "ecosystem/**",
    "pack_seeds",
    "pack_seeds/**",
    ".env",
    ".env.*",
    "*.local.*",
)


class CoreUpdateError(RuntimeError):
    """Raised when a core update cannot be completed safely."""


class CoreUpdateManager:
    def __init__(
        self,
        *,
        base_dir: Path | str | None = None,
        user_data_dir: Path | str | None = None,
        index_url: str | None = None,
        timeout: int = 30,
        trust_roots_path: Path | None = None,
    ) -> None:
        self.base_dir = Path(base_dir) if base_dir is not None else BASE_DIR
        self.user_data_dir = Path(user_data_dir) if user_data_dir is not None else USER_DATA_DIR
        self.index_url = index_url or os.environ.get("RUMI_CORE_INDEX_URL") or DEFAULT_CORE_INDEX_URL
        self.timeout = timeout
        self.trust_roots_path = trust_roots_path
        self.update_state_dir = self.user_data_dir / "update_state" / "core"

    def check_core(self, channel: str = "stable") -> CoreUpdateResult:
        current = self.current_version()
        try:
            index = self.fetch_core_index(channel)
            latest = str(index.get("latest") or current)
            errors: list[str] = []
        except Exception as exc:
            latest = current
            errors = [str(exc)]
        return CoreUpdateResult(
            target="core",
            current_version=current,
            latest_version=latest,
            update_available=version_newer(latest, current),
            staged=self._has_staged(),
            errors=errors,
        )

    def stage_core(self, version: str | None = None, channel: str = "stable") -> dict[str, Any]:
        with self._core_lock():
            index = self.fetch_core_index(channel)
            selected = version or str(index.get("latest") or "")
            versions = index.get("versions")
            if not selected or not isinstance(versions, Mapping) or selected not in versions:
                raise CoreUpdateError("no core update found")
            entry = versions[selected]
            if not isinstance(entry, Mapping):
                raise CoreUpdateError("invalid core index entry")
            url = str(entry.get("url") or "")
            expected_sha = str(entry.get("sha256") or "")
            if not url or not expected_sha:
                raise CoreUpdateError("core index entry requires url and sha256")
            signature = signature_string_from_entry(entry)
            if not signature:
                raise CoreUpdateError("core index entry requires signature")
            stage_id = make_stage_id()
            stage_dir = self.update_state_dir / "staging" / stage_id
            bundle_path = stage_dir / f"rumiai-core-{selected}.zip"
            extracted = stage_dir / "extracted"
            stage_dir.mkdir(parents=True, exist_ok=False)
            download_to_file(url, bundle_path, timeout=self.timeout)
            actual_sha = verify_sha256(bundle_path, expected_sha)
            self._verify_bundle_signature(selected, actual_sha, signature)
            safe_extract_zip(bundle_path, extracted)
            self._validate_extracted_core(extracted, expected_version=selected)
            metadata = {
                "schema": "rumi.staged_core_update.v1",
                "stage_id": stage_id,
                "version": selected,
                "sha256": actual_sha,
                "signature": signature,
                "bundle_path": str(bundle_path),
                "staged_at": utc_now_iso(),
            }
            self._write_json_atomic(stage_dir / "stage.json", metadata)
            return metadata

    def apply_staged_core(self, stage_id: str) -> CoreUpdateResult:
        try:
            stage_dir = resolve_stage_dir(
                self.update_state_dir / "staging",
                stage_id,
                allowed_root=self.update_state_dir,
            )
        except ValueError as exc:
            raise CoreUpdateError(str(exc)) from exc
        stage_id = stage_dir.name
        if not (stage_dir / "stage.json").is_file():
            raise CoreUpdateError(f"unknown staged core update: {stage_id}")
        with self._core_lock():
            stage = json.loads((stage_dir / "stage.json").read_text(encoding="utf-8"))
            if stage.get("stage_id") != str(stage_id):
                raise CoreUpdateError("staged core metadata stage_id mismatch")
            extracted = stage_dir / "extracted"
            self._validate_extracted_core(extracted, expected_version=str(stage.get("version") or ""))
            current = self.current_version()
            latest = str(stage.get("version") or current)
            backup_dir = self._backup_core()
            applied = self._copy_core_overlay(extracted)
            self._write_json_atomic(
                self.update_state_dir / "last_core_update.json",
                {
                    "schema": "rumi.core_update_record.v1",
                    "previous_version": current,
                    "version": latest,
                    "backup_dir": str(backup_dir),
                    "applied_files": applied,
                    "applied_at": utc_now_iso(),
                },
            )
            return CoreUpdateResult(
                target="core",
                current_version=current,
                latest_version=latest,
                applied=True,
                staged=True,
                restart_required=True,
                backup_dir=str(backup_dir),
            )

    def apply_core(self, version: str | None = None, channel: str = "stable", force: bool = False) -> CoreUpdateResult:
        current = self.current_version()
        stage = self.stage_core(version=version, channel=channel)
        latest = str(stage.get("version") or current)
        if not force and not version_newer(latest, current):
            shutil.rmtree(Path(stage["bundle_path"]).parent, ignore_errors=True)
            raise CoreUpdateError(f"core is already up to date ({current} >= {latest})")
        return self.apply_staged_core(str(stage["stage_id"]))

    def current_version(self) -> str:
        return read_pyproject_version(self.base_dir / "pyproject.toml") or "0.0.0"

    def fetch_core_index(self, channel: str = "stable") -> dict[str, Any]:
        url = os.environ.get(f"RUMI_CORE_INDEX_{channel.upper()}_URL") or self.index_url
        if url.startswith("file://"):
            data = json.loads(Path(url.removeprefix("file://")).read_text(encoding="utf-8"))
        else:
            import urllib.request

            request = urllib.request.Request(url, headers={"User-Agent": "rumi-core-updater/1.0"})
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                data = json.loads(response.read().decode("utf-8"))
        if not isinstance(data, dict) or data.get("schema") != "rumi.core_index.v1":
            raise CoreUpdateError("invalid core index")
        try:
            verify_index_signatures(
                data,
                subject=f"core index {channel}",
                trust_roots=load_official_trust_roots(),
            )
        except Exception as exc:
            raise CoreUpdateError(str(exc)) from exc
        return data

    def _verify_bundle_signature(self, version: str, bundle_sha: str, signature: str) -> None:
        try:
            verify_signature(
                payload=core_bundle_signature_payload(version, bundle_sha),
                signature=signature,
                subject=f"core bundle {version}",
                trust_roots=load_official_trust_roots(),
            )
        except Exception as exc:
            raise CoreUpdateError(str(exc)) from exc

    def _validate_extracted_core(self, root: Path, *, expected_version: str | None = None) -> None:
        marker = root / "pyproject.toml"
        if not marker.is_file():
            raise CoreUpdateError("core bundle missing pyproject.toml")
        bundle_version = read_pyproject_version(marker)
        if expected_version and bundle_version != expected_version:
            raise CoreUpdateError(
                f"core bundle version mismatch: index={expected_version} bundle={bundle_version or 'unknown'}"
            )
        for path in root.rglob("*"):
            if path.is_symlink():
                raise CoreUpdateError(f"symlink rejected: {path.relative_to(root).as_posix()}")
            if not path.is_file():
                continue
            rel = path.relative_to(root).as_posix()
            if _path_matches_any(rel, CORE_PROTECTED_PATTERNS):
                raise CoreUpdateError(f"core update contains protected path: {rel}")

    def _copy_core_overlay(self, src: Path) -> list[str]:
        applied: list[str] = []
        for path in sorted(src.rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(src).as_posix()
            if _path_matches_any(rel, CORE_PROTECTED_PATTERNS):
                continue
            dest = self.base_dir / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, dest)
            applied.append(rel)
        return applied

    def _backup_core(self) -> Path:
        ts = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
        backup_dir = self.update_state_dir / "backups" / ts
        backup_dir.parent.mkdir(parents=True, exist_ok=True)
        backup_dir.mkdir(exist_ok=False)
        for rel_name in ("app.py", "core_runtime", "pyproject.toml", "requirements.txt"):
            src = self.base_dir / rel_name
            if src.is_dir():
                shutil.copytree(src, backup_dir / rel_name, symlinks=False)
            elif src.is_file():
                shutil.copy2(src, backup_dir / rel_name)
        return backup_dir

    def _has_staged(self) -> bool:
        root = self.update_state_dir / "staging"
        return root.is_dir() and any((child / "stage.json").is_file() for child in root.iterdir() if child.is_dir())

    @contextmanager
    def _core_lock(self) -> Iterator[None]:
        self.update_state_dir.mkdir(parents=True, exist_ok=True)
        lock = self.update_state_dir / ".core_update.lock"
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.close(fd)
        except FileExistsError as exc:
            raise CoreUpdateError("core update already in progress") from exc
        try:
            yield
        finally:
            try:
                lock.unlink()
            except OSError:
                pass

    @staticmethod
    def _write_json_atomic(path: Path, data: Mapping[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(tmp, path)


def _path_matches_any(rel: str, patterns: tuple[str, ...]) -> bool:
    for pattern in patterns:
        if fnmatch.fnmatch(rel, pattern):
            return True
        if pattern.endswith("/**") and rel == pattern[:-3]:
            return True
    return False
