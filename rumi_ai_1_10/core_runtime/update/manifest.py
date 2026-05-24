"""Validation for .rumi-pack bundle contents."""

from __future__ import annotations

import fnmatch
import json
import os
from pathlib import Path
from typing import Any, Mapping

from .download import DownloadError, sha256_file
from .versioning import is_valid_semver, satisfies_constraint

PACK_SCHEMA = "rumi.pack.v1"
MANIFEST_SCHEMA = "rumi.pack_manifest.v1"
DEFAULT_PROTECTED_PATTERNS = (
    "user_data",
    "user_data/**",
    "state",
    "state/**",
    "secrets",
    "secrets/**",
    ".env",
    "*.local.*",
)


class ManifestError(RuntimeError):
    """Raised when a pack bundle manifest is invalid."""


def read_json_object(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise ManifestError(f"invalid JSON: {path}") from exc
    if not isinstance(data, dict):
        raise ManifestError(f"expected JSON object: {path}")
    return data


def validate_extracted_pack(
    root: Path,
    *,
    target_pack_id: str,
    core_version: str,
    viewer_version: str,
    require_stable_semver: bool = True,
) -> dict[str, Any]:
    pack_manifest_path = root / "rumi-pack.json"
    ecosystem_path = root / "ecosystem.json"
    if not pack_manifest_path.is_file():
        raise ManifestError("missing rumi-pack.json")
    if not ecosystem_path.is_file():
        raise ManifestError("missing ecosystem.json")

    manifest = read_json_object(pack_manifest_path)
    ecosystem = read_json_object(ecosystem_path)
    if manifest.get("schema") != PACK_SCHEMA:
        raise ManifestError("unsupported rumi-pack schema")
    pack_id = str(manifest.get("pack_id") or "")
    ecosystem_pack_id = str(ecosystem.get("pack_id") or "")
    if pack_id != target_pack_id or ecosystem_pack_id != target_pack_id:
        raise ManifestError(
            f"pack_id mismatch: target={target_pack_id} rumi-pack={pack_id} ecosystem={ecosystem_pack_id}"
        )
    version = str(manifest.get("version") or ecosystem.get("version") or "")
    if not version:
        raise ManifestError("missing pack version")
    if require_stable_semver and str(manifest.get("channel") or "stable") == "stable" and not is_valid_semver(version):
        raise ManifestError(f"invalid stable semver: {version}")
    if str(ecosystem.get("version") or version) != version:
        raise ManifestError("rumi-pack.json and ecosystem.json versions diverge")

    _validate_entrypoint(manifest)
    _validate_compatibility(manifest, core_version=core_version, viewer_version=viewer_version)
    _validate_no_symlinks(root)
    _validate_protected_paths(root, manifest)
    validate_file_manifest(root)
    return manifest


def validate_file_manifest(root: Path) -> None:
    manifest_json = root / "manifest.json"
    manifest_sha = root / "manifest.sha256"
    if manifest_json.is_file():
        data = read_json_object(manifest_json)
        files = data.get("files", data)
        if not isinstance(files, Mapping):
            raise ManifestError("manifest.json files must be an object")
        expected = {str(k): str(v) for k, v in files.items() if k not in {"schema"}}
    elif manifest_sha.is_file():
        expected = _read_manifest_sha256(manifest_sha)
    else:
        raise ManifestError("missing checksum manifest")

    actual_files = {
        path.relative_to(root).as_posix(): path
        for path in root.rglob("*")
        if path.is_file()
        and not path.is_symlink()
        and path.name not in {"manifest.json", "manifest.sha256", "signature", "signature.sig"}
        and path.suffix != ".sig"
    }
    if not expected:
        raise ManifestError("checksum manifest is empty")
    for rel, digest in expected.items():
        if rel not in actual_files:
            raise ManifestError(f"checksum references missing file: {rel}")
        actual = sha256_file(actual_files[rel])
        if actual.lower() != digest.lower():
            raise ManifestError(f"checksum mismatch for {rel}")
    missing = sorted(set(actual_files) - set(expected))
    if missing:
        raise ManifestError(f"checksum manifest missing file: {missing[0]}")


def _read_manifest_sha256(path: Path) -> dict[str, str]:
    entries: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        parts = line.split(None, 1)
        if len(parts) != 2:
            raise ManifestError("invalid manifest.sha256 line")
        digest, rel = parts
        rel = rel.strip().lstrip("*")
        if not _safe_rel(rel):
            raise ManifestError(f"unsafe checksum path: {rel}")
        entries[rel] = digest
    return entries


def _validate_entrypoint(manifest: Mapping[str, Any]) -> None:
    entrypoints = manifest.get("entrypoints")
    if not isinstance(entrypoints, Mapping) or entrypoints.get("ecosystem") != "ecosystem.json":
        raise ManifestError("entrypoints.ecosystem must be ecosystem.json")


def _validate_compatibility(manifest: Mapping[str, Any], *, core_version: str, viewer_version: str) -> None:
    compatibility = manifest.get("compatibility")
    if not isinstance(compatibility, Mapping):
        return
    min_core = compatibility.get("min_core_version")
    max_core = compatibility.get("max_core_version")
    min_viewer = compatibility.get("min_viewer_version")
    if min_core and not satisfies_constraint(core_version, f">={min_core}"):
        raise ManifestError(f"incompatible core version: requires >= {min_core}")
    if max_core and not satisfies_constraint(core_version, str(max_core)):
        raise ManifestError(f"incompatible core version: requires {max_core}")
    if min_viewer and not satisfies_constraint(viewer_version, f">={min_viewer}"):
        raise ManifestError(f"incompatible viewer version: requires >= {min_viewer}")


def _validate_no_symlinks(root: Path) -> None:
    for path in root.rglob("*"):
        if path.is_symlink():
            raise DownloadError(f"symlink in pack rejected: {path.relative_to(root).as_posix()}")


def _validate_protected_paths(root: Path, manifest: Mapping[str, Any]) -> None:
    protected = manifest.get("protected_paths")
    additions = protected if isinstance(protected, list) else []
    patterns = list(dict.fromkeys([*DEFAULT_PROTECTED_PATTERNS, *(str(item) for item in additions)]))
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        if rel in {"rumi-pack.json", "ecosystem.json", "manifest.json", "manifest.sha256", "signature", "signature.sig"}:
            continue
        if path_matches_any(rel, patterns):
            raise ManifestError(f"bundle contains protected path: {rel}")


def path_matches_any(rel: str, patterns: list[str] | tuple[str, ...]) -> bool:
    for pattern in patterns:
        if fnmatch.fnmatch(rel, pattern):
            return True
        if pattern.endswith("/**") and rel == pattern[:-3]:
            return True
    return False


def _safe_rel(rel: str) -> bool:
    rel_path = Path(rel)
    return not rel_path.is_absolute() and ".." not in rel_path.parts and "\x00" not in rel


def copy_validated_tree(src: Path, dst: Path) -> list[str]:
    applied: list[str] = []
    for path in sorted(src.rglob("*")):
        rel = path.relative_to(src)
        if path.is_dir():
            (dst / rel).mkdir(parents=True, exist_ok=True)
            continue
        if path.is_symlink():
            raise ManifestError(f"symlink rejected during install: {rel.as_posix()}")
        target = dst / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(path.read_bytes())
        try:
            os.utime(target, ns=(path.stat().st_atime_ns, path.stat().st_mtime_ns))
        except OSError:
            pass
        applied.append(rel.as_posix())
    return applied
