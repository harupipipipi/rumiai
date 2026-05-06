from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from .categories import DEFAULT_CATEGORY_SPECS, CategorySpec
from .manifest import ManifestValidationError, validate_manifest


@dataclass
class DiscoveryIssue:
    path: str
    category: str
    message: str


@dataclass
class DiscoveredExtension:
    category: str
    extension_id: str
    manifest: Dict[str, Any]
    path: str


@dataclass
class DiscoveryResult:
    extensions: List[DiscoveredExtension] = field(default_factory=list)
    issues: List[DiscoveryIssue] = field(default_factory=list)


def discover_extensions(
    root: Path,
    *,
    categories: Optional[Iterable[str]] = None,
    category_specs: Optional[Dict[str, CategorySpec]] = None,
    strict: bool = False,
) -> DiscoveryResult:
    specs = category_specs or DEFAULT_CATEGORY_SPECS
    selected = list(categories) if categories is not None else list(specs.keys())
    result = DiscoveryResult()
    seen = set()

    root_path = Path(root)
    if not root_path.exists():
        return result
    source_pack_id = ""
    try:
        source_pack_id = root_path.parent.name
    except Exception:
        source_pack_id = ""

    for category in selected:
        spec = specs.get(category)
        if spec is None:
            issue = DiscoveryIssue(
                path=str(root_path),
                category=category,
                message=f"unknown category: {category}",
            )
            if strict:
                raise ManifestValidationError(issue.message)
            result.issues.append(issue)
            continue

        for manifest_path in sorted(root_path.glob(spec.manifest_glob)):
            if not manifest_path.is_file():
                continue
            try:
                raw = json.loads(manifest_path.read_text(encoding="utf-8"))
                manifest = validate_manifest(raw, expected_category=category)
            except Exception as exc:
                issue = DiscoveryIssue(
                    path=str(manifest_path),
                    category=category,
                    message=str(exc),
                )
                if strict:
                    raise
                result.issues.append(issue)
                continue

            dedupe_key = (category, manifest["id"])
            if dedupe_key in seen:
                issue = DiscoveryIssue(
                    path=str(manifest_path),
                    category=category,
                    message=f"duplicate extension id: {manifest['id']}",
                )
                if strict:
                    raise ManifestValidationError(issue.message)
                result.issues.append(issue)
                continue

            seen.add(dedupe_key)
            manifest["source_path"] = str(manifest_path)
            if source_pack_id:
                manifest["source_pack_id"] = source_pack_id
            result.extensions.append(
                DiscoveredExtension(
                    category=category,
                    extension_id=manifest["id"],
                    manifest=manifest,
                    path=str(manifest_path),
                )
            )

    return result
