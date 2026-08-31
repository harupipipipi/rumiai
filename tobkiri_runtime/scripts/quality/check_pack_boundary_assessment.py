#!/usr/bin/env python3
"""Validate the non-runtime Pack boundary assessment inventory."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Iterable

REPO_ROOT = Path(__file__).resolve().parents[3]
RUNTIME_ROOT = REPO_ROOT / "tobkiri_runtime"
ASSESSMENT_PATH = RUNTIME_ROOT / "docs" / "status" / "pack-boundary-assessment.v1.json"
SCHEMA_VERSION = "tobkiri.pack-boundary-assessment.v1"
ASSESSMENT_FILENAME = ASSESSMENT_PATH.name

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
    "evidence",
}
UNRESOLVED_VALUES = {"unknown", "unresolved", "undecided"}


def discover_pack_manifests(repo_root: Path = REPO_ROOT) -> list[Path]:
    """Return runtime Pack manifests, excluding docs, tests, and templates."""
    runtime_root = repo_root / "tobkiri_runtime"
    patterns = (
        "ecosystem/*/ecosystem.json",
        "core_runtime/core_pack/*/ecosystem.json",
        "core_runtime/core_pack/*/backend/ecosystem.json",
    )
    return sorted(
        {path.resolve() for pattern in patterns for path in runtime_root.glob(pattern)},
        key=lambda path: path.relative_to(repo_root.resolve()).as_posix(),
    )


def _relative(path: Path, repo_root: Path) -> str:
    return path.resolve().relative_to(repo_root.resolve()).as_posix()


def _manifest_id(path: Path) -> str:
    payload = json.loads(path.read_text(encoding="utf-8"))
    pack_id = payload.get("pack_id")
    if not isinstance(pack_id, str) or not pack_id.strip():
        raise ValueError(f"manifest has no non-empty pack_id: {path}")
    return pack_id.strip()


def new_record(path: Path, repo_root: Path = REPO_ROOT) -> dict[str, Any]:
    """Build an unresolved assessment row for a discovered Pack manifest."""
    manifest_path = _relative(path, repo_root)
    return {
        "observed_pack_id": _manifest_id(path),
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
        "evidence": [manifest_path],
    }


def render_assessment(
    repo_root: Path = REPO_ROOT, existing: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Render the inventory while preserving existing rows by manifest path."""
    previous: dict[str, dict[str, Any]] = {}
    if isinstance(existing, dict):
        records = existing.get("records")
        if isinstance(records, list):
            previous = {
                row.get("manifest_path"): row
                for row in records
                if isinstance(row, dict) and isinstance(row.get("manifest_path"), str)
            }

    rows = []
    for path in discover_pack_manifests(repo_root):
        default = new_record(path, repo_root)
        old = previous.get(default["manifest_path"])
        if (
            isinstance(old, dict)
            and old.get("observed_pack_id") == default["observed_pack_id"]
            and old.get("review_status") != "unreviewed"
        ):
            rows.append(old)
        else:
            rows.append(default)
    rows.sort(key=lambda row: (row["manifest_path"], row["observed_pack_id"]))
    return {
        "schema_version": SCHEMA_VERSION,
        "document_role": "non_normative_architecture_review",
        "runtime_authority": False,
        "activation_input": False,
        "decision_status": "draft",
        "records": rows,
    }


def _validate_evidence(
    repo_root: Path, record_label: str, evidence: object, errors: list[str]
) -> None:
    if not isinstance(evidence, list) or not evidence:
        errors.append(f"{record_label}: evidence must be a non-empty list")
        return
    root = repo_root.resolve()
    for index, item in enumerate(evidence):
        if not isinstance(item, str) or not item.strip():
            errors.append(f"{record_label}: evidence[{index}] must be a path")
            continue
        candidate = (root / item).resolve()
        try:
            candidate.relative_to(root)
        except ValueError:
            errors.append(f"{record_label}: evidence escapes repository: {item}")
            continue
        if not candidate.exists():
            errors.append(f"{record_label}: evidence does not exist: {item}")


def validate_assessment(
    payload: object,
    repo_root: Path = REPO_ROOT,
    manifests: Iterable[Path] | None = None,
) -> list[str]:
    """Return contract violations in an assessment payload."""
    if not isinstance(payload, dict):
        return ["assessment root must be an object"]

    errors: list[str] = []
    expected_header = {
        "schema_version": SCHEMA_VERSION,
        "document_role": "non_normative_architecture_review",
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

    actual_manifests = list(
        discover_pack_manifests(repo_root) if manifests is None else manifests
    )
    expected_pairs = {
        (_manifest_id(path), _relative(path, repo_root)) for path in actual_manifests
    }
    observed_pairs: list[tuple[str, str]] = []

    for index, row in enumerate(records):
        label = f"records[{index}]"
        if not isinstance(row, dict):
            errors.append(f"{label} must be an object")
            continue
        missing = sorted(REQUIRED_RECORD_FIELDS - row.keys())
        if missing:
            errors.append(f"{label}: missing fields: {', '.join(missing)}")
            continue

        pack_id = row.get("observed_pack_id")
        manifest_path = row.get("manifest_path")
        if not isinstance(pack_id, str) or not pack_id.strip():
            errors.append(f"{label}: observed_pack_id must be non-empty")
        if not isinstance(manifest_path, str) or not manifest_path.strip():
            errors.append(f"{label}: manifest_path must be non-empty")
        if isinstance(pack_id, str) and isinstance(manifest_path, str):
            observed_pairs.append((pack_id, manifest_path))

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

        for field in ("external_effects", "deprecated_ids"):
            value = row.get(field)
            if not isinstance(value, list) or any(
                not isinstance(item, str) or not item.strip() for item in value
            ):
                errors.append(f"{label}: {field} must contain non-empty strings")

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

        removal_phase = row.get("removal_phase")
        if removal_phase is not None:
            if not isinstance(removal_phase, str) or not removal_phase.strip():
                errors.append(f"{label}: removal_phase must be null or non-empty")
            if not row.get("deprecated_ids"):
                errors.append(f"{label}: removal_phase requires deprecated_ids")
            if disposition in {"undecided", "keep"}:
                errors.append(f"{label}: removal_phase requires a removal disposition")

        _validate_evidence(repo_root, label, row.get("evidence"), errors)

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


def find_runtime_references(repo_root: Path = REPO_ROOT) -> list[str]:
    """Find production Python code that attempts to consume the assessment."""
    runtime_root = repo_root / "tobkiri_runtime"
    roots = (
        runtime_root / "core_runtime",
        runtime_root / "backend_core",
        runtime_root / "ecosystem",
    )
    references = []
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*.py"):
            if ASSESSMENT_FILENAME in path.read_text(encoding="utf-8"):
                references.append(_relative(path, repo_root))
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
        errors.append(f"production runtime references assessment: {references}")
    if errors:
        for error in errors:
            print(f"pack boundary assessment: {error}")
        return 1
    print(f"pack boundary assessment: ok ({len(payload['records'])} manifests)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
