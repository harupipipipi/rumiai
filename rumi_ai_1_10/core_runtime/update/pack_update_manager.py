"""Managed pack update manager."""

from __future__ import annotations

import json
import os
import re
import shutil
import time
import uuid
import zipfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Mapping

from ..pack_seed import read_current_pointer, utc_now_iso, write_current_pointer_atomic
from ..paths import BASE_DIR, MANAGED_PACKS_DIR, PACK_STATE_DIR, find_ecosystem_json
from .download import download_to_file, safe_extract_zip, verify_sha256
from .manifest import (
    DEFAULT_PROTECTED_PATTERNS,
    copy_validated_tree,
    path_matches_any,
    read_json_object,
    validate_extracted_pack,
)
from .models import AutoUpdateRunResult, PackUpdateCheck, PackUpdateResult, StagedPackUpdate
from .rollback import rollback_available, rollback_pack_version
from .stage_ids import make_stage_id, resolve_stage_dir, validate_stage_id
from .trust import (
    load_trust_roots,
    load_official_trust_roots,
    pack_bundle_signature_payload,
    signature_string_from_entry,
    verify_index_signatures,
    verify_signature,
)
from .versioning import read_pyproject_version, sort_versions, version_newer

DEFAULT_PACK_INDEX_URL = (
    "https://github.com/harupipipipi/rumiai/releases/latest/download/pack-index.stable.json"
)
AUTO_UPDATE_INTERVAL_HOURS = 24
OFFICIAL_PACK_IDS = frozenset({"defaultspack"})


class PackUpdateError(RuntimeError):
    """Raised when a pack update cannot be completed safely."""


_PACK_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


def validate_pack_id(pack_id: str) -> str:
    normalized = str(pack_id or "").strip()
    if (
        not normalized
        or not _PACK_ID_RE.fullmatch(normalized)
        or normalized in {".", ".."}
        or "\x00" in normalized
        or "/" in normalized
        or "\\" in normalized
        or ".." in Path(normalized).parts
    ):
        raise PackUpdateError(f"invalid pack_id: {pack_id!r}")
    return normalized


def _validate_version_path_part(version: str) -> None:
    if "/" in version or "\\" in version or "\x00" in version or ".." in Path(version).parts:
        raise PackUpdateError(f"unsafe version: {version}")


class PackUpdateManager:
    def __init__(
        self,
        *,
        managed_dir: Path | str | None = None,
        pack_state_dir: Path | str | None = None,
        index_url: str | None = None,
        timeout: int = 30,
        core_version: str | None = None,
        viewer_version: str | None = None,
        trust_roots_path: Path | None = None,
    ) -> None:
        self.managed_dir = Path(managed_dir) if managed_dir is not None else MANAGED_PACKS_DIR
        self.pack_state_dir = Path(pack_state_dir) if pack_state_dir is not None else PACK_STATE_DIR
        self.index_url = index_url or os.environ.get("RUMI_PACK_INDEX_URL") or DEFAULT_PACK_INDEX_URL
        self.timeout = timeout
        self.core_version = core_version or read_pyproject_version(BASE_DIR / "pyproject.toml") or "1.10.0"
        self.viewer_version = viewer_version or os.environ.get("RUMI_VIEWER_VERSION", "0.1.0")
        self.trust_roots_path = trust_roots_path

    def check_pack(self, pack_id: str, channel: str = "stable") -> PackUpdateCheck:
        try:
            pack_id = validate_pack_id(pack_id)
        except PackUpdateError as exc:
            return PackUpdateCheck(
                target="pack:invalid",
                pack_id="invalid",
                current_version="0.0.0",
                latest_version="0.0.0",
                update_available=False,
                channel=channel,
                errors=[str(exc)],
            )
        current = self.current_version(pack_id)
        try:
            index = self.fetch_pack_index(channel)
            self._verify_pack_index_signature(index, pack_id, channel)
            version, _entry = self._select_latest(index, pack_id)
            latest = version or current
            errors: list[str] = []
        except Exception as exc:
            latest = current
            errors = [str(exc)]
        return PackUpdateCheck(
            target=f"pack:{pack_id}",
            pack_id=pack_id,
            current_version=current,
            latest_version=latest,
            update_available=version_newer(latest, current),
            channel=channel,
            staged=self._has_staged(pack_id),
            rollback_available=rollback_available(pack_id, self.managed_dir),
            errors=errors,
        )

    def check_all(self, channel: str = "stable") -> list[PackUpdateCheck]:
        try:
            index = self.fetch_pack_index(channel)
            packs = index.get("packs")
            if not isinstance(packs, Mapping):
                return []
            checks: list[PackUpdateCheck] = []
            for pack_id in sorted(packs):
                checks.append(self.check_pack(str(pack_id), channel=channel))
            return checks
        except Exception:
            return [self.check_pack("defaultspack", channel=channel)]

    def stage_pack(
        self,
        pack_id: str,
        version: str | None = None,
        channel: str = "stable",
    ) -> StagedPackUpdate:
        pack_id = validate_pack_id(pack_id)
        with self._pack_lock(pack_id):
            index = self.fetch_pack_index(channel)
            self._verify_pack_index_signature(index, pack_id, channel)
            selected_version, entry = self._select_latest(index, pack_id, version)
            if not selected_version or not entry:
                raise PackUpdateError(f"no update found for {pack_id}")
            url = str(entry.get("url") or "")
            expected_sha = str(entry.get("sha256") or "")
            signature = signature_string_from_entry(entry)
            if not url or not expected_sha:
                raise PackUpdateError("pack index entry requires url and sha256")

            stage_id = make_stage_id()
            stage_dir = self._staging_root(pack_id) / stage_id
            bundle_path = stage_dir / f"{pack_id}-{selected_version}.rumi-pack"
            extracted = stage_dir / "extracted"
            stage_dir.mkdir(parents=True, exist_ok=False)
            download_to_file(url, bundle_path, timeout=self.timeout)
            actual_sha = verify_sha256(bundle_path, expected_sha)
            self._verify_bundle_signature(bundle_path, actual_sha, signature, pack_id)
            safe_extract_zip(bundle_path, extracted)
            manifest = validate_extracted_pack(
                extracted,
                target_pack_id=pack_id,
                core_version=self.core_version,
                viewer_version=self.viewer_version,
            )
            if str(manifest.get("version")) != selected_version:
                raise PackUpdateError("bundle version does not match pack index")
            metadata = {
                "schema": "rumi.staged_pack_update.v1",
                "stage_id": stage_id,
                "pack_id": pack_id,
                "version": selected_version,
                "bundle_path": str(bundle_path),
                "sha256": actual_sha,
                "signature": signature,
                "staged_at": utc_now_iso(),
            }
            self._write_json_atomic(stage_dir / "stage.json", metadata)
            return StagedPackUpdate(
                stage_id=stage_id,
                pack_id=pack_id,
                version=selected_version,
                staging_dir=str(stage_dir),
                bundle_path=str(bundle_path),
                sha256=actual_sha,
            )

    def apply_staged_pack(self, stage_id: str, *, expected_pack_id: str | None = None) -> PackUpdateResult:
        try:
            stage_id = validate_stage_id(stage_id)
        except ValueError as exc:
            raise PackUpdateError(str(exc)) from exc
        expected_pack_id = validate_pack_id(expected_pack_id) if expected_pack_id is not None else None
        for pack_root in self.managed_dir.iterdir() if self.managed_dir.is_dir() else []:
            if not pack_root.is_dir() or pack_root.is_symlink():
                continue
            if expected_pack_id is not None and pack_root.name != expected_pack_id:
                continue
            try:
                stage_dir = resolve_stage_dir(
                    pack_root / "staging",
                    stage_id,
                    allowed_root=self.managed_dir / pack_root.name,
                )
            except ValueError as exc:
                raise PackUpdateError(str(exc)) from exc
            if (stage_dir / "stage.json").is_file():
                data = read_json_object(stage_dir / "stage.json")
                pack_id = validate_pack_id(str(data.get("pack_id") or ""))
                if data.get("stage_id") != stage_id:
                    raise PackUpdateError("staged update metadata stage_id mismatch")
                if pack_id != pack_root.name:
                    raise PackUpdateError("staged update metadata pack_id mismatch")
                if expected_pack_id is not None and pack_id != expected_pack_id:
                    raise PackUpdateError("staged update target pack_id mismatch")
                return self._activate_stage(pack_id, stage_dir)
        raise PackUpdateError(f"unknown staged update: {stage_id}")

    def apply_pack(
        self,
        pack_id: str,
        version: str | None = None,
        channel: str = "stable",
        force: bool = False,
    ) -> PackUpdateResult:
        pack_id = validate_pack_id(pack_id)
        current = self.current_version(pack_id)
        staged = self.stage_pack(pack_id, version=version, channel=channel)
        if not force and not version_newer(staged.version, current):
            shutil.rmtree(staged.staging_dir, ignore_errors=True)
            raise PackUpdateError(f"{pack_id} is already up to date ({current} >= {staged.version})")
        if force:
            return self._activate_stage(pack_id, Path(staged.staging_dir), replace_existing=True)
        return self.apply_staged_pack(staged.stage_id)

    def rollback_pack(self, pack_id: str, version: str | None = None):
        pack_id = validate_pack_id(pack_id)
        if version is not None:
            _validate_version_path_part(str(version))
        with self._pack_lock(pack_id):
            return rollback_pack_version(pack_id, version, self.managed_dir)

    def run_auto_updates_once(self, force: bool = False) -> AutoUpdateRunResult:
        settings = self.read_update_preferences()
        official_enabled = settings["auto_update"].get("official_packs") is True
        third_party_enabled = settings["auto_update"].get("third_party_packs") is True
        if not official_enabled and not third_party_enabled:
            return AutoUpdateRunResult([], False, settings.get("last_checked_at"), list(settings.get("last_results") or []), "disabled")
        if not force and not self._auto_update_due(settings):
            enabled = [name for name, enabled in (("official_packs", official_enabled), ("third_party_packs", third_party_enabled)) if enabled]
            return AutoUpdateRunResult(enabled, False, settings.get("last_checked_at"), list(settings.get("last_results") or []), "interval")

        results: list[dict[str, Any]] = []
        checked_at = utc_now_iso()
        for check in self.check_all(channel=str(settings["channels"].get("packs", "stable"))):
            if check.pack_id not in OFFICIAL_PACK_IDS:
                results.append({
                    **check.to_dict(),
                    "status": "manual_required" if check.update_available or third_party_enabled else "skipped",
                    "error": "Third-party pack auto-updates are not supported.",
                })
                continue
            if not official_enabled:
                results.append({**check.to_dict(), "status": "skipped"})
                continue
            if not check.update_available:
                results.append({**check.to_dict(), "status": "up_to_date"})
                continue
            try:
                result = self.apply_pack(check.pack_id)
                results.append({**result.to_dict(), "status": "applied"})
            except Exception as exc:
                results.append({**check.to_dict(), "status": "error", "error": str(exc)})
        updated = {**settings, "last_checked_at": checked_at, "last_results": results}
        self.write_update_preferences(updated)
        enabled = [name for name, enabled in (("official_packs", official_enabled), ("third_party_packs", third_party_enabled)) if enabled]
        return AutoUpdateRunResult(enabled, True, checked_at, results)

    def install_extracted_pack(
        self,
        pack_id: str,
        source_dir: Path,
        *,
        version: str | None = None,
        source_label: str = "manual",
        source_metadata: Mapping[str, Any] | None = None,
        force: bool = False,
    ) -> PackUpdateResult:
        pack_id = validate_pack_id(pack_id)
        with self._pack_lock(pack_id):
            eco, pack_subdir = find_ecosystem_json(source_dir)
            if eco is None or pack_subdir is None:
                raise PackUpdateError("extracted pack is missing ecosystem.json")
            ecosystem = read_json_object(eco)
            if ecosystem.get("pack_id") != pack_id:
                raise PackUpdateError("pack_id mismatch")
            latest = version or str(ecosystem.get("version") or "0.0.0")
            current = self.current_version(pack_id)
            if not force and not version_newer(latest, current):
                raise PackUpdateError(f"{pack_id} is already up to date ({current} >= {latest})")
            tmp_dir, version_dir = self._prepare_version_dir(pack_id, latest, replace_existing=force)
            applied = _copy_pack_tree_for_install(pack_subdir, tmp_dir)
            backup_dir = self._commit_version_dir(pack_id, latest, tmp_dir, version_dir, replace_existing=force)
            self._record_install(pack_id, latest, source_label, current, source_metadata=source_metadata)
            write_current_pointer_atomic(pack_id, latest, Path("versions") / latest, self.managed_dir)
            return PackUpdateResult(
                target=f"pack:{pack_id}",
                pack_id=pack_id,
                current_version=current,
                latest_version=latest,
                applied=True,
                staged=False,
                applied_files=applied,
                backup_dir=backup_dir,
            )

    def current_version(self, pack_id: str) -> str:
        pack_id = validate_pack_id(pack_id)
        current = read_current_pointer(pack_id, self.managed_dir)
        if current and current.get("version"):
            return str(current["version"])
        direct_eco = self.managed_dir / pack_id / "ecosystem.json"
        if direct_eco.is_file():
            try:
                return str(read_json_object(direct_eco).get("version") or "0.0.0")
            except Exception:
                return "0.0.0"
        return "0.0.0"

    def fetch_pack_index(self, channel: str = "stable") -> dict[str, Any]:
        if channel != "stable":
            url = os.environ.get(f"RUMI_PACK_INDEX_{channel.upper()}_URL") or self.index_url
        else:
            url = self.index_url
        if url.startswith("file://"):
            data = json.loads(Path(url.removeprefix("file://")).read_text(encoding="utf-8"))
        else:
            import urllib.request

            request = urllib.request.Request(url, headers={"User-Agent": "rumi-pack-updater/1.0"})
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                data = json.loads(response.read().decode("utf-8"))
        if not isinstance(data, dict) or data.get("schema") != "rumi.pack_index.v1":
            raise PackUpdateError("invalid pack index")
        return data

    def read_update_preferences(self) -> dict[str, Any]:
        path = self.pack_state_dir / "update_preferences.json"
        data: Mapping[str, Any] = {}
        if path.is_file():
            try:
                loaded = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(loaded, Mapping):
                    data = loaded
            except (OSError, json.JSONDecodeError):
                data = {}
        return normalize_update_preferences(data)

    def write_update_preferences(self, settings: Mapping[str, Any]) -> dict[str, Any]:
        normalized = normalize_update_preferences(settings)
        normalized["updated_at"] = utc_now_iso()
        self._write_json_atomic(self.pack_state_dir / "update_preferences.json", normalized)
        return self.read_update_preferences()

    def _activate_stage(self, pack_id: str, stage_dir: Path, *, replace_existing: bool = False) -> PackUpdateResult:
        pack_id = validate_pack_id(pack_id)
        with self._pack_lock(pack_id):
            stage = read_json_object(stage_dir / "stage.json")
            version = str(stage["version"])
            extracted = stage_dir / "extracted"
            validate_extracted_pack(
                extracted,
                target_pack_id=pack_id,
                core_version=self.core_version,
                viewer_version=self.viewer_version,
            )
            current = self.current_version(pack_id)
            tmp_dir, version_dir = self._prepare_version_dir(pack_id, version, replace_existing=replace_existing)
            applied = copy_validated_tree(extracted, tmp_dir)
            backup_dir = self._commit_version_dir(pack_id, version, tmp_dir, version_dir, replace_existing=replace_existing)
            signature = str(stage.get("signature") or "")
            self._record_install(
                pack_id,
                version,
                "rumi-pack",
                current,
                source_metadata={
                    "sha256": stage.get("sha256"),
                    "signature": signature,
                    "signature_scheme": _signature_scheme(signature),
                    "key_id": _signature_key_id(signature),
                },
            )
            write_current_pointer_atomic(pack_id, version, Path("versions") / version, self.managed_dir)
            return PackUpdateResult(
                target=f"pack:{pack_id}",
                pack_id=pack_id,
                current_version=current,
                latest_version=version,
                applied=True,
                staged=True,
                applied_files=applied,
                backup_dir=backup_dir,
            )

    def _prepare_version_dir(self, pack_id: str, version: str, *, replace_existing: bool = False) -> tuple[Path, Path]:
        pack_id = validate_pack_id(pack_id)
        _validate_version_path_part(version)
        version_dir = self.managed_dir / pack_id / "versions" / version
        if version_dir.exists() and not replace_existing:
            raise PackUpdateError(f"managed pack version already exists: {pack_id} {version}")
        tmp_dir = version_dir.with_name(f".{version}.tmp-{uuid.uuid4().hex[:8]}")
        tmp_dir.mkdir(parents=True, exist_ok=False)
        return tmp_dir, version_dir

    def _commit_version_dir(
        self,
        pack_id: str,
        version: str,
        tmp_dir: Path,
        version_dir: Path,
        *,
        replace_existing: bool = False,
    ) -> str | None:
        backup_dir: Path | None = None
        if version_dir.exists():
            if not replace_existing:
                raise PackUpdateError(f"managed pack version already exists: {pack_id} {version}")
            backup_dir = (
                self.managed_dir
                / pack_id
                / "backups"
                / "replaced_versions"
                / f"{version}-{int(time.time())}-{uuid.uuid4().hex[:8]}"
            )
            backup_dir.parent.mkdir(parents=True, exist_ok=True)
            version_dir.rename(backup_dir)
        try:
            tmp_dir.rename(version_dir)
        except Exception:
            if backup_dir is not None and backup_dir.exists() and not version_dir.exists():
                backup_dir.rename(version_dir)
            raise
        return str(backup_dir) if backup_dir is not None else None

    def _record_install(
        self,
        pack_id: str,
        version: str,
        source: str,
        previous_version: str,
        *,
        source_metadata: Mapping[str, Any] | None = None,
    ) -> None:
        pack_id = validate_pack_id(pack_id)
        record: dict[str, Any] = {
            "schema": "rumi.pack_install_record.v1",
            "pack_id": pack_id,
            "version": version,
            "source": source,
            "previous_version": previous_version,
            "installed_at": utc_now_iso(),
        }
        if source_metadata:
            for key, value in source_metadata.items():
                if isinstance(key, str) and (isinstance(value, (str, int, float, bool)) or value is None):
                    record[key] = value
        install_dir = self.managed_dir / pack_id
        self._write_json_atomic(install_dir / "install_record.json", record)
        history = install_dir / "backups" / "install_history.jsonl"
        history.parent.mkdir(parents=True, exist_ok=True)
        with history.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")

    def _verify_bundle_signature(self, bundle_path: Path, bundle_sha: str, signature: str | None, pack_id: str) -> None:
        if signature is None:
            signature = _signature_from_bundle(bundle_path)
        roots = self._pack_trust_roots(pack_id)
        verify_signature(
            payload=pack_bundle_signature_payload(bundle_sha),
            signature=signature,
            subject=f"pack {pack_id}",
            trust_roots=roots,
        )

    def _verify_pack_index_signature(self, index: Mapping[str, Any], pack_id: str, channel: str) -> None:
        try:
            verify_index_signatures(
                index,
                subject=f"pack index {channel} for {pack_id}",
                trust_roots=self._pack_trust_roots(pack_id),
            )
        except Exception as exc:
            raise PackUpdateError(str(exc)) from exc

    def _select_latest(
        self,
        index: Mapping[str, Any],
        pack_id: str,
        version: str | None = None,
    ) -> tuple[str | None, Mapping[str, Any] | None]:
        pack_id = validate_pack_id(pack_id)
        packs = index.get("packs")
        if not isinstance(packs, Mapping) or pack_id not in packs:
            return None, None
        pack_entry = packs[pack_id]
        if not isinstance(pack_entry, Mapping):
            return None, None
        versions = pack_entry.get("versions")
        if not isinstance(versions, Mapping):
            return None, None
        selected = version or str(pack_entry.get("latest") or "")
        if not selected:
            selected = sort_versions([str(v) for v in versions.keys()])[-1]
        entry = versions.get(selected)
        if not isinstance(entry, Mapping):
            return None, None
        min_core = entry.get("min_core_version")
        max_core = entry.get("max_core_version")
        from .versioning import satisfies_constraint

        if min_core and not satisfies_constraint(self.core_version, f">={min_core}"):
            return None, None
        if max_core and not satisfies_constraint(self.core_version, str(max_core)):
            return None, None
        return selected, entry

    def _pack_trust_roots(self, pack_id: str) -> dict[str, Any]:
        if pack_id in OFFICIAL_PACK_IDS:
            return load_official_trust_roots()
        roots = load_trust_roots(self.trust_roots_path)
        pack_scopes = roots.get("pack_keys")
        if isinstance(pack_scopes, Mapping):
            scoped_keys = pack_scopes.get(pack_id)
            if isinstance(scoped_keys, Mapping):
                public_keys = roots.setdefault("ed25519_public_keys", {})
                if isinstance(public_keys, dict):
                    for key_id, value in scoped_keys.items():
                        if isinstance(key_id, str) and isinstance(value, str):
                            public_keys[key_id] = value
        return roots

    def _staging_root(self, pack_id: str) -> Path:
        pack_id = validate_pack_id(pack_id)
        return self.managed_dir / pack_id / "staging"

    def _has_staged(self, pack_id: str) -> bool:
        pack_id = validate_pack_id(pack_id)
        root = self._staging_root(pack_id)
        return root.is_dir() and any((child / "stage.json").is_file() for child in root.iterdir() if child.is_dir())

    @contextmanager
    def _pack_lock(self, pack_id: str) -> Iterator[None]:
        pack_id = validate_pack_id(pack_id)
        lock_dir = self.managed_dir / pack_id
        lock_dir.mkdir(parents=True, exist_ok=True)
        lock_path = lock_dir / ".update.lock"
        try:
            fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.close(fd)
        except FileExistsError as exc:
            raise PackUpdateError(f"update already in progress for {pack_id}") from exc
        try:
            yield
        finally:
            try:
                lock_path.unlink()
            except OSError:
                pass

    @staticmethod
    def _write_json_atomic(path: Path, data: Mapping[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(tmp, path)

    @staticmethod
    def _auto_update_due(settings: Mapping[str, Any]) -> bool:
        last_checked = settings.get("last_checked_at")
        if not isinstance(last_checked, str) or not last_checked:
            return True
        from datetime import datetime, timezone

        try:
            dt = datetime.fromisoformat(last_checked.replace("Z", "+00:00"))
        except ValueError:
            return True
        interval = _normalize_check_interval_hours(settings.get("check_interval_hours"))
        return (datetime.now(timezone.utc) - dt).total_seconds() >= interval * 3600


def normalize_update_preferences(data: Mapping[str, Any]) -> dict[str, Any]:
    raw_auto = data.get("auto_update")
    if not isinstance(raw_auto, Mapping):
        raw_auto = {}
    raw_channels = data.get("channels")
    if not isinstance(raw_channels, Mapping):
        raw_channels = {}
    last_results = data.get("last_results")
    if not isinstance(last_results, list):
        last_results = []
    return {
        "auto_update": {
            "viewer": bool(raw_auto.get("viewer", False)),
            "core": bool(raw_auto.get("core", raw_auto.get("rumiai", False))),
            "official_packs": bool(raw_auto.get("official_packs", raw_auto.get("defaultspack", False))),
            "third_party_packs": bool(raw_auto.get("third_party_packs", False)),
        },
        "channels": {
            "viewer": str(raw_channels.get("viewer", "stable")),
            "core": str(raw_channels.get("core", "stable")),
            "packs": str(raw_channels.get("packs", "stable")),
        },
        "check_interval_hours": _normalize_check_interval_hours(data.get("check_interval_hours")),
        "last_checked_at": data.get("last_checked_at") if isinstance(data.get("last_checked_at"), str) else None,
        "last_results": last_results,
        "updated_at": data.get("updated_at") if isinstance(data.get("updated_at"), str) else None,
    }


def _signature_from_bundle(bundle_path: Path) -> str | None:
    try:
        with zipfile.ZipFile(bundle_path, "r") as zf:
            for name in ("signature", "signature.sig"):
                try:
                    return zf.read(name).decode("utf-8").strip()
                except KeyError:
                    continue
    except zipfile.BadZipFile:
        return None
    return None


def _signature_scheme(signature: str) -> str:
    parts = str(signature or "").split(":", 2)
    return parts[0] if len(parts) == 3 else ""


def _signature_key_id(signature: str) -> str:
    parts = str(signature or "").split(":", 2)
    return parts[1] if len(parts) == 3 else ""


def _normalize_check_interval_hours(value: Any) -> int:
    try:
        interval = int(value)
    except (TypeError, ValueError):
        interval = AUTO_UPDATE_INTERVAL_HOURS
    return max(1, min(interval, 24 * 30))


def _copy_pack_tree_for_install(src: Path, dst: Path) -> list[str]:
    applied: list[str] = []
    for path in sorted(src.rglob("*")):
        rel = path.relative_to(src)
        rel_posix = rel.as_posix()
        if path_matches_any(rel_posix, DEFAULT_PROTECTED_PATTERNS):
            continue
        if path.is_dir():
            (dst / rel).mkdir(parents=True, exist_ok=True)
        elif path.is_file() and not path.is_symlink():
            target = dst / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
            applied.append(rel_posix)
    return applied
