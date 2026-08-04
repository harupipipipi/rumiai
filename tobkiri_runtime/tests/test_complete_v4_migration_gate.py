"""Non-negotiable, current-tree gates for the complete Tobkiri v4 migration.

The inventory is deliberately finite: only the three canonical artifacts in
each direct ``ecosystem`` Pack directory are counted.  Source checks use
Python ASTs or comment/string-stripped Rust call tokens so schemas, type
declarations, tests, Playwright, development helpers, and display text do not
become runtime findings.
"""

from __future__ import annotations

import ast
import hashlib
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Mapping

from tobkiri_protocol.validation import load_schema, validate_file


ROOT = Path(__file__).resolve().parents[2]
RUNTIME = ROOT / "tobkiri_runtime"
ECOSYSTEM = RUNTIME / "ecosystem"
START_SHA = "df61ff78bdeed84aae7096e06d7608cce70f2b8a"

EXPECTED_PRODUCTION_PACK_COUNT = 141
PACK_ARTIFACTS = {
    "artifact-index.v4.json": "pack_artifact_index",
    "pack.v4.json": "pack",
    "contracts.v4.json": "pack_contract_catalog",
}
EXPECTED_AUTHORITY_COUNTS = {
    "legacy-authoritative": 46,
    "modern-only": 0,
    "v3-authoritative": 95,
}
SOURCE_SUFFIXES = {".py", ".rs"}
IGNORED_PARTS = {
    ".git",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "target",
    "tests",
    "fixtures",
    "schemas",
    "schema",
    "playwright",
    "dev",
    "display",
}
IGNORED_FILE_TOKENS = (
    ".schema.",
    ".d.ts",
    "schema",
    "typing",
    "types",
    "playwright",
    "debug",
    "package",
    "verify",
    "prepare",
    ".test.",
    "_test.",
)

LEGACY_SYMBOLS = frozenset(
    {
        "FunctionRegistry",
        "InterfaceRegistry",
        "CapabilityExecutor",
        "AuthorityService",
        "PermissionManager",
    }
)
LEGACY_AUTHORITY_MODULES = frozenset(
    {
        "core_runtime.authority.service",
        "core_runtime.authority",
        "backend_core.ecosystem.registry",
    }
)
INSTALLED_LOOKUP_NAMES = frozenset(
    {
        "all_installed",
        "installed_packs",
        "_discover_installed_packs",
        "discover_installed_packs",
        "list_installed_packs",
    }
)
PROJECTION_CALL_NAMES = frozenset(
    {"generate_legacy_ecosystem_projection", "project_legacy_ecosystem"}
)
FALLBACK_NAMES = frozenset(
    {
        "active_provider_fallback",
        "fallback_provider",
        "implicit_fallback",
        "promotion_fallback",
        "auto_promote",
        "auto_promotion",
    }
)
OLD_COMPOSITION_MODULE = "domain.pack_architecture"

RUST_CALL_PATTERNS = (
    ("launcher_env", re.compile(r"\b(?:std::)?env::var(?:_os)?\s*\(")),
    ("launcher_command", re.compile(r"\b(?:std::process::)?Command::new\s*\(")),
    ("launcher_spawn", re.compile(r"\.spawn\s*\(")),
)


def _production_files() -> tuple[Path, ...]:
    """Return only production Python/Rust files in the scoped surfaces."""
    roots = (
        RUNTIME / "core_runtime",
        RUNTIME / "backend_core",
        RUNTIME / "ecosystem",
        RUNTIME / "tobkiri_host",
        ROOT / "tobkiri_launcher" / "src-tauri" / "src",
        ROOT / "tobkiri_launcher" / "scripts",
        ROOT / "pack-shell" / "src",
    )
    paths: set[Path] = set()
    for base in roots:
        if not base.is_dir():
            continue
        for path in base.rglob("*"):
            if path.is_file() and path.suffix.lower() in SOURCE_SUFFIXES:
                paths.add(path)
    return tuple(sorted(path for path in paths if not _ignored_source(path)))


def _ignored_source(path: Path) -> bool:
    """Exclude non-production source contexts before syntax analysis."""
    if any(part in IGNORED_PARTS for part in path.parts):
        return True
    name = path.name.lower()
    return any(token in name for token in IGNORED_FILE_TOKENS)


def _relative(path: Path) -> str:
    """Return a stable repository-relative path."""
    return path.relative_to(ROOT).as_posix()


def _finding(path: Path, line: int, rule: str, **extra: Any) -> dict[str, Any]:
    """Build one deterministic scanner finding."""
    return {"path": _relative(path), "line": line, "rule": rule, **extra}


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return None


def _sha256(path: Path) -> str:
    """Return the protocol digest for one regular file."""
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _production_pack_dirs() -> tuple[Path, ...]:
    """Return exactly the direct Pack roots under ``ecosystem``."""
    return tuple(
        sorted(
            path
            for path in ECOSYSTEM.iterdir()
            if path.is_dir() and path.name != "setup_pack" and not path.name.startswith(".")
        )
    )


def _v4_pack_artifacts() -> list[Path]:
    """Return only the 141 direct ``pack.v4.json`` files."""
    return [path / "pack.v4.json" for path in _production_pack_dirs()]


def _v4_profile_artifacts() -> list[Path]:
    """Return the explicit v4 Profile entrypoint, not recursive Pack bundles."""
    path = ECOSYSTEM / "defaultspack" / "v4" / "defaults.profile.v4.json"
    return [path] if path.is_file() else []


def _v4_artifact_findings() -> list[dict[str, Any]]:
    """Validate the exact 141 x 3 direct artifact set and cross-file pins."""
    findings: list[dict[str, Any]] = []
    for pack_dir in _production_pack_dirs():
        values: dict[str, Mapping[str, Any]] = {}
        for name, schema_name in PACK_ARTIFACTS.items():
            path = pack_dir / name
            if not path.is_file():
                findings.append(_finding(path, 1, "missing_v4_artifact", artifact=name))
                continue
            try:
                values[name] = validate_file(path, schema_name)
            except Exception as exc:  # schema validator emits stable diagnostics
                findings.append(
                    _finding(
                        path,
                        1,
                        "invalid_v4_artifact",
                        artifact=name,
                        error=str(exc)[:240],
                    )
                )

        manifest = values.get("pack.v4.json")
        index = values.get("artifact-index.v4.json")
        contracts = values.get("contracts.v4.json")
        if not manifest or not index or not contracts:
            continue
        pack_id = manifest.get("pack", {}).get("id")
        source_identity = manifest.get("integrity", {}).get("source_identity")
        if pack_id != pack_dir.name:
            findings.append(
                _finding(pack_dir / "pack.v4.json", 1, "pack_identity_mismatch", expected=pack_dir.name, actual=pack_id)
            )
        if set((index.get("pack_id"), contracts.get("pack_id"), pack_id)) != {pack_dir.name}:
            findings.append(_finding(pack_dir / "pack.v4.json", 1, "artifact_pack_id_mismatch"))
        if set(
            (
                source_identity,
                index.get("source_identity"),
                contracts.get("source_identity"),
            )
        ) != {source_identity}:
            findings.append(_finding(pack_dir / "pack.v4.json", 1, "source_identity_mismatch"))

        expected_artifacts = {
            "pack.v4.json": ("canonical_manifest", _sha256(pack_dir / "pack.v4.json")),
            "contracts.v4.json": ("contract_catalog", _sha256(pack_dir / "contracts.v4.json")),
        }
        indexed = {item.get("path"): item for item in index.get("artifacts", [])}
        for name, (role, digest) in expected_artifacts.items():
            item = indexed.get(name)
            if not isinstance(item, Mapping) or item.get("role") != role or item.get("digest") != digest:
                findings.append(_finding(pack_dir / "artifact-index.v4.json", 1, "artifact_digest_mismatch", artifact=name))
        if index.get("artifact_set_digest") != manifest.get("pack", {}).get("artifact_digest"):
            findings.append(_finding(pack_dir / "pack.v4.json", 1, "artifact_set_digest_mismatch"))
        integrity = manifest.get("integrity", {})
        if integrity.get("contract_catalog_digest") != _sha256(pack_dir / "contracts.v4.json"):
            findings.append(_finding(pack_dir / "pack.v4.json", 1, "contract_catalog_digest_mismatch"))
    return findings


def _v4_profile_findings() -> list[dict[str, Any]]:
    """Validate the explicit Profile artifact and its exact selection shape."""
    findings: list[dict[str, Any]] = []
    for path in _v4_profile_artifacts():
        try:
            profile = validate_file(path, "profile")
        except Exception as exc:
            findings.append(_finding(path, 1, "invalid_v4_profile", error=str(exc)[:240]))
            continue
        if profile.get("profile_id") != "defaults" or profile.get("state") != "needs_resolution":
            findings.append(_finding(path, 1, "profile_scope_mismatch"))
        if not isinstance(profile.get("base"), Mapping) or not isinstance(profile.get("shell"), Mapping):
            findings.append(_finding(path, 1, "profile_selection_not_exact"))
    return findings


def _manifest_authority_counts() -> tuple[Counter[str], list[dict[str, Any]]]:
    """Return direct-Pack authority ownership without discovering installed Packs."""
    catalog = _load_json(RUNTIME / "schemas" / "manifest_authority.v1.json")
    classified = catalog.get("packs", {}) if isinstance(catalog, Mapping) else {}
    records = [
        {
            "pack_id": path.name,
            "classified_as": classified.get(path.name),
            "v4_artifacts": all((path / name).is_file() for name in PACK_ARTIFACTS),
        }
        for path in _production_pack_dirs()
    ]
    return Counter(str(record["classified_as"]) for record in records), records


def _authority_resolved_plan_findings() -> list[dict[str, Any]]:
    """Require exact Authority ownership and the narrow ResolvedPlan scope."""
    findings: list[dict[str, Any]] = []
    counts, records = _manifest_authority_counts()
    catalog = _load_json(RUNTIME / "schemas" / "manifest_authority.v1.json")
    classified = catalog.get("packs", {}) if isinstance(catalog, Mapping) else {}
    direct_ids = {record["pack_id"] for record in records}
    if set(classified) != direct_ids or counts != Counter(EXPECTED_AUTHORITY_COUNTS):
        findings.append(
            {
                "path": "tobkiri_runtime/schemas/manifest_authority.v1.json",
                "line": 1,
                "rule": "authority_scope_mismatch",
                "classified": dict(sorted(classified.items())),
                "direct_pack_count": len(direct_ids),
            }
        )
    plan_schema = load_schema("resolved_plan")
    required_plan = frozenset(plan_schema.get("required", ()))
    expected_plan = frozenset(
        {
            "plan_api_version",
            "profile_id",
            "profile_revision",
            "security_epoch",
            "base",
            "shell",
            "bindings",
            "plan_digest",
        }
    )
    if required_plan != expected_plan:
        findings.append(
            {
                "path": "tobkiri_runtime/tobkiri_protocol/schemas/resolved_plan_v1.schema.json",
                "line": 1,
                "rule": "resolved_plan_scope_mismatch",
                "required": sorted(required_plan),
            }
        )
    contracts_path = RUNTIME / "tobkiri_host" / "contracts.py"
    try:
        tree = ast.parse(contracts_path.read_text(encoding="utf-8"), filename=str(contracts_path))
        operation_catalog = next(
            node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "OperationCatalog"
        )
        methods = {node.name for node in operation_catalog.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))}
        if not {"__init__", "resolve"}.issubset(methods):
            raise LookupError("OperationCatalog exact resolve scope is missing")
    except (OSError, SyntaxError, LookupError) as exc:
        findings.append(_finding(contracts_path, 1, "resolved_plan_runtime_scope_missing", error=str(exc)))
    return findings


def _python_tree(path: Path) -> ast.AST | None:
    try:
        return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except (OSError, UnicodeError, SyntaxError):
        return None


def _parents(tree: ast.AST) -> dict[ast.AST, ast.AST]:
    return {child: parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)}


def _owner(node: ast.AST, parents: Mapping[ast.AST, ast.AST]) -> str:
    current = node
    while current in parents:
        current = parents[current]
        if isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            return current.name
    return "<module>"


def _called_name(node: ast.Call) -> str:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return ""


def _ast_legacy_runtime_findings() -> list[dict[str, Any]]:
    """Find reachable legacy Registry and installed-inventory calls via AST."""
    findings: list[dict[str, Any]] = []
    for path in _production_files():
        if path.suffix != ".py":
            continue
        tree = _python_tree(path)
        if tree is None:
            continue
        parents = _parents(tree)
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                module = node.module or "" if isinstance(node, ast.ImportFrom) else ""
                imported = {alias.name.split(".")[-1] for alias in node.names}
                if module in LEGACY_AUTHORITY_MODULES or imported & LEGACY_SYMBOLS:
                    findings.append(
                        _finding(
                            path,
                            node.lineno,
                            "legacy_registry_import",
                            module=module,
                            symbols=sorted(imported & LEGACY_SYMBOLS),
                        )
                    )
            elif isinstance(node, ast.ClassDef) and node.name in LEGACY_SYMBOLS:
                findings.append(_finding(path, node.lineno, "legacy_registry_definition", symbol=node.name))
            elif isinstance(node, ast.Call):
                name = _called_name(node)
                if name in LEGACY_SYMBOLS:
                    findings.append(
                        _finding(path, node.lineno, "legacy_registry_call", symbol=name, owner=_owner(node, parents))
                    )
                if name in INSTALLED_LOOKUP_NAMES:
                    findings.append(
                        _finding(path, node.lineno, "runtime_installed_lookup", symbol=name, owner=_owner(node, parents))
                    )
    return findings


def _ast_authority_bypass_findings() -> list[dict[str, Any]]:
    """Find executable legacy authority bypasses without matching text."""
    findings: list[dict[str, Any]] = []
    for path in _production_files():
        if path.suffix != ".py":
            continue
        tree = _python_tree(path)
        if tree is None:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                name = _called_name(node)
                if name in {"FunctionRegistry", "InterfaceRegistry", "CapabilityExecutor", "AuthorityService"}:
                    findings.append(_finding(path, node.lineno, "authority_bypass_call", symbol=name))
                if any(keyword.arg == "approved" and isinstance(keyword.value, ast.Constant) and keyword.value.value is True for keyword in node.keywords):
                    findings.append(_finding(path, node.lineno, "client_approval_flag"))
            elif isinstance(node, ast.Attribute) and node.attr in {"authority_granted", "host_execution"}:
                findings.append(_finding(path, node.lineno, "authority_bypass_attribute", symbol=node.attr))
    return findings


def _ast_projection_findings() -> list[dict[str, Any]]:
    """Find projection calls in runtime code; offline scripts are not runtime."""
    findings: list[dict[str, Any]] = []
    for path in _production_files():
        if path.suffix != ".py" or "scripts" in path.parts:
            continue
        tree = _python_tree(path)
        if tree is None:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and _called_name(node) in PROJECTION_CALL_NAMES:
                findings.append(_finding(path, node.lineno, "runtime_projection_call", symbol=_called_name(node)))
    return findings


def _ast_fallback_findings() -> list[dict[str, Any]]:
    """Find executable fallback/promotion symbols via AST names and calls."""
    findings: list[dict[str, Any]] = []
    for path in _production_files():
        if path.suffix != ".py":
            continue
        tree = _python_tree(path)
        if tree is None:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and _called_name(node) in FALLBACK_NAMES:
                findings.append(_finding(path, node.lineno, "implicit_fallback_call", symbol=_called_name(node)))
    return findings


def _ast_old_composition_findings() -> list[dict[str, Any]]:
    """Find deleted composition imports, not schema fields or display text."""
    findings: list[dict[str, Any]] = []
    for path in _production_files():
        if path.suffix != ".py":
            continue
        tree = _python_tree(path)
        if tree is None:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == OLD_COMPOSITION_MODULE or alias.name.startswith(f"{OLD_COMPOSITION_MODULE}."):
                        findings.append(_finding(path, node.lineno, "deleted_composition_import", module=alias.name))
            elif isinstance(node, ast.ImportFrom) and (node.module or "").startswith(OLD_COMPOSITION_MODULE):
                findings.append(_finding(path, node.lineno, "deleted_composition_import", module=node.module))
    return findings


def _strip_rust_comments_and_strings(source: str) -> str:
    """Remove Rust comments and string contents while preserving line offsets."""
    without_comments = re.sub(r"//[^\n]*|/\*.*?\*/", _preserve_lines, source, flags=re.S)
    return re.sub(r'"(?:\\.|[^"\\])*"', '""', without_comments)


def _preserve_lines(match: re.Match[str]) -> str:
    return "".join("\n" if char == "\n" else " " for char in match.group(0))


def _rust_function_at(source: str, offset: int) -> str:
    matches = list(re.finditer(r"\bfn\s+([A-Za-z_][A-Za-z0-9_]*)", source[:offset]))
    return matches[-1].group(1) if matches else "<module>"


def _rust_call_findings() -> list[dict[str, Any]]:
    """Find production Launcher calls after comments and string literals are removed."""
    findings: list[dict[str, Any]] = []
    for path in _production_files():
        if path.suffix != ".rs" or "tobkiri_launcher" not in path.parts:
            continue
        try:
            source = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            continue
        stripped = _strip_rust_comments_and_strings(source)
        for rule, pattern in RUST_CALL_PATTERNS:
            for match in pattern.finditer(stripped):
                function = _rust_function_at(stripped, match.start())
                if function.startswith("debug_") or function.startswith("test"):
                    continue
                line = stripped.count("\n", 0, match.start()) + 1
                findings.append(_finding(path, line, rule, function=function))
    return findings


def _launcher_safety_findings() -> list[dict[str, Any]]:
    """Scan Launcher env/PATH/process calls and unverified v3 entrypoints."""
    findings = _rust_call_findings()
    for path in _production_files():
        if path.suffix != ".py" or "tobkiri_launcher" not in path.parts:
            continue
        tree = _python_tree(path)
        if tree is None:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
                if node.func.value.id == "subprocess":
                    findings.append(_finding(path, node.lineno, "launcher_process_call", symbol=node.func.attr))
                if node.func.value.id == "os" and node.func.attr in {"system", "popen"}:
                    findings.append(_finding(path, node.lineno, "launcher_process_call", symbol=node.func.attr))
    for path in sorted(ECOSYSTEM.glob("*/rumi.pack.v3.json")):
        value = _load_json(path)
        if not isinstance(value, Mapping):
            continue
        for entry in value.get("entrypoints", []):
            if isinstance(entry, Mapping) and entry.get("loader") in {"python", "process"}:
                findings.append(_finding(path, 1, "unverified_v3_entrypoint", loader=entry.get("loader")))
        provenance = value.get("provenance")
        if isinstance(provenance, Mapping) and provenance.get("signature") is None:
            findings.append(_finding(path, 1, "unverified_v3_provenance"))
    return sorted(findings, key=lambda item: (item["path"], item["line"], item["rule"]))


def _double_authority_findings() -> list[dict[str, Any]]:
    """Detect a production authority inventory that can read both Pack roots."""
    findings: list[dict[str, Any]] = []
    path = RUNTIME / "backend_core" / "ecosystem" / "registry.py"
    tree = _python_tree(path)
    if tree is None:
        return findings
    has_registry = any(
        isinstance(node, ast.ClassDef) and node.name == "Registry"
        for node in ast.walk(tree)
    )
    has_inventory_read = any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in {"iterdir", "glob", "rglob"}
        for node in ast.walk(tree)
    )
    if has_registry and has_inventory_read:
        findings.append(
            _finding(
                path,
                1,
                "double_authority_reachable",
                text="production EcosystemRegistry inventories direct defaults and defaultspack roots",
            )
        )
    return findings


def _offline_projection_findings() -> list[dict[str, Any]]:
    """Require projection marker, owner marker, and canonical source identity."""
    findings: list[dict[str, Any]] = []
    catalog = _load_json(RUNTIME / "schemas" / "manifest_authority.v1.json")
    authorities = catalog.get("packs", {}) if isinstance(catalog, Mapping) else {}
    for pack_dir in _production_pack_dirs():
        if authorities.get(pack_dir.name) != "v3-authoritative":
            continue
        legacy_path = pack_dir / "ecosystem.json"
        source_path = pack_dir / "rumi.pack.v3.json"
        value = _load_json(legacy_path)
        metadata = value.get("metadata") if isinstance(value, Mapping) else None
        generated = metadata.get("generated_from") if isinstance(metadata, Mapping) else None
        expected = {
            "format": "rumi.ecosystem.v1",
            "generated": True,
            "read_only_projection": True,
            "manifest_authority": "v3-authoritative",
        }
        if not isinstance(metadata, Mapping) or any(metadata.get(key) != expected_value for key, expected_value in expected.items()):
            findings.append(_finding(legacy_path, 1, "projection_marker_or_owner_missing"))
            continue
        if not isinstance(generated, Mapping) or generated.get("source") != "rumi.pack.v3.json" or generated.get("generator") != "tobkiri.core_runtime.manifest_projection/v2":
            findings.append(_finding(legacy_path, 1, "projection_source_marker_missing"))
        if not source_path.is_file() or generated.get("source_content_hash") != _source_identity(source_path):
            findings.append(_finding(legacy_path, 1, "projection_source_identity_mismatch"))
    return findings


def _source_identity(path: Path) -> str:
    """Compute the canonical v3 source identity through the production helper."""
    from core_runtime.manifest_projection import source_manifest_identity

    value = _load_json(path)
    return source_manifest_identity(value) if isinstance(value, Mapping) else ""


def _audit_snapshot() -> dict[str, Any]:
    """Collect deterministic current-tree evidence with no baseline or skip."""
    pack_dirs = _production_pack_dirs()
    artifact_findings = _v4_artifact_findings()
    authority_findings = _authority_resolved_plan_findings()
    legacy_findings = _ast_legacy_runtime_findings()
    bypass_findings = _ast_authority_bypass_findings()
    projection_calls = _ast_projection_findings()
    fallback_findings = _ast_fallback_findings()
    old_composition = _ast_old_composition_findings()
    double_authority = _double_authority_findings()
    launcher = _launcher_safety_findings()
    projection = _offline_projection_findings()
    gates = {
        "artifact_contracts": artifact_findings,
        "authority_resolved_plan_scope": authority_findings,
        "legacy_registry_and_installed_lookup": legacy_findings + bypass_findings + old_composition + fallback_findings + projection_calls,
        "double_authority": double_authority,
        "launcher_safety": launcher,
        "offline_projection": projection,
    }
    return {
        "schema": "io.tobkiri.quality.complete-v4-migration.v2",
        "start_sha": START_SHA,
        "head_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "gate": {
            "status": "GREEN" if all(not findings for findings in gates.values()) else "RED",
            "clean": all(not findings for findings in gates.values()),
            "expected_green": {name: 0 for name in gates},
        },
        "gates": {name: {"status": "GREEN" if not findings else "RED", "findings": findings} for name, findings in gates.items()},
        "pack_inventory": {
            "production_pack_directories": len(pack_dirs),
            "expected_production_pack_directories": EXPECTED_PRODUCTION_PACK_COUNT,
            "v4_artifacts_per_pack": len(PACK_ARTIFACTS),
            "v4_artifact_files": len(pack_dirs) * len(PACK_ARTIFACTS),
            "v4_pack_artifacts": [_relative(path) for path in _v4_pack_artifacts()],
            "v4_profile_artifacts": [_relative(path) for path in _v4_profile_artifacts()],
            "authority_counts": dict(sorted(_manifest_authority_counts()[0].items())),
            "authority_records": _manifest_authority_counts()[1],
        },
        "findings": gates,
    }


def _assert_zero(name: str, findings: list[dict[str, Any]]) -> None:
    """Fail with deterministic evidence and never baseline a finding."""
    assert not findings, f"{name} RED: count={len(findings)} evidence={findings[:8]}"


def test_production_v4_pack_and_profile_artifacts_are_complete() -> None:
    """The exact direct artifact set is 141 Packs x 3 files."""
    assert len(_production_pack_dirs()) == EXPECTED_PRODUCTION_PACK_COUNT
    assert len(_v4_pack_artifacts()) == EXPECTED_PRODUCTION_PACK_COUNT
    assert len(_v4_pack_artifacts()) * len(PACK_ARTIFACTS) == 423
    _assert_zero("v4 artifact contracts", _v4_artifact_findings())


def test_authority_and_resolved_plan_scope_is_exact() -> None:
    """Authority ownership and ResolvedPlan fields remain exact and finite."""
    _assert_zero("Authority/ResolvedPlan scope", _authority_resolved_plan_findings())


def test_legacy_registry_and_installed_lookup_are_zero() -> None:
    """Legacy Registry, runtime inventory lookup, bypass, and projection calls are zero."""
    _assert_zero(
        "legacy Registry/all-installed runtime lookup",
        _ast_legacy_runtime_findings()
        + _ast_authority_bypass_findings()
        + _ast_old_composition_findings()
        + _ast_fallback_findings()
        + _ast_projection_findings(),
    )


def test_double_authority_is_zero_by_production_reachability() -> None:
    """Directory presence alone is not a double-authority finding."""
    _assert_zero("double authority", _double_authority_findings())


def test_launcher_env_path_direct_and_unverified_fallback_are_zero() -> None:
    """Launcher has no unscoped environment, process, or unverified entrypoint path."""
    _assert_zero("Launcher env/PATH/direct/unverified fallback", _launcher_safety_findings())


def test_offline_projection_has_marker_owner_and_source_identity() -> None:
    """Every v3 projection carries its offline marker, owner, and source identity."""
    _assert_zero("offline projection marker/owner/source identity", _offline_projection_findings())


def test_v4_runtime_and_protocol_composition_apis_are_live() -> None:
    """The live check uses runtime_v4 and protocol composition, never pack_architecture."""
    pack_root = RUNTIME / "ecosystem" / "defaultspack"
    if str(pack_root) not in sys.path:
        sys.path.insert(0, str(pack_root))
    from domain.runtime_v4 import BundledCatalog, ResolvedDefaultProfile, resolve_default_profile
    from tobkiri_protocol.composition import compose_runtime_profile, load_verified_catalog

    assert BundledCatalog is not None
    assert ResolvedDefaultProfile is not None
    assert callable(resolve_default_profile)
    assert callable(compose_runtime_profile)
    assert callable(load_verified_catalog)


def test_current_sha_red_evidence_reports_actual_findings() -> None:
    """Current SHA evidence is measured directly and remains RED until production migration."""
    report = _audit_snapshot()
    assert report["start_sha"] == START_SHA
    assert report["gate"]["status"] == "RED"
    assert report["pack_inventory"]["production_pack_directories"] == 141
    assert report["pack_inventory"]["v4_artifact_files"] == 423
