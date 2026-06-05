from __future__ import annotations

import ast
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
DOMAIN_ROOT = DEFAULTSPACK_ROOT / "domain"
BOUNDARIES_PATH = DEFAULTSPACK_ROOT / "domain_boundaries.yaml"


def _read_yaml(path: Path) -> dict[str, Any]:
    try:
        import yaml

        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def _domain_name_for_path(path: Path) -> str:
    rel = path.relative_to(DOMAIN_ROOT)
    return rel.parts[0]


def _iter_domain_imports(py_path: Path) -> set[str]:
    imports: set[str] = set()
    try:
        tree = ast.parse(py_path.read_text(encoding="utf-8"), filename=str(py_path))
    except SyntaxError:
        raise

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module.startswith("ecosystem.defaultspack.domain."):
                rest = module.split("ecosystem.defaultspack.domain.", 1)[1]
            elif module.startswith("domain."):
                rest = module.split("domain.", 1)[1]
            else:
                continue
            target = rest.split(".", 1)[0]
            if target:
                imports.add(target)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                module = alias.name
                if module.startswith("ecosystem.defaultspack.domain."):
                    rest = module.split("ecosystem.defaultspack.domain.", 1)[1]
                elif module.startswith("domain."):
                    rest = module.split("domain.", 1)[1]
                else:
                    continue
                target = rest.split(".", 1)[0]
                if target:
                    imports.add(target)
    return imports


def main() -> int:
    config = _read_yaml(BOUNDARIES_PATH)
    domains = config.get("domains") or {}
    exceptions = config.get("exceptions") or []
    errors: list[str] = []

    configured_domains = set(domains)
    actual_domains = {
        path.name
        for path in DOMAIN_ROOT.iterdir()
        if path.is_dir() and not path.name.startswith("__")
    }
    missing_domains = sorted(actual_domains - configured_domains)
    if missing_domains:
        errors.append(
            "domain_boundaries.yaml is missing domains: " + ", ".join(missing_domains)
        )

    exception_keys = {
        (
            str(item.get("from") or "").strip(),
            str(item.get("import") or "").strip().replace("domain/", "").replace("domain.", ""),
            str(item.get("file") or "").strip(),
        )
        for item in exceptions
        if isinstance(item, dict)
    }

    for domain_name, spec in sorted(domains.items()):
        if not isinstance(spec, dict):
            errors.append(f"domain spec must be a mapping: {domain_name}")
            continue
        path = DEFAULTSPACK_ROOT / str(spec.get("path") or "")
        allowed = {
            str(item).replace("domain/", "").replace("domain.", "").split("/", 1)[0]
            for item in (spec.get("may_import") or [])
            if str(item).strip()
        }
        if not path.is_dir():
            errors.append(f"domain path does not exist: {domain_name} -> {path.relative_to(ROOT)}")
            continue
        for py_path in sorted(path.rglob("*.py")):
            source_domain = _domain_name_for_path(py_path)
            for target_domain in sorted(_iter_domain_imports(py_path)):
                if target_domain == source_domain:
                    continue
                rel_file = str(py_path.relative_to(DEFAULTSPACK_ROOT))
                if (source_domain, target_domain, rel_file) in exception_keys:
                    continue
                if target_domain not in allowed:
                    errors.append(
                        f"cross-domain import not allowlisted: {source_domain} -> {target_domain} in {rel_file}"
                    )

    if errors:
        print("defaultspack boundary scan failed:")
        for error in errors:
            print(f"- {error}")
        return 1

    print("defaultspack boundary scan passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
