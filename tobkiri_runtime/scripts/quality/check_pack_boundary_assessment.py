#!/usr/bin/env python3
"""Validate the non-runtime Pack boundary assessment inventory.

This checker intentionally mirrors only the *filesystem discovery contract* of
the runtime. It does not import ``core_runtime``: an architecture-review tool
must not become another caller of, or dependency of, production Pack loading.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

REPO_ROOT = Path(__file__).resolve().parents[3]
RUNTIME_ROOT = REPO_ROOT / "tobkiri_runtime"
ASSESSMENT_PATH = RUNTIME_ROOT / "docs" / "status" / "pack-boundary-assessment.v1.json"
SCHEMA_VERSION = "tobkiri.pack-boundary-assessment.v1"
DOCUMENT_ROLE = "non_normative_architecture_review"
ASSESSMENT_FILENAME = ASSESSMENT_PATH.name

# These values correspond one-to-one with the five criteria in ADR 0001.
BOUNDARY_CRITERIA = frozenset(
    {
        "independent_lifecycle",
        "trust_or_authority_boundary",
        "meaningful_isolation",
        "independently_migrated_state",
        "third_party_replaceability",
    }
)
UNRESOLVED_VALUES = {"unknown", "unresolved", "undecided"}
REQUIRED_RECORD_FIELDS = {
    "observed_pack_id",
    "manifest_path",
    "review_status",
    "lifecycle_owner",
    "state_owner",
    "external_effects",
    "trust_domain",
    "execution_mode",
    "canonical_owner",
    "disposition",
    "deprecated_ids",
    "removal_phase",
    "boundary_criteria",
    "assessment_justification",
    "evidence",
}

# ``paths.discover_pack_locations`` uses this fuller list for ecosystem packs.
ECOSYSTEM_EXCLUDED_DIRS = frozenset(
    {
        ".git",
        "__pycache__",
        "node_modules",
        ".venv",
        ".tox",
        ".mypy_cache",
        ".pytest_cache",
        ".eggs",
        "packs",
        "flows",
        "setup_pack",
    }
)
# ``backend_core.ecosystem.registry`` uses this candidate list for core packs.
CORE_PACK_EXCLUDED_DIRS = frozenset(
    {
        ".git",
        "__pycache__",
        "node_modules",
        ".venv",
        "packs",
        "flows",
        "setup_pack",
    }
)

# A static, intentionally bounded non-consumption guard. Vendor and generated
# outputs are excluded; this is not proof against dynamic or external loading.
PRODUCTION_GUARD_ROOTS = (
    Path("tobkiri_runtime"),
    Path("tobkiri_launcher"),
    Path(".github"),
)
PRODUCTION_GUARD_SUFFIXES = frozenset(
    {
        ".py",
        ".pyi",
        ".js",
        ".mjs",
        ".cjs",
        ".ts",
        ".tsx",
        ".rs",
        ".json",
        ".toml",
        ".yaml",
        ".yml",
    }
)
PRODUCTION_GUARD_EXCLUDED_PARTS = frozenset(
    {
        ".git",
        "__pycache__",
        ".mypy_cache",
        ".pytest_cache",
        ".venv",
        "node_modules",
        "target",
        "dist",
        "build",
        "generated",
        "coverage",
        "docs",
        "tests",
        "test",
    }
)
FORBIDDEN_CONSUMPTION_TOKENS = frozenset(
    {ASSESSMENT_FILENAME, SCHEMA_VERSION, DOCUMENT_ROLE}
)


@dataclass(frozen=True)
class AssessmentPackLocation:
    """A physical Pack location found with the runtime's search semantics."""

    pack_dir: Path
    pack_id: str
    ecosystem_json_path: Path
    pack_subdir: Path
    is_legacy: bool = False
    is_core: bool = False


def find_ecosystem_json(
    pack_dir: Path, excluded_dirs: frozenset[str]
) -> tuple[Path | None, Path | None]:
    """Find a direct manifest first, then the first eligible child manifest."""
    if not pack_dir.is_dir():
        return None, None

    direct = pack_dir / "ecosystem.json"
    if direct.is_file():
        return direct, pack_dir

    try:
        children = sorted(
            (
                child
                for child in pack_dir.iterdir()
                if child.is_dir()
                and child.name not in excluded_dirs
                and not child.name.startswith(".")
            ),
            key=lambda child: child.name,
        )
    except OSError:
        return None, None

    for child in children:
        candidate = child / "ecosystem.json"
        if candidate.is_file():
            return candidate, child
    return None, None


def _candidate_dirs(root: Path, excluded_dirs: frozenset[str]) -> list[Path]:
    """Return immediate non-hidden candidate Pack directories in name order."""
    if not root.is_dir():
        return []
    try:
        return sorted(
            (
                child
                for child in root.iterdir()
                if child.is_dir()
                and child.name not in excluded_dirs
                and not child.name.startswith(".")
            ),
            key=lambda child: child.name,
        )
    except OSError:
        return []


def discover_pack_locations(
    repo_root: Path = REPO_ROOT,
) -> list[AssessmentPackLocation]:
    """Discover assessment rows with runtime Pack search precedence.

    The ecosystem search follows ``core_runtime.paths.discover_pack_locations``:
    direct manifest first, then a sorted eligible child; normal
    ``ecosystem/<pack>`` wins over the same ``ecosystem/packs/<pack>`` legacy
    directory. Core Pack discovery follows the registry's equivalent direct /
    child search. This is a local copy of the discovery shape, not a runtime
    import or an assertion that these locations form a supported architecture.
    """
    root = repo_root.resolve()
    runtime_root = root / "tobkiri_runtime"
    ecosystem_root = runtime_root / "ecosystem"
    core_pack_root = runtime_root / "core_runtime" / "core_pack"
    found: list[AssessmentPackLocation] = []

    # The registry loads shipped core packs before ecosystem packs. Keep those
    # physical entries distinct from similarly named third-party directories.
    for pack_dir in _candidate_dirs(core_pack_root, CORE_PACK_EXCLUDED_DIRS):
        manifest, subdir = find_ecosystem_json(pack_dir, ECOSYSTEM_EXCLUDED_DIRS)
        if manifest is not None and subdir is not None:
            found.append(
                AssessmentPackLocation(
                    pack_dir=pack_dir,
                    pack_id=pack_dir.name,
                    ecosystem_json_path=manifest,
                    pack_subdir=subdir,
                    is_core=True,
                )
            )

    ecosystem_names: set[str] = set()
    for pack_dir in _candidate_dirs(ecosystem_root, ECOSYSTEM_EXCLUDED_DIRS):
        manifest, subdir = find_ecosystem_json(pack_dir, ECOSYSTEM_EXCLUDED_DIRS)
        if manifest is None or subdir is None:
            continue
        ecosystem_names.add(pack_dir.name)
        found.append(
            AssessmentPackLocation(
                pack_dir=pack_dir,
                pack_id=pack_dir.name,
                ecosystem_json_path=manifest,
                pack_subdir=subdir,
            )
        )

    legacy_root = ecosystem_root / "packs"
    for pack_dir in _candidate_dirs(legacy_root, ECOSYSTEM_EXCLUDED_DIRS):
        if pack_dir.name in ecosystem_names:
            continue
        manifest, subdir = find_ecosystem_json(pack_dir, ECOSYSTEM_EXCLUDED_DIRS)
        if manifest is not None and subdir is not None:
            found.append(
                AssessmentPackLocation(
                    pack_dir=pack_dir,
                    pack_id=pack_dir.name,
                    ecosystem_json_path=manifest,
                    pack_subdir=subdir,
                    is_legacy=True,
                )
            )

    return sorted(
        found,
        key=lambda location: _relative(location.ecosystem_json_path, root),
    )


def discover_pack_manifests(repo_root: Path = REPO_ROOT) -> list[Path]:
    """Return Pack manifests using :func:`discover_pack_locations` semantics."""
    return [
        location.ecosystem_json_path for location in discover_pack_locations(repo_root)
    ]


def _relative(path: Path, repo_root: Path) -> str:
    return path.resolve().relative_to(repo_root.resolve()).as_posix()


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _evidence_item(path: Path, repo_root: Path) -> dict[str, str]:
    return {"path": _relative(path, repo_root), "sha256": _digest(path)}


def new_record(
    location: AssessmentPackLocation, repo_root: Path = REPO_ROOT
) -> dict[str, Any]:
    """Build a schema-shaped, explicitly unresolved assessment row."""
    manifest_path = _relative(location.ecosystem_json_path, repo_root)
    return {
        "observed_pack_id": location.pack_id,
        "manifest_path": manifest_path,
        "review_status": "unreviewed",
        "lifecycle_owner": "unknown",
        "state_owner": "unknown",
        "external_effects": ["unknown"],
        "trust_domain": "unknown",
        "execution_mode": "unknown",
        "canonical_owner": "unresolved",
        "disposition": "undecided",
        "deprecated_ids": [],
        "removal_phase": None,
        "boundary_criteria": [],
        "assessment_justification": "",
        "evidence": [_evidence_item(location.ecosystem_json_path, repo_root)],
    }


def _reviewed_record_is_current(
    record: dict[str, Any], location: AssessmentPackLocation, repo_root: Path
) -> bool:
    """Return whether a reviewed row still binds to its current evidence."""
    manifest_path = _relative(location.ecosystem_json_path, repo_root)
    if record.get("observed_pack_id") != location.pack_id:
        return False
    if record.get("manifest_path") != manifest_path:
        return False
    errors: list[str] = []
    _validate_evidence(repo_root, "reviewed record", record.get("evidence"), errors)
    return not errors


def render_assessment(
    repo_root: Path = REPO_ROOT, existing: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Render the inventory, resetting stale reviewed rows to ``unreviewed``.

    A reviewed decision survives regeneration only when its selected manifest and
    every evidence digest still match. An evidence or manifest modification
    therefore requires a fresh review rather than silently carrying forward a
    decision made against older bytes.
    """
    previous: dict[str, dict[str, Any]] = {}
    if isinstance(existing, dict) and isinstance(existing.get("records"), list):
        previous = {
            row.get("manifest_path"): row
            for row in existing["records"]
            if isinstance(row, dict) and isinstance(row.get("manifest_path"), str)
        }

    rows: list[dict[str, Any]] = []
    for location in discover_pack_locations(repo_root):
        default = new_record(location, repo_root)
        old = previous.get(default["manifest_path"])
        if (
            isinstance(old, dict)
            and old.get("review_status") != "unreviewed"
            and _reviewed_record_is_current(old, location, repo_root)
        ):
            rows.append(old)
        else:
            rows.append(default)
    rows.sort(key=lambda row: (row["manifest_path"], row["observed_pack_id"]))
    return {
        "schema_version": SCHEMA_VERSION,
        "document_role": DOCUMENT_ROLE,
        "runtime_authority": False,
        "activation_input": False,
        "decision_status": "draft",
        "records": rows,
    }


def _validate_evidence(
    repo_root: Path, record_label: str, evidence: object, errors: list[str]
) -> None:
    """Validate that every evidence item exists and remains content-bound."""
    if not isinstance(evidence, list) or not evidence:
        errors.append(f"{record_label}: evidence must be a non-empty list")
        return
    root = repo_root.resolve()
    for index, item in enumerate(evidence):
        item_label = f"{record_label}: evidence[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{item_label} must be an object with path and sha256")
            continue
        path_value = item.get("path")
        digest = item.get("sha256")
        if not isinstance(path_value, str) or not path_value.strip():
            errors.append(f"{item_label}.path must be a non-empty path")
            continue
        if not isinstance(digest, str) or len(digest) != 64:
            errors.append(f"{item_label}.sha256 must be a SHA-256 digest")
            continue
        candidate = (root / path_value).resolve()
        try:
            candidate.relative_to(root)
        except ValueError:
            errors.append(f"{item_label}.path escapes repository: {path_value}")
            continue
        if not candidate.is_file():
            errors.append(f"{item_label}.path does not exist: {path_value}")
            continue
        if _digest(candidate) != digest:
            errors.append(f"{item_label}.sha256 does not match current file")


def _validate_record(
    repo_root: Path, index: int, row: object, errors: list[str]
) -> tuple[str, str] | None:
    """Validate one inventory row and return its identity pair when valid."""
    label = f"records[{index}]"
    if not isinstance(row, dict):
        errors.append(f"{label} must be an object")
        return None
    missing = sorted(REQUIRED_RECORD_FIELDS - row.keys())
    if missing:
        errors.append(f"{label}: missing fields: {', '.join(missing)}")
        return None

    pack_id = row.get("observed_pack_id")
    manifest_path = row.get("manifest_path")
    if not isinstance(pack_id, str) or not pack_id.strip():
        errors.append(f"{label}: observed_pack_id must be non-empty")
    if not isinstance(manifest_path, str) or not manifest_path.strip():
        errors.append(f"{label}: manifest_path must be non-empty")

    review_status = row.get("review_status")
    if review_status not in {"unreviewed", "proposed", "accepted", "rejected"}:
        errors.append(f"{label}: invalid review_status")
    disposition = row.get("disposition")
    if disposition not in {
        "undecided",
        "keep",
        "merge",
        "module",
        "resource",
        "compatibility",
        "delete",
    }:
        errors.append(f"{label}: invalid disposition")

    for field in (
        "lifecycle_owner",
        "state_owner",
        "trust_domain",
        "execution_mode",
        "canonical_owner",
    ):
        if not isinstance(row.get(field), str) or not row[field].strip():
            errors.append(f"{label}: {field} must be a non-empty string")

    for field in ("external_effects", "deprecated_ids", "boundary_criteria"):
        value = row.get(field)
        if not isinstance(value, list) or any(
            not isinstance(item, str) or not item.strip() for item in value
        ):
            errors.append(f"{label}: {field} must contain non-empty strings")
    criteria = row.get("boundary_criteria")
    if isinstance(criteria, list):
        if len(criteria) != len(set(criteria)):
            errors.append(f"{label}: boundary_criteria must not contain duplicates")
        unsupported = sorted(set(criteria) - BOUNDARY_CRITERIA)
        if unsupported:
            errors.append(f"{label}: unsupported boundary_criteria: {unsupported}")

    justification = row.get("assessment_justification")
    if not isinstance(justification, str):
        errors.append(f"{label}: assessment_justification must be a string")

    if review_status == "accepted":
        for field in (
            "lifecycle_owner",
            "state_owner",
            "trust_domain",
            "execution_mode",
            "canonical_owner",
            "disposition",
        ):
            if row.get(field) in UNRESOLVED_VALUES:
                errors.append(f"{label}: accepted row has unresolved {field}")
        if "unknown" in row.get("external_effects", []):
            errors.append(f"{label}: accepted row has unresolved external_effects")
        if not isinstance(criteria, list) or not criteria:
            errors.append(f"{label}: accepted row requires boundary_criteria")
        if not isinstance(justification, str) or not justification.strip():
            errors.append(f"{label}: accepted row requires assessment_justification")
        evidence = row.get("evidence")
        supporting_paths = (
            {item.get("path") for item in evidence if isinstance(item, dict)}
            if isinstance(evidence, list)
            else set()
        )
        manifest_token = manifest_path if isinstance(manifest_path, str) else None
        if supporting_paths <= {manifest_token}:
            errors.append(
                f"{label}: accepted row requires evidence beyond its manifest"
            )

    removal_phase = row.get("removal_phase")
    if removal_phase is not None:
        if not isinstance(removal_phase, str) or not removal_phase.strip():
            errors.append(f"{label}: removal_phase must be null or non-empty")
        if not row.get("deprecated_ids"):
            errors.append(f"{label}: removal_phase requires deprecated_ids")
        if disposition in {"undecided", "keep"}:
            errors.append(f"{label}: removal_phase requires a removal disposition")

    _validate_evidence(repo_root, label, row.get("evidence"), errors)
    if isinstance(pack_id, str) and isinstance(manifest_path, str):
        return pack_id, manifest_path
    return None


def validate_assessment(
    payload: object,
    repo_root: Path = REPO_ROOT,
    locations: Iterable[AssessmentPackLocation] | None = None,
) -> list[str]:
    """Return contract violations in an assessment payload."""
    if not isinstance(payload, dict):
        return ["assessment root must be an object"]

    errors: list[str] = []
    expected_header = {
        "schema_version": SCHEMA_VERSION,
        "document_role": DOCUMENT_ROLE,
        "runtime_authority": False,
        "activation_input": False,
        "decision_status": "draft",
    }
    for field, expected in expected_header.items():
        if payload.get(field) != expected:
            errors.append(f"{field} must be {expected!r}")

    records = payload.get("records")
    if not isinstance(records, list):
        return [*errors, "records must be a list"]

    actual_locations = list(
        discover_pack_locations(repo_root) if locations is None else locations
    )
    expected_pairs = {
        (location.pack_id, _relative(location.ecosystem_json_path, repo_root))
        for location in actual_locations
    }
    observed_pairs = [
        pair
        for index, row in enumerate(records)
        if (pair := _validate_record(repo_root, index, row, errors)) is not None
    ]
    if len(observed_pairs) != len(set(observed_pairs)):
        errors.append("records must not contain duplicate Pack/manifest pairs")
    if observed_pairs != sorted(observed_pairs, key=lambda item: (item[1], item[0])):
        errors.append("records must be sorted by manifest_path and observed_pack_id")
    if set(observed_pairs) != expected_pairs:
        missing = sorted(expected_pairs - set(observed_pairs))
        extra = sorted(set(observed_pairs) - expected_pairs)
        if missing:
            errors.append(f"assessment is missing discovered manifests: {missing}")
        if extra:
            errors.append(f"assessment has stale manifest rows: {extra}")
    return errors


def _is_guard_candidate(path: Path, repo_root: Path) -> bool:
    """Return whether a production file is covered by the static guard."""
    try:
        relative = path.resolve().relative_to(repo_root.resolve())
    except ValueError:
        return False
    if path.suffix not in PRODUCTION_GUARD_SUFFIXES:
        return False
    if any(part in PRODUCTION_GUARD_EXCLUDED_PARTS for part in relative.parts):
        return False
    return relative.as_posix() != (
        "tobkiri_runtime/scripts/quality/check_pack_boundary_assessment.py"
    )


def find_runtime_references(repo_root: Path = REPO_ROOT) -> list[str]:
    """Find static assessment-token consumption in covered production files.

    This checks source/config files under ``tobkiri_runtime``,
    ``tobkiri_launcher``, and ``.github`` with the extensions listed in
    :data:`PRODUCTION_GUARD_SUFFIXES`. Documentation, tests, and generated or
    vendor directories are intentionally out of scope, so this is a drift guard
    rather than a claim to prove the absence of every dynamic consumption path.
    """
    root = repo_root.resolve()
    references: list[str] = []
    for relative_root in PRODUCTION_GUARD_ROOTS:
        scan_root = root / relative_root
        if not scan_root.exists():
            continue
        for candidate in scan_root.rglob("*"):
            if not candidate.is_file() or not _is_guard_candidate(candidate, root):
                continue
            try:
                contents = candidate.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            tokens = sorted(
                token for token in FORBIDDEN_CONSUMPTION_TOKENS if token in contents
            )
            if tokens:
                references.append(f"{_relative(candidate, root)} ({', '.join(tokens)})")
    return sorted(references)


def _load_existing(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return payload if isinstance(payload, dict) else None


def main() -> int:
    """Check or regenerate the assessment inventory."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--write", action="store_true", help="update the inventory before checking"
    )
    args = parser.parse_args()

    if args.write:
        payload = render_assessment(REPO_ROOT, _load_existing(ASSESSMENT_PATH))
        ASSESSMENT_PATH.parent.mkdir(parents=True, exist_ok=True)
        ASSESSMENT_PATH.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    try:
        payload = json.loads(ASSESSMENT_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"pack boundary assessment: {exc}")
        return 1

    errors = validate_assessment(payload)
    references = find_runtime_references()
    if references:
        errors.append(f"production source/config references assessment: {references}")
    if errors:
        for error in errors:
            print(f"pack boundary assessment: {error}")
        return 1
    print(f"pack boundary assessment: ok ({len(payload['records'])} manifests)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
