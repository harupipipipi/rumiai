"""Manifest-only verification for pack runtime and frontend artifacts."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping


def verify_declared_artifacts(
    pack_root: Path,
    ecosystem_manifest: Mapping[str, Any],
) -> tuple[bool, tuple[str, ...]]:
    """Verify a declared artifact index and every bound file hash."""
    metadata = ecosystem_manifest.get("metadata")
    metadata = metadata if isinstance(metadata, Mapping) else {}
    integrity = metadata.get("integrity")
    integrity = integrity if isinstance(integrity, Mapping) else {}
    relative = str(integrity.get("artifact_manifest") or "").strip()
    if not relative:
        return True, ()
    artifact_path = (pack_root / relative).resolve()
    try:
        artifact_path.relative_to(pack_root.resolve())
    except ValueError:
        return False, ("artifact manifest escapes pack root",)
    try:
        raw = artifact_path.read_bytes()
        payload = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        return False, (f"artifact manifest is unreadable: {type(exc).__name__}",)
    provenance = ecosystem_manifest.get("provenance")
    provenance = provenance if isinstance(provenance, Mapping) else {}
    expected_index_hash = str(provenance.get("content_hash") or "")
    actual_index_hash = "sha256:" + hashlib.sha256(raw).hexdigest()
    diagnostics: list[str] = []
    if actual_index_hash != expected_index_hash:
        diagnostics.append("artifact manifest hash does not match provenance")
    artifacts = payload.get("artifacts") if isinstance(payload, dict) else None
    if not isinstance(artifacts, list):
        diagnostics.append("artifact manifest has no artifacts list")
        return False, tuple(diagnostics)
    for item in artifacts:
        if not isinstance(item, dict):
            diagnostics.append("artifact entry is not an object")
            continue
        path_value = str(item.get("path") or "").strip()
        expected_hash = str(item.get("sha256") or "").strip()
        candidate = (pack_root / path_value).resolve()
        try:
            candidate.relative_to(pack_root.resolve())
        except ValueError:
            diagnostics.append(f"artifact escapes pack root: {path_value}")
            continue
        try:
            actual_hash = "sha256:" + hashlib.sha256(candidate.read_bytes()).hexdigest()
        except OSError:
            diagnostics.append(f"artifact is missing: {path_value}")
            continue
        if actual_hash != expected_hash:
            diagnostics.append(f"artifact hash mismatch: {path_value}")
    return not diagnostics, tuple(diagnostics)
