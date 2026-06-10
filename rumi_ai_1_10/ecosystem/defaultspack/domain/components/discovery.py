from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from .manifest import DomainComponent
from .validation import ComponentManifestError, validate_component_manifest


@dataclass(frozen=True)
class ComponentDiscoveryIssue:
    path: str
    category: str
    message: str


@dataclass
class ComponentDiscoveryResult:
    components: list[DomainComponent] = field(default_factory=list)
    issues: list[ComponentDiscoveryIssue] = field(default_factory=list)


def _source_pack_id_for_domain_root(domain_root: Path) -> str:
    pack_root = domain_root.parent
    if domain_root.name != "domain":
        return ""
    fallback_pack_id = pack_root.name
    ecosystem = pack_root / "ecosystem.json"
    if ecosystem.is_file():
        try:
            raw = json.loads(ecosystem.read_text(encoding="utf-8"))
            declared_pack_id = str(raw.get("pack_id") or raw.get("id") or "").strip()
            if declared_pack_id == fallback_pack_id:
                return declared_pack_id
        except Exception:
            pass
    return fallback_pack_id


def discover_components(
    domain_roots: Path | str | Iterable[Path | str],
    *,
    categories: Iterable[str] | None = None,
    strict: bool = False,
) -> ComponentDiscoveryResult:
    if isinstance(domain_roots, (str, Path)):
        roots = [Path(domain_roots)]
    else:
        roots = [Path(root) for root in domain_roots]

    selected = {str(category).strip() for category in categories or [] if str(category).strip()}
    result = ComponentDiscoveryResult()
    seen: set[tuple[str, str]] = set()

    for root in roots:
        if not root.exists() or not root.is_dir():
            continue
        source_pack_id = _source_pack_id_for_domain_root(root)
        category_dirs = [root / category for category in sorted(selected)] if selected else sorted(
            path for path in root.iterdir() if path.is_dir()
        )
        for category_dir in category_dirs:
            category = category_dir.name
            if not category_dir.exists() or not category_dir.is_dir():
                continue
            for manifest_path in sorted(category_dir.glob("*/manifest.json")):
                try:
                    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
                    manifest = validate_component_manifest(raw, expected_category=category)
                except Exception as exc:
                    issue = ComponentDiscoveryIssue(
                        path=str(manifest_path),
                        category=category,
                        message=str(exc),
                    )
                    if strict:
                        raise ComponentManifestError(issue.message) from exc
                    result.issues.append(issue)
                    continue

                component_id = str(manifest["id"])
                dedupe_key = (category, component_id)
                if dedupe_key in seen:
                    issue = ComponentDiscoveryIssue(
                        path=str(manifest_path),
                        category=category,
                        message=f"duplicate component id: {component_id}",
                    )
                    if strict:
                        raise ComponentManifestError(issue.message)
                    result.issues.append(issue)
                    continue

                seen.add(dedupe_key)
                manifest["source_path"] = str(manifest_path)
                if source_pack_id:
                    # Treat the discovery root as the authoritative pack identity.
                    # Component manifests are data supplied by the pack itself and
                    # must not be able to spoof first-party trust by declaring a
                    # different source_pack_id.
                    manifest["source_pack_id"] = source_pack_id
                result.components.append(
                    DomainComponent(
                        category=category,
                        component_id=component_id,
                        manifest=manifest,
                        manifest_path=manifest_path,
                        source_pack_id=source_pack_id,
                    )
                )

    return result
