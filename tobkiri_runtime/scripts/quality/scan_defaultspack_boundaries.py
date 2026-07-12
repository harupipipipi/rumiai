from __future__ import annotations

import ast
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
DOMAIN_ROOT = DEFAULTSPACK_ROOT / "domain"
BOUNDARIES_PATH = DEFAULTSPACK_ROOT / "domain_boundaries.yaml"


class BoundaryConfigError(ValueError):
    pass


def _read_yaml(path: Path) -> dict[str, Any]:
    try:
        import yaml
    except ImportError as exc:
        raise BoundaryConfigError("PyYAML is required to read domain_boundaries.yaml") from exc
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        raise BoundaryConfigError(f"cannot read {path}: {exc}") from exc
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise BoundaryConfigError(f"invalid YAML in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise BoundaryConfigError("domain_boundaries.yaml root must be a mapping")
    return data


def _canonical_domain_path(value: object) -> str:
    path = str(value or "").strip().replace("\\", "/").replace(".", "/")
    path = path.strip("/")
    if path and not path.startswith("domain/"):
        path = f"domain/{path}"
    return path


def _absolute_domain_module(module: str) -> str | None:
    prefixes = ("ecosystem.defaultspack.domain", "domain")
    for prefix in prefixes:
        if module == prefix:
            return ""
        dotted_prefix = f"{prefix}."
        if module.startswith(dotted_prefix):
            return module[len(dotted_prefix) :]
    return None


def _relative_domain_module(
    py_path: Path, domain_root: Path, level: int, module: str
) -> str | None:
    if level <= 0:
        return None
    try:
        package_parts = list(py_path.parent.relative_to(domain_root).parts)
    except ValueError:
        return None
    module_parts = [part for part in module.split(".") if part]
    parent_hops = level - 1
    # Defaultspack is imported both with ``domain`` on sys.path and through its
    # full namespace-package name. Resolve against both identities so an import
    # that climbs above ``domain`` cannot disappear from the scan.
    package_variants = (
        ["domain", *package_parts],
        ["ecosystem", "defaultspack", "domain", *package_parts],
    )
    for package in package_variants:
        if parent_hops >= len(package):
            continue
        candidate = ".".join(package[: len(package) - parent_hops] + module_parts)
        resolved = _absolute_domain_module(candidate)
        if resolved is not None:
            return resolved
    return None


def _iter_domain_import_references(
    py_path: Path, domain_root: Path | None = None
) -> set[tuple[str, str]]:
    """Return ``(domain, module path)`` for imports rooted in defaultspack/domain."""
    domain_root = domain_root or DOMAIN_ROOT
    tree = ast.parse(py_path.read_text(encoding="utf-8"), filename=str(py_path))
    references: set[tuple[str, str]] = set()

    for node in ast.walk(tree):
        modules: list[str] = []
        if isinstance(node, ast.ImportFrom):
            if node.level:
                resolved = _relative_domain_module(
                    py_path, domain_root, node.level, node.module or ""
                )
            else:
                resolved = _absolute_domain_module(node.module or "")
            if resolved is None:
                continue
            if resolved:
                modules.append(resolved)
            else:
                # Covers bypass forms such as ``from domain import chat`` and
                # ``from .. import chat``. A package import is deliberately
                # treated as the domain root, not guessed to be a public module.
                modules.extend(alias.name for alias in node.names if alias.name != "*")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                resolved = _absolute_domain_module(alias.name)
                if resolved:
                    modules.append(resolved)

        for module in modules:
            parts = [part for part in module.split(".") if part]
            if parts:
                references.add((parts[0], f"domain/{'/'.join(parts)}"))
    return references


def _iter_domain_imports(py_path: Path) -> set[str]:
    """Compatibility helper used by focused scanner tests."""
    return {domain for domain, _module in _iter_domain_import_references(py_path)}


def _portable_rel(path: Path, base: Path) -> str:
    return path.relative_to(base).as_posix()


def _string_list(value: object, label: str, errors: list[str]) -> list[str]:
    if not isinstance(value, list):
        errors.append(f"{label} must be a list")
        return []
    result: list[str] = []
    for index, item in enumerate(value):
        if not isinstance(item, str) or not item.strip():
            errors.append(f"{label}[{index}] must be a non-empty string")
            continue
        result.append(item.strip())
    return result


def _validate_config(
    config: dict[str, Any], defaultspack_root: Path, domain_root: Path
) -> tuple[dict[str, Any], list[dict[str, str]], list[str]]:
    errors: list[str] = []
    domains_value = config.get("domains")
    if not isinstance(domains_value, dict):
        return {}, [], ["domain_boundaries.yaml domains must be a mapping"]

    actual_paths: dict[str, str] = {
        path.name: f"domain/{path.name}"
        for path in domain_root.iterdir()
        if path.is_dir() and not path.name.startswith("__")
    }
    actual_paths.update(
        {
            path.stem: f"domain/{path.name}"
            for path in domain_root.glob("*.py")
            if path.name != "__init__.py"
        }
    )

    domains: dict[str, Any] = {}
    for domain_name, spec in domains_value.items():
        if not isinstance(domain_name, str) or not domain_name.strip():
            errors.append("domain names must be non-empty strings")
            continue
        if not isinstance(spec, dict):
            errors.append(f"domain spec must be a mapping: {domain_name}")
            continue
        expected_path = actual_paths.get(domain_name)
        configured_path = spec.get("path")
        if not isinstance(configured_path, str) or configured_path != expected_path:
            errors.append(
                f"domain path must be {expected_path or f'domain/{domain_name}'}: "
                f"{domain_name} -> {configured_path!r}"
            )
        may_import = _string_list(
            spec.get("may_import"), f"domains.{domain_name}.may_import", errors
        )
        public_imports = _string_list(
            spec.get("public_imports", []),
            f"domains.{domain_name}.public_imports",
            errors,
        )
        domains[domain_name] = {
            "path": configured_path,
            "may_import": may_import,
            "public_imports": public_imports,
        }

    configured_domains = set(domains)
    missing_domains = sorted(set(actual_paths) - configured_domains)
    if missing_domains:
        errors.append("domain_boundaries.yaml is missing domains: " + ", ".join(missing_domains))
    unknown_specs = sorted(configured_domains - set(actual_paths))
    if unknown_specs:
        errors.append("domain_boundaries.yaml has unknown domains: " + ", ".join(unknown_specs))

    for domain_name, spec in domains.items():
        for field in ("may_import", "public_imports"):
            for item in spec[field]:
                canonical = _canonical_domain_path(item)
                target = canonical.removeprefix("domain/").split("/", 1)[0]
                if not target or target not in configured_domains:
                    errors.append(
                        f"unknown imported domain in domains.{domain_name}.{field}: {item}"
                    )
                if field == "may_import" and canonical != f"domain/{target}":
                    errors.append(
                        f"domains.{domain_name}.may_import must name a domain: {item}"
                    )
                if field == "public_imports":
                    target_path = defaultspack_root / canonical
                    if not target_path.with_suffix(".py").is_file():
                        errors.append(
                            "public import must name a concrete .py module for "
                            f"{domain_name}: {canonical}"
                        )

    exceptions_value = config.get("exceptions", [])
    if not isinstance(exceptions_value, list):
        errors.append("domain_boundaries.yaml exceptions must be a list")
        exceptions_value = []
    exceptions: list[dict[str, str]] = []
    for index, item in enumerate(exceptions_value):
        label = f"exceptions[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{label} must be a mapping")
            continue
        values: dict[str, str] = {}
        for field in ("file", "from", "import", "reason"):
            value = item.get(field)
            if not isinstance(value, str) or not value.strip():
                errors.append(f"{label}.{field} must be a non-empty string")
            else:
                values[field] = (
                    value.strip().replace("\\", "/") if field == "file" else value.strip()
                )
        if len(values) != 4:
            continue
        source = values["from"]
        file_path = values["file"]
        imported = _canonical_domain_path(values["import"])
        target = imported.removeprefix("domain/").split("/", 1)[0]
        if source not in configured_domains:
            errors.append(f"{label}.from names unknown domain: {source}")
        source_prefix = f"domain/{source}"
        if file_path != source_prefix + ".py" and not file_path.startswith(source_prefix + "/"):
            errors.append(f"{label}.file is outside source domain {source}: {file_path}")
        if Path(file_path).is_absolute() or ".." in Path(file_path).parts:
            errors.append(f"{label}.file must be a relative domain path: {file_path}")
        if not (defaultspack_root / file_path).is_file():
            errors.append(f"{label}.file does not exist: {file_path}")
        if target not in configured_domains:
            errors.append(f"{label}.import names unknown domain: {values['import']}")
        imported_path = defaultspack_root / imported
        if not imported_path.is_dir() and not imported_path.with_suffix(".py").is_file():
            errors.append(f"{label}.import module does not exist: {values['import']}")
        values["import"] = imported
        exceptions.append(values)
    return domains, exceptions, errors


def scan_boundaries(defaultspack_root: Path, boundaries_path: Path) -> list[str]:
    domain_root = defaultspack_root / "domain"
    if not domain_root.is_dir():
        return [f"domain root does not exist: {domain_root}"]
    try:
        config = _read_yaml(boundaries_path)
    except BoundaryConfigError as exc:
        return [str(exc)]
    domains, exceptions, errors = _validate_config(config, defaultspack_root, domain_root)
    if errors:
        return errors

    exception_keys = {
        (
            item["from"],
            item["import"],
            item["file"],
        )
        for item in exceptions
    }

    for domain_name, spec in sorted(domains.items()):
        path = defaultspack_root / spec["path"]
        allowed = {
            _canonical_domain_path(item).removeprefix("domain/").split("/", 1)[0]
            for item in (spec.get("may_import") or [])
            if str(item).strip()
        }
        public_imports = {
            _canonical_domain_path(item)
            for item in (spec.get("public_imports") or [])
            if str(item).strip()
        }
        public_domains = {item.removeprefix("domain/").split("/", 1)[0] for item in public_imports}
        overlap = sorted(allowed & public_domains)
        if overlap:
            errors.append(
                f"domain imports cannot be both broad and public-only: {domain_name} -> "
                + ", ".join(overlap)
            )
        py_paths = sorted(path.rglob("*.py")) if path.is_dir() else [path]
        for py_path in py_paths:
            try:
                references = _iter_domain_import_references(py_path, domain_root)
            except (OSError, UnicodeError, SyntaxError) as exc:
                errors.append(
                    f"cannot parse {_portable_rel(py_path, defaultspack_root)}: "
                    f"{type(exc).__name__}: {exc}"
                )
                continue
            source_domain = domain_name
            for target_domain, target_module in sorted(references):
                if target_domain == source_domain:
                    continue
                rel_file = _portable_rel(py_path, defaultspack_root)
                broad_exception = (source_domain, f"domain/{target_domain}", rel_file)
                exact_exception = (source_domain, target_module, rel_file)
                if broad_exception in exception_keys or exact_exception in exception_keys:
                    continue
                if target_domain in allowed or target_module in public_imports:
                    continue
                if target_domain in public_domains:
                    errors.append(
                        "cross-domain import bypasses public contract: "
                        f"{source_domain} -> {target_module} in {rel_file}"
                    )
                else:
                    errors.append(
                        f"cross-domain import not allowlisted: {source_domain} -> "
                        f"{target_domain} in {rel_file}"
                    )
    return errors


def main() -> int:
    errors = scan_boundaries(DEFAULTSPACK_ROOT, BOUNDARIES_PATH)
    if errors:
        print("defaultspack boundary scan failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    print("defaultspack boundary scan passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
