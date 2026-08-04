"""Non-negotiable RED gates for the complete Tobkiri v4 migration.

This file is intentionally independent of the historical pack-architecture
baseline.  It inventories production paths and asserts the v4 end state
directly.  The current migration snapshot is expected to be RED; these gates
must become GREEN only after the Sol-owned runtime changes are integrated.
"""

from __future__ import annotations

import ast
import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Iterable, Mapping

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[2]
RUNTIME = ROOT / "tobkiri_runtime"
ECOSYSTEM = RUNTIME / "ecosystem"
START_SHA = "64b2240e2e3d019c97920b6fb0e278cca83d6691"

SOURCE_SUFFIXES = {".py", ".rs", ".ts", ".tsx", ".js", ".jsx", ".dart"}
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
}

EXPECTED_AUTHORITY_COUNTS = {
    "legacy-authoritative": 46,
    "modern-only": 0,
    "v3-authoritative": 95,
}
EXPECTED_PRODUCTION_PACK_COUNT = 141

LEGACY_RUNTIME_MARKERS = (
    "FunctionRegistry",
    "InterfaceRegistry",
    "CapabilityExecutor",
    "AuthorityService",
    "python_file_call",
    "RUMI_ALLOW_HOST_EXECUTION",
    "pack_api_server",
    "importlib.import_module",
    "sys.path.insert",
)
AUTHORITY_BYPASS_MARKERS = (
    "core_runtime.authority.service",
    "from .authority.service import",
    "CapabilityExecutor(",
    "FunctionRegistry(",
    "InterfaceRegistry(",
    "authority_service",
    "host_execution",
    "RUMI_ALLOW_HOST_EXECUTION",
    "approved=True",
    "authority_granted",
)
OLD_COMPOSITION_MARKERS = (
    "rumi.profile.v1",
    "rumi.pack.v3",
    "rumi.ecosystem.v1",
    "base_pack",
    "desktop_app",
    "desktop_app.command",
    "graph_id",
    "capability_profile_id",
    "startup_profile",
    "operating_profile",
    "shell_provider",
)
DIRECT_SHELL_MARKERS = (
    "desktop_app.command",
    "read_desktop_app_command",
    "cargo tauri dev",
    "npm run dev",
)
DIRECT_SHELL_PROCESS_MARKERS = ("subprocess.Popen", "Command::new", ".spawn()")
DIRECT_SHELL_LAUNCH_FILES = {"desktop_app_manager.py", "dock_registration.rs"}
PROJECTION_RUNTIME_MARKERS = (
    "generate_legacy_ecosystem_projection",
    "project_legacy_ecosystem",
)
INSTALLED_SCAN_MARKERS = (
    "all_installed",
    "installed_packs",
    "_discover_installed_packs",
)
IMPLICIT_FALLBACK_MARKERS = (
    "active_provider_fallback",
    "fallback_provider",
    "implicit_fallback",
    "auto_promot",
    "promotion_fallback",
)


def _production_files() -> Iterable[Path]:
    """Yield production source files without test or fixture exemptions."""
    roots = (
        RUNTIME / "core_runtime",
        RUNTIME / "backend_core",
        RUNTIME / "ecosystem",
        RUNTIME / "tobkiri_host",
        ROOT / "tobkiri_launcher" / "src-tauri" / "src",
        ROOT / "tobkiri_launcher" / "frontend" / "src",
        ROOT / "tobkiri_launcher" / "scripts",
        ROOT / "tobkiri_mobile" / "lib",
        ROOT / "pack-shell" / "src",
    )
    for base in roots:
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if not path.is_file() or path.suffix.lower() not in SOURCE_SUFFIXES:
                continue
            if any(part in IGNORED_PARTS for part in path.parts):
                continue
            yield path


def _relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def _lines_containing(markers: Iterable[str]) -> list[dict[str, Any]]:
    """Return every production occurrence of any exact marker."""
    marker_set = tuple(markers)
    findings: list[dict[str, Any]] = []
    for path in _production_files():
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for line_number, line in enumerate(lines, start=1):
            hits = [marker for marker in marker_set if marker in line]
            if hits:
                findings.append(
                    {
                        "path": _relative(path),
                        "line": line_number,
                        "markers": hits,
                        "text": line.strip()[:240],
                    }
                )
    return findings


def _json_files() -> Iterable[Path]:
    """Yield production JSON manifests and schema-bearing documents."""
    for path in sorted(ECOSYSTEM.rglob("*.json")):
        if any(part in IGNORED_PARTS for part in path.parts):
            continue
        yield path


def _load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _v4_pack_artifacts() -> list[Path]:
    """Return checked-in production Pack manifests carrying the v4 schema."""
    result: list[Path] = []
    roots = (
        ECOSYSTEM,
        RUNTIME / "packs_v4",
        RUNTIME / "distributions",
    )
    paths: set[Path] = set()
    for root in roots:
        if root.is_dir():
            paths.update(root.rglob("*.json"))
    for path in sorted(paths):
        if any(part in IGNORED_PARTS or part == "examples" for part in path.parts):
            continue
        value = _load_json(path)
        if isinstance(value, dict) and (
            value.get("schema") == "io.tobkiri.pack.v4"
            or value.get("pack_api_version") == "io.tobkiri.pack.v4"
        ):
            result.append(path)
    return result


def _v4_profile_artifacts() -> list[Path]:
    """Return checked-in production Profile documents carrying the v4 schema."""
    result: list[Path] = []
    roots = (
        ECOSYSTEM,
        RUNTIME / "profiles_v4",
        RUNTIME / "distributions",
    )
    paths: set[Path] = set()
    for root in roots:
        if root.is_dir():
            paths.update(root.rglob("*.yaml"))
            paths.update(root.rglob("*.yml"))
            paths.update(root.rglob("*.json"))
    for path in sorted(paths):
        if any(part in IGNORED_PARTS or part == "examples" for part in path.parts):
            continue
        value: Any
        try:
            value = (
                yaml.safe_load(path.read_text(encoding="utf-8", errors="replace"))
                if path.suffix.lower() in {".yaml", ".yml"}
                else _load_json(path)
            )
        except (OSError, yaml.YAMLError):
            continue
        if isinstance(value, Mapping) and (
            value.get("schema") == "io.tobkiri.profile.v4"
            or value.get("profile_api_version") == "io.tobkiri.profile.v4"
        ):
            result.append(path)
    return result


def _v4_pack_compliance_findings() -> list[dict[str, Any]]:
    """Return missing required v4 Pack fields without accepting partial manifests."""
    findings: list[dict[str, Any]] = []
    for path in _v4_pack_artifacts():
        value = _load_json(path)
        if not isinstance(value, Mapping):
            findings.append({"path": _relative(path), "line": 1, "text": "not an object"})
            continue
        if value.get("pack_api_version") == "io.tobkiri.pack.v4":
            required = ("pack_api_version", "pack", "functions", "contracts", "artifacts", "provenance", "migration")
        else:
            required = ("schema", "pack_id", "version", "kind")
        for key in required:
            if key not in value:
                findings.append(
                    {
                        "path": _relative(path),
                        "line": 1,
                        "text": f"missing required v4 Pack field: {key}",
                    }
                )
    return findings


def _v4_profile_shape_findings() -> list[dict[str, Any]]:
    """Require explicit base, shell, and conversation selections in v4 Profiles."""
    findings: list[dict[str, Any]] = []
    for path in _v4_profile_artifacts():
        try:
            value = (
                yaml.safe_load(path.read_text(encoding="utf-8", errors="replace"))
                if path.suffix.lower() in {".yaml", ".yml"}
                else _load_json(path)
            )
        except (OSError, yaml.YAMLError):
            value = None
        if not isinstance(value, Mapping):
            findings.append({"path": _relative(path), "line": 1, "text": "Profile is not an object"})
            continue
        if value.get("profile_api_version") == "io.tobkiri.profile.v4":
            required = ("profile_api_version", "state", "base", "packs", "requested_edges", "authority_references", "provenance")
        else:
            required = ("schema", "base", "shell", "packs", "conversation")
        for key in required:
            if key not in value:
                findings.append(
                    {
                        "path": _relative(path),
                        "line": 1,
                        "text": f"missing required v4 Profile field: {key}",
                    }
                )
        for key in ("base", "shell", "conversation"):
            if key in value and not isinstance(value[key], Mapping):
                findings.append(
                    {
                        "path": _relative(path),
                        "line": 1,
                        "text": f"v4 Profile selection {key!r} is not exactly one object",
                    }
                )
    return findings


def _manifest_authority_counts() -> tuple[Counter[str], list[dict[str, Any]]]:
    """Return exact installed Pack authority classification evidence."""
    catalog_path = RUNTIME / "schemas" / "manifest_authority.v1.json"
    catalog = _load_json(catalog_path)
    classified = catalog.get("packs", {}) if isinstance(catalog, dict) else {}
    pack_dirs = sorted(
        path
        for path in ECOSYSTEM.iterdir()
        if path.is_dir() and path.name != "setup_pack" and not path.name.startswith(".")
    )
    records = []
    for path in pack_dirs:
        legacy = path / "ecosystem.json"
        v3 = path / "rumi.pack.v3.json"
        records.append(
            {
                "pack_id": path.name,
                "classified_as": classified.get(path.name),
                "ecosystem_json": legacy.is_file(),
                "v3_manifest": v3.is_file(),
            }
        )
    return Counter(str(item["classified_as"]) for item in records), records


def _legacy_qualified_routes_and_functions() -> list[dict[str, Any]]:
    """Inventory legacy qualified route/function declarations in manifests."""
    findings: list[dict[str, Any]] = []
    qualified = re.compile(r"(?:defaultspack|defaults|[a-z0-9_]+_pack):[a-z][a-z0-9_.-]+")
    for path in _json_files():
        value = _load_json(path)
        if not isinstance(value, (dict, list)):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for line_number, line in enumerate(text.splitlines(), start=1):
            if "function_id" in line or "api_routes" in line or qualified.search(line):
                findings.append(
                    {
                        "path": _relative(path),
                        "line": line_number,
                        "text": line.strip()[:240],
                    }
                )
    return findings


def _ast_legacy_imports_and_calls() -> list[dict[str, Any]]:
    """Inventory legacy runtime imports/calls with AST evidence."""
    findings: list[dict[str, Any]] = []
    symbols = {
        "FunctionRegistry",
        "InterfaceRegistry",
        "CapabilityExecutor",
        "AuthorityService",
        "PermissionManager",
    }
    for path in _production_files():
        if path.suffix != ".py":
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (OSError, SyntaxError):
            continue
        for node in ast.walk(tree):
            hit = None
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = [alias.name for alias in node.names]
                if isinstance(node, ast.ImportFrom):
                    names.extend(alias.name for alias in node.names)
                hit = next((name for name in names if name in symbols), None)
            elif isinstance(node, ast.Call):
                name = node.func.id if isinstance(node.func, ast.Name) else ""
                if name in symbols:
                    hit = name
            if hit:
                findings.append(
                    {
                        "path": _relative(path),
                        "line": node.lineno,
                        "symbol": hit,
                    }
                )
    return findings


def _ast_legacy_call_graph_edges() -> list[dict[str, Any]]:
    """Return caller-to-legacy-symbol edges found by AST traversal."""
    findings: list[dict[str, Any]] = []
    symbols = {
        "FunctionRegistry",
        "InterfaceRegistry",
        "CapabilityExecutor",
        "AuthorityService",
        "PermissionManager",
    }
    for path in _production_files():
        if path.suffix != ".py":
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        except (OSError, SyntaxError):
            continue
        parents = {child: parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)}
        for node in ast.walk(tree):
            hit = None
            edge_kind = None
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                names = [alias.name for alias in node.names]
                if isinstance(node, ast.ImportFrom):
                    names.extend(alias.name for alias in node.names)
                hit = next((name for name in names if name in symbols), None)
                edge_kind = "import"
            elif isinstance(node, ast.Call):
                name = node.func.id if isinstance(node.func, ast.Name) else ""
                if name in symbols:
                    hit = name
                    edge_kind = "call"
            if not hit:
                continue
            owner: ast.AST = node
            while owner not in parents:
                break
            while owner in parents:
                owner = parents[owner]
                if isinstance(owner, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    break
            caller = (
                getattr(owner, "name", "<module>")
                if isinstance(owner, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                else "<module>"
            )
            findings.append(
                {
                    "path": _relative(path),
                    "line": node.lineno,
                    "caller": caller,
                    "callee": hit,
                    "kind": edge_kind,
                }
            )
    return findings


def _shell_artifact_findings() -> list[dict[str, Any]]:
    """Inventory direct shell launches and unverified v3 entrypoints."""
    findings = _lines_containing(DIRECT_SHELL_MARKERS)
    for path in _production_files():
        if path.name not in DIRECT_SHELL_LAUNCH_FILES:
            continue
        try:
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for line_number, line in enumerate(lines, start=1):
            hits = [marker for marker in DIRECT_SHELL_PROCESS_MARKERS if marker in line]
            if hits:
                findings.append(
                    {
                        "path": _relative(path),
                        "line": line_number,
                        "markers": hits,
                        "text": line.strip()[:240],
                    }
                )
    for path in sorted(ECOSYSTEM.glob("*/rumi.pack.v3.json")):
        value = _load_json(path)
        if not isinstance(value, dict):
            continue
        for entrypoint in value.get("entrypoints", []):
            if not isinstance(entrypoint, dict):
                continue
            if entrypoint.get("loader") == "python":
                findings.append(
                    {
                        "path": _relative(path),
                        "line": 1,
                        "markers": ["loader=python"],
                        "text": "v3 Python entrypoint is not a v4 verified PackVM/Wasm artifact",
                    }
                )
        provenance = value.get("provenance", {})
        if isinstance(provenance, dict) and provenance.get("signature") is None:
            findings.append(
                {
                    "path": _relative(path),
                    "line": 1,
                    "markers": ["provenance.signature=null"],
                    "text": "v3 artifact has no publisher signature",
                }
            )
    return findings


def _audit_snapshot() -> dict[str, Any]:
    """Collect the complete current-tree RED evidence without a baseline."""
    authority_counts, authority_records = _manifest_authority_counts()
    legacy_imports = _ast_legacy_imports_and_calls()
    legacy_call_graph = _ast_legacy_call_graph_edges()
    legacy_markers = _lines_containing(LEGACY_RUNTIME_MARKERS)
    authority_bypass = _lines_containing(AUTHORITY_BYPASS_MARKERS)
    old_composition = _lines_containing(OLD_COMPOSITION_MARKERS)
    projection_runtime_calls = _lines_containing(PROJECTION_RUNTIME_MARKERS)
    installed_scan = _lines_containing(INSTALLED_SCAN_MARKERS)
    fallback_promotion = _lines_containing(IMPLICIT_FALLBACK_MARKERS)
    shell = _shell_artifact_findings()
    qualified = _legacy_qualified_routes_and_functions()
    pack_compliance = _v4_pack_compliance_findings()
    profile_shape = _v4_profile_shape_findings()
    defaults_dir = ECOSYSTEM / "defaults"
    defaultspack_dir = ECOSYSTEM / "defaultspack"
    double_authority = []
    if defaults_dir.is_dir() and defaultspack_dir.is_dir():
        double_authority.append(
            {
                "path": "tobkiri_runtime/ecosystem",
                "line": 1,
                "text": "both defaults and defaultspack production roots exist",
            }
        )
        default_files = {
            path.relative_to(defaults_dir).as_posix()
            for path in defaults_dir.rglob("*")
            if path.is_file()
        }
        defaultspack_files = {
            path.relative_to(defaultspack_dir).as_posix()
            for path in defaultspack_dir.rglob("*")
            if path.is_file()
        }
        double_authority.append(
            {
                "path": "tobkiri_runtime/ecosystem/defaults",
                "line": 1,
                "text": f"overlapping relative files={len(default_files & defaultspack_files)}",
            }
        )
    status = "GREEN"
    if any(
        (
            len(_v4_pack_artifacts()) != EXPECTED_PRODUCTION_PACK_COUNT,
            not _v4_profile_artifacts(),
            authority_counts != Counter(EXPECTED_AUTHORITY_COUNTS),
            len(authority_records) != EXPECTED_PRODUCTION_PACK_COUNT,
            legacy_imports,
            legacy_call_graph,
            legacy_markers,
            authority_bypass,
            old_composition,
            projection_runtime_calls,
            installed_scan,
            fallback_promotion,
            double_authority,
            shell,
            qualified,
            pack_compliance,
            profile_shape,
        )
    ):
        status = "RED"
    return {
        "schema": "io.tobkiri.quality.complete-v4-migration.v1",
        "start_sha": START_SHA,
        "head_sha": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "gate": {
            "status": status,
            "expected_green": {
                "v4_pack_artifacts": EXPECTED_PRODUCTION_PACK_COUNT,
                "v4_profile_artifacts": ">=1",
                "v4_pack_manifest_compliance": 0,
                "v4_profile_selection_shape": 0,
                "authority_classification": dict(EXPECTED_AUTHORITY_COUNTS),
                "production_pack_directories": EXPECTED_PRODUCTION_PACK_COUNT,
                "legacy_runtime_imports_or_calls": 0,
                "legacy_call_graph_edges": 0,
                "legacy_runtime_markers": 0,
                "authority_bypass": 0,
                "old_composition_schema_usage": 0,
                "runtime_projection_calls": 0,
                "installed_pack_scans": 0,
                "implicit_fallback_or_promotion": 0,
                "defaults_double_authority": 0,
                "direct_or_unverified_shell_launch": 0,
                "legacy_qualified_routes_or_functions": 0,
            },
            "clean": status == "GREEN",
        },
        "pack_inventory": {
            "production_pack_directories": len(authority_records),
            "authority_counts": dict(sorted(authority_counts.items())),
            "records": authority_records,
            "v4_pack_artifacts": [_relative(path) for path in _v4_pack_artifacts()],
            "v4_profile_artifacts": [_relative(path) for path in _v4_profile_artifacts()],
            "v4_pack_manifest_compliance": pack_compliance,
            "v4_profile_selection_shape": profile_shape,
        },
        "findings": {
            "legacy_runtime_imports_or_calls": legacy_imports,
            "legacy_call_graph_edges": legacy_call_graph,
            "legacy_runtime_markers": legacy_markers,
            "authority_bypass": authority_bypass,
            "old_composition_schema_usage": old_composition,
            "runtime_projection_calls": projection_runtime_calls,
            "installed_pack_scans": installed_scan,
            "implicit_fallback_or_promotion": fallback_promotion,
            "defaults_double_authority": double_authority,
            "direct_or_unverified_shell_launch": shell,
            "legacy_qualified_routes_or_functions": qualified,
        },
    }


def _assert_zero(name: str, findings: list[dict[str, Any]]) -> None:
    """Fail with deterministic count and sample evidence; never baseline it."""
    assert not findings, f"{name} RED: count={len(findings)} evidence={findings[:8]}"


def test_production_v4_pack_and_profile_artifacts_are_complete() -> None:
    """Every shipped Pack must have a v4 artifact and an explicit v4 Profile."""
    packs = _v4_pack_artifacts()
    profiles = _v4_profile_artifacts()
    assert len(packs) == EXPECTED_PRODUCTION_PACK_COUNT, (
        "v4 Pack artifacts RED: "
        f"count={len(packs)} expected={EXPECTED_PRODUCTION_PACK_COUNT}"
    )
    assert profiles, "v4 Profile artifacts RED: count=0 expected>=1"


def test_all_141_packs_have_exact_authority_classification() -> None:
    """The complete installed Pack set has one explicit authority owner each."""
    counts, records = _manifest_authority_counts()
    assert len(records) == EXPECTED_PRODUCTION_PACK_COUNT, (
        f"Pack authority inventory RED: count={len(records)} "
        f"expected={EXPECTED_PRODUCTION_PACK_COUNT}"
    )
    assert counts == Counter(EXPECTED_AUTHORITY_COUNTS), (
        f"Pack authority classification RED: counts={dict(counts)} "
        f"expected={EXPECTED_AUTHORITY_COUNTS}"
    )


def test_v4_pack_and_profile_artifacts_are_contract_complete() -> None:
    """v4 artifacts cannot be counted as migrated while required fields are absent."""
    _assert_zero("v4 Pack/Profile contract compliance", _v4_pack_compliance_findings())
    _assert_zero("v4 Profile explicit selections", _v4_profile_shape_findings())


def test_legacy_runtime_imports_and_calls_are_zero() -> None:
    """Legacy Registry/authority execution symbols must not remain reachable."""
    _assert_zero("legacy runtime imports/calls", _ast_legacy_imports_and_calls())
    _assert_zero("legacy runtime call graph", _ast_legacy_call_graph_edges())
    _assert_zero("legacy runtime marker", _lines_containing(LEGACY_RUNTIME_MARKERS))


def test_authority_kernel_bypass_is_zero() -> None:
    """Only the v4 Authority Kernel may make production authority decisions."""
    _assert_zero("Authority Kernel bypass", _lines_containing(AUTHORITY_BYPASS_MARKERS))


def test_runtime_legacy_projection_and_installed_scan_are_zero() -> None:
    """Projection is offline-only and runtime selection never scans installed Packs."""
    _assert_zero("runtime legacy projection", _lines_containing(PROJECTION_RUNTIME_MARKERS))
    _assert_zero("all-installed Pack scan", _lines_containing(INSTALLED_SCAN_MARKERS))


def test_implicit_fallback_and_promotion_are_zero() -> None:
    """Profile/Pack selection must fail closed instead of falling back or promoting."""
    _assert_zero("implicit fallback/promotion", _lines_containing(IMPLICIT_FALLBACK_MARKERS))


def test_old_base_shell_and_profile_schema_usage_is_zero() -> None:
    """Legacy composition fields and v1/v3 schema names are not runtime input."""
    _assert_zero("old Base/Shell/Profile schema usage", _lines_containing(OLD_COMPOSITION_MARKERS))


def test_defaults_and_defaultspack_do_not_have_double_authority() -> None:
    """Defaults backend state and routing must have one owner."""
    defaults = ECOSYSTEM / "defaults"
    defaultspack = ECOSYSTEM / "defaultspack"
    findings: list[dict[str, Any]] = []
    if defaults.is_dir() and defaultspack.is_dir():
        findings.append({"path": _relative(defaults), "line": 1, "text": "duplicate authority roots"})
    _assert_zero("defaults/defaultspack double authority", findings)


def test_direct_and_unverified_shell_launch_is_zero() -> None:
    """Production never launches arbitrary commands or unverified v3 Python."""
    _assert_zero("direct/unverified shell launch", _shell_artifact_findings())


def test_legacy_qualified_routes_and_functions_are_zero() -> None:
    """Pack-qualified legacy route/function names are not public runtime APIs."""
    _assert_zero("legacy qualified routes/functions", _legacy_qualified_routes_and_functions())


def test_new_v4_profile_resolver_and_shell_contract_are_live() -> None:
    """Exercise the new Profile/Base/Shell path, including exact provider choice."""
    pack_root = RUNTIME / "ecosystem" / "defaultspack"
    if str(pack_root) not in sys.path:
        sys.path.insert(0, str(pack_root))
    from domain.pack_architecture import PackCatalog, resolve_profile  # noqa: PLC0415

    catalog = PackCatalog.from_assets_root(
        pack_root / "domain" / "pack_architecture" / "assets"
    )
    profile_path = pack_root / "profiles" / "defaults-modern-cli.profile.yaml"
    profile = yaml.safe_load(profile_path.read_text(encoding="utf-8"))
    resolved = resolve_profile(profile, catalog)
    assert resolved.base_pack_id == "defaults-basepack"
    assert resolved.shell_contract == "app.shell.v1"
    assert resolved.shell_provider_id == "shell.cli.default"
    assert resolved.backend_identity == ("defaultspack",)
    assert all(
        item.presentation_family == "terminal"
        for item in resolved.selected_contributions
    )


def test_current_sha_red_evidence_has_a_clean_green_target() -> None:
    """Keep the migration handoff explicit: current evidence RED, target clean."""
    report = _audit_snapshot()
    assert report["start_sha"] == START_SHA
    assert report["gate"]["status"] == "RED"
    assert report["gate"]["clean"] is False
    assert report["gate"]["expected_green"]["v4_pack_artifacts"] == 141
    assert report["gate"]["expected_green"]["v4_profile_artifacts"] == ">=1"
    assert report["gate"]["expected_green"]["legacy_call_graph_edges"] == 0
