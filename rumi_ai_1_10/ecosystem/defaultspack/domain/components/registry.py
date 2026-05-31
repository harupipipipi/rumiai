from __future__ import annotations

import os
import threading
from pathlib import Path
from typing import Iterable

from .discovery import ComponentDiscoveryIssue, discover_components
from .manifest import DomainComponent

_LOCK = threading.Lock()
_REGISTRY: "DomainComponentRegistry | None" = None
_EXTRA_DOMAIN_ROOTS_ENV = "RUMI_DEFAULTSPACK_DOMAIN_COMPONENT_ROOTS"


def _default_pack_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _is_dir(path: Path) -> bool:
    try:
        return path.is_dir()
    except OSError:
        return False


def _is_file(path: Path) -> bool:
    try:
        return path.is_file()
    except OSError:
        return False


def _coerce_domain_root(path: Path | str) -> Path:
    candidate = Path(path).expanduser()
    if _is_file(candidate / "ecosystem.json"):
        return candidate / "domain"
    if candidate.name == "extensions" and _is_file(candidate.parent / "ecosystem.json"):
        return candidate.parent / "domain"
    return candidate


def _append_unique(roots: list[Path], root: Path | str) -> None:
    candidate = _coerce_domain_root(root)
    if candidate not in roots:
        roots.append(candidate)


def _pack_roots_in_ecosystem_dir(ecosystem_dir: Path) -> list[Path]:
    if not _is_dir(ecosystem_dir):
        return []
    roots: list[Path] = []
    try:
        children = sorted(ecosystem_dir.iterdir())
    except OSError:
        return []
    for child in children:
        if _is_dir(child) and _is_file(child / "ecosystem.json"):
            roots.append(child)
    return roots


def _append_resolved_root(roots: list[Path], root: Path | str) -> None:
    _append_resolved_root_with_options(roots, root, allow_direct_root=True)


def _append_resolved_root_with_options(
    roots: list[Path],
    root: Path | str,
    *,
    allow_direct_root: bool,
) -> None:
    candidate = Path(root).expanduser()
    if _is_file(candidate / "ecosystem.json") or (
        candidate.name == "extensions" and _is_file(candidate.parent / "ecosystem.json")
    ):
        _append_unique(roots, candidate)
        return
    for ecosystem_dir in (candidate, candidate / "ecosystem"):
        pack_roots = _pack_roots_in_ecosystem_dir(ecosystem_dir)
        if not pack_roots:
            continue
        for pack_root in pack_roots:
            _append_unique(roots, pack_root)
        return
    if allow_direct_root:
        _append_unique(roots, candidate)


def _env_roots(raw: str | None = None) -> list[Path]:
    roots: list[Path] = []
    sources = (
        [(raw, True)]
        if raw is not None
        else [
            (os.environ.get(_EXTRA_DOMAIN_ROOTS_ENV, ""), True),
            (os.environ.get("RUMI_DEFAULTSPACK_EXTENSION_ROOTS", ""), True),
            (os.environ.get("RUMI_APP_DIR", ""), False),
            (os.environ.get("RUMI_HOME", ""), False),
        ]
    )
    for value, allow_direct_root in sources:
        for item in str(value or "").split(os.pathsep):
            item = item.strip()
            if item:
                _append_resolved_root_with_options(
                    roots,
                    item,
                    allow_direct_root=allow_direct_root,
                )
    return roots


def build_domain_component_roots(
    pack_root: Path | str,
    *,
    extra_roots: Iterable[Path | str] | None = None,
) -> list[Path]:
    pack_root = Path(pack_root)
    ecosystem_dir = pack_root.parent
    roots: list[Path] = []

    _append_unique(roots, pack_root / "domain")
    if _is_dir(ecosystem_dir):
        try:
            siblings = sorted(ecosystem_dir.iterdir())
        except OSError:
            siblings = []
        for sibling in siblings:
            if sibling == pack_root:
                continue
            if _is_dir(sibling) and _is_file(sibling / "ecosystem.json") and _is_dir(sibling / "domain"):
                _append_unique(roots, sibling / "domain")

    _append_unique(roots, pack_root / "user_data" / "shared" / "domain_components")
    for root in extra_roots or ():
        _append_resolved_root(roots, root)
    return roots


def get_domain_component_roots() -> list[Path]:
    return build_domain_component_roots(_default_pack_root(), extra_roots=_env_roots())


class DomainComponentRegistry:
    def __init__(
        self,
        roots: Path | str | Iterable[Path | str] | None = None,
        *,
        strict: bool = False,
    ) -> None:
        if roots is None:
            self._roots = get_domain_component_roots()
        elif isinstance(roots, (str, Path)):
            self._roots = [_coerce_domain_root(roots)]
        else:
            self._roots = [_coerce_domain_root(root) for root in roots]
        self._strict = strict
        self._components: dict[str, dict[str, DomainComponent]] = {}
        self._aliases: dict[str, dict[str, str]] = {}
        self._issues: list[ComponentDiscoveryIssue] = []
        self.reload()

    @property
    def roots(self) -> list[Path]:
        return list(self._roots)

    @property
    def issues(self) -> list[ComponentDiscoveryIssue]:
        return list(self._issues)

    def reload(self) -> "DomainComponentRegistry":
        self._components = {}
        self._aliases = {}
        self._issues = []
        result = discover_components(self._roots, strict=self._strict)
        self._issues.extend(result.issues)
        for component in result.components:
            bucket = self._components.setdefault(component.category, {})
            bucket[component.id] = component
            alias_bucket = self._aliases.setdefault(component.category, {})
            for alias in component.aliases:
                alias_bucket.setdefault(alias, component.id)
        return self

    def diagnostics(self) -> list[dict[str, str]]:
        return [
            {"path": issue.path, "category": issue.category, "message": issue.message}
            for issue in self._issues
        ]

    def categories(self) -> list[str]:
        return sorted(self._components.keys())

    def list(
        self,
        category: str | None = None,
        *,
        status: str | None = None,
    ) -> list[DomainComponent]:
        categories = [category] if category else self.categories()
        items: list[DomainComponent] = []
        for current_category in categories:
            items.extend(self._components.get(str(current_category), {}).values())
        if status:
            items = [item for item in items if item.status == status]
        items.sort(key=lambda item: (item.category, item.id))
        return items

    def manifests(self, category: str | None = None) -> list[dict]:
        return [component.as_dict() for component in self.list(category)]

    def get(self, category: str, component_id: str) -> DomainComponent | None:
        category = str(category or "").strip()
        component_id = str(component_id or "").strip()
        if not category or not component_id:
            return None
        bucket = self._components.get(category, {})
        if component_id in bucket:
            return bucket[component_id]
        alias_target = self._aliases.get(category, {}).get(component_id)
        if alias_target:
            return bucket.get(alias_target)
        return None

    def manifest_for(self, category: str, component_id: str) -> dict | None:
        component = self.get(category, component_id)
        return component.as_dict() if component else None

    def aliases_for(self, category: str) -> dict[str, str]:
        return dict(self._aliases.get(str(category or "").strip(), {}))


def get_domain_component_registry(
    *,
    force_reload: bool = False,
    strict: bool = False,
) -> DomainComponentRegistry:
    global _REGISTRY
    if _REGISTRY is None:
        with _LOCK:
            if _REGISTRY is None:
                _REGISTRY = DomainComponentRegistry(strict=strict)
    elif force_reload:
        with _LOCK:
            _REGISTRY = DomainComponentRegistry(strict=strict)
    return _REGISTRY
