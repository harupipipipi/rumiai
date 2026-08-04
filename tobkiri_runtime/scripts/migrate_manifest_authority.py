"""Normalize Pack manifests and maintain deterministic authority projections."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend_core.ecosystem.spec.schema.validator import validate_ecosystem
from core_runtime.global_contracts.manifest import load_manifest
from core_runtime.manifest_projection import render_legacy_ecosystem

ECOSYSTEM = ROOT / "ecosystem"
CATALOG = ROOT / "schemas" / "manifest_authority.v1.json"


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _normalize_v3(manifest: dict[str, Any], pack_root: Path) -> dict[str, Any]:
    for provided in manifest.get("contracts", {}).get("provides", []):
        if provided.get("security") == "critical":
            provided["security"] = "restricted"
        lifecycle = provided.get("lifecycle")
        if isinstance(lifecycle, dict) and lifecycle.get("data_owner") is None:
            lifecycle.pop("data_owner", None)
    for required in manifest.get("contracts", {}).get("requires", []):
        if "version_range" not in required:
            required["version_range"] = required.pop("version", ">=1.0.0")
        else:
            required.pop("version", None)
        required.setdefault("optional", required.get("cardinality") == "optional")
        required["version_range"] = str(required["version_range"]).replace(
            ",", " "
        )
        required.pop("failure", None)
        for key in set(required) - {
            "id",
            "version_range",
            "cardinality",
            "optional",
            "instance_key",
        }:
            required.pop(key, None)
    migration = manifest.get("migration")
    if isinstance(migration, dict):
        projection = migration.get("compatibility_projection")
        if projection not in {"none", "legacy_to_v3_read_only"}:
            migration["compatibility_projection"] = "legacy_to_v3_read_only"
        aliases = migration.get("compatibility_aliases")
        if isinstance(aliases, list) and any(isinstance(item, str) for item in aliases):
            migration["compatibility_aliases"] = []
    for permission in manifest.get("permissions", []):
        if permission.get("access") == "publish":
            permission["access"] = "execute"
    normalized_resources = []
    for resource in manifest.get("resources", []):
        if not isinstance(resource, dict):
            continue
        path_value = str(resource.get("path") or "").strip()
        content_hash = str(resource.get("content_hash") or "").strip()
        if not content_hash and path_value:
            candidate = (pack_root / path_value).resolve()
            try:
                candidate.relative_to(pack_root.resolve())
                content_hash = _sha256(candidate)
            except (OSError, ValueError):
                content_hash = ""
        normalized_resources.append(
            {
                "id": str(resource.get("id") or path_value),
                "kind": str(resource.get("kind") or "file"),
                "content_hash": content_hash,
            }
        )
    manifest["resources"] = normalized_resources
    for entrypoint in manifest.get("entrypoints", []):
        module = str(entrypoint.get("module") or "").strip()
        if not module:
            continue
        candidate = ROOT.joinpath(*module.split(".")).with_suffix(".py")
        if candidate.is_file():
            entrypoint["artifact_hash"] = _sha256(candidate)
    return manifest


def _normalize_artifact_index(
    pack_root: Path,
    ecosystem: dict[str, Any],
    *,
    check: bool,
) -> None:
    metadata = ecosystem.get("metadata")
    metadata = metadata if isinstance(metadata, dict) else {}
    integrity = metadata.get("integrity")
    integrity = integrity if isinstance(integrity, dict) else {}
    relative = str(integrity.get("artifact_manifest") or "").strip()
    if not relative:
        return
    index_path = (pack_root / relative).resolve()
    index_path.relative_to(pack_root.resolve())
    payload = json.loads(index_path.read_text(encoding="utf-8"))
    artifacts = payload.get("artifacts")
    if not isinstance(artifacts, list):
        raise SystemExit(f"artifact index has no artifacts: {index_path}")
    for item in artifacts:
        if not isinstance(item, dict) or not item.get("path"):
            raise SystemExit(f"invalid artifact entry: {index_path}")
        candidate = (pack_root / str(item["path"])).resolve()
        candidate.relative_to(pack_root.resolve())
        item["sha256"] = _sha256(candidate)
    expected = json.dumps(
        payload, ensure_ascii=False, indent=2, sort_keys=True
    ) + "\n"
    if check:
        if index_path.read_text(encoding="utf-8") != expected:
            raise SystemExit(f"artifact index drift: {index_path}")
    else:
        index_path.write_text(expected, encoding="utf-8")
    provenance = ecosystem.get("provenance")
    if isinstance(provenance, dict):
        provenance["content_hash"] = "sha256:" + hashlib.sha256(
            expected.encode("utf-8")
        ).hexdigest()


def _schema_properties() -> set[str]:
    schema = json.loads(
        (
            ROOT
            / "backend_core"
            / "ecosystem"
            / "spec"
            / "schema"
            / "ecosystem.schema.json"
        ).read_text(encoding="utf-8")
    )
    return set(schema["properties"])


def _normalize_legacy(data: dict[str, Any]) -> dict[str, Any]:
    result = dict(data)
    metadata = result.get("metadata")
    metadata = dict(metadata) if isinstance(metadata, dict) else {}
    for generated_key in (
        "format",
        "generated",
        "generated_from",
        "manifest_authority",
        "read_only_projection",
    ):
        metadata.pop(generated_key, None)
    annotations = metadata.get("legacy_annotations")
    annotations = dict(annotations) if isinstance(annotations, dict) else {}
    depends_on = result.pop("depends_on", None)
    if "dependencies" not in result and isinstance(depends_on, list):
        result["dependencies"] = {
            str(item["pack_id"]): str(item.get("version") or ">=0.0.0")
            for item in depends_on
            if isinstance(item, dict) and item.get("pack_id")
        }
    elif depends_on is not None:
        annotations["depends_on"] = depends_on
    allowed = _schema_properties()
    for key in sorted(set(result) - allowed):
        annotations[key] = result.pop(key)
    vocabulary = result.get("vocabulary")
    if not isinstance(vocabulary, dict) or not vocabulary.get("types"):
        result["vocabulary"] = {"types": ["service"]}
    runtime = result.get("runtime")
    if isinstance(runtime, dict) and runtime.get("type") == "verified_hybrid_pack":
        annotations["runtime"] = result.pop("runtime")
    connectivity = result.get("connectivity")
    if isinstance(connectivity, dict):
        extras = set(connectivity) - {"requires", "provides"}
        if extras:
            annotations["connectivity"] = {
                key: connectivity.pop(key) for key in sorted(extras)
            }
    if annotations:
        metadata["legacy_annotations"] = annotations
    result["metadata"] = metadata
    return result


def migrate(*, check: bool) -> None:
    pack_roots = sorted(path.parent for path in ECOSYSTEM.glob("*/ecosystem.json"))
    authorities = {
        root.name: (
            "v3-authoritative"
            if (root / "rumi.pack.v3.json").is_file()
            else "legacy-authoritative"
        )
        for root in pack_roots
    }
    catalog_text = json.dumps(
        {"version": 1, "packs": authorities},
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ) + "\n"
    if check:
        if not CATALOG.is_file() or CATALOG.read_text(encoding="utf-8") != catalog_text:
            raise SystemExit("manifest authority catalog drift")
    else:
        CATALOG.write_text(catalog_text, encoding="utf-8")

    for root in pack_roots:
        ecosystem_path = root / "ecosystem.json"
        ecosystem = _normalize_legacy(
            json.loads(ecosystem_path.read_text(encoding="utf-8"))
        )
        _normalize_artifact_index(root, ecosystem, check=check)
        v3_path = root / "rumi.pack.v3.json"
        if v3_path.is_file():
            manifest = _normalize_v3(
                json.loads(v3_path.read_text(encoding="utf-8")), root
            )
            if isinstance(manifest.get("provenance"), dict) and isinstance(
                ecosystem.get("provenance"), dict
            ):
                manifest["provenance"]["content_hash"] = ecosystem[
                    "provenance"
                ]["content_hash"]
            extensions = manifest.setdefault("extensions", {})
            options = extensions.setdefault("rumi.legacy_projection", {})
            options["pack_id"] = root.name
            options["dependencies"] = ecosystem.get("dependencies", {})
            options["host_execution"] = bool(
                ecosystem.get("host_execution", False)
            )
            options["manifest"] = ecosystem
            v3_text = json.dumps(
                manifest, ensure_ascii=False, indent=2, sort_keys=True
            ) + "\n"
            if check:
                if v3_path.read_text(encoding="utf-8") != v3_text:
                    raise SystemExit(f"canonical v3 manifest drift: {v3_path}")
            else:
                v3_path.write_text(v3_text, encoding="utf-8")
            loaded = load_manifest(v3_path)
            if not loaded.ok:
                raise SystemExit(f"invalid canonical v3 manifest {v3_path}: {loaded.diagnostics}")
            ecosystem_text = render_legacy_ecosystem(loaded.value)
        else:
            ecosystem_text = json.dumps(
                ecosystem, ensure_ascii=False, indent=2, sort_keys=True
            ) + "\n"
        if check:
            if ecosystem_path.read_text(encoding="utf-8") != ecosystem_text:
                raise SystemExit(f"legacy projection drift: {ecosystem_path}")
        else:
            ecosystem_path.write_text(ecosystem_text, encoding="utf-8")
        errors = validate_ecosystem(
            json.loads(ecosystem_text), raise_on_error=False
        )
        if errors:
            raise SystemExit(f"invalid legacy projection {ecosystem_path}: {errors}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    migrate(check=args.check)


if __name__ == "__main__":
    main()
