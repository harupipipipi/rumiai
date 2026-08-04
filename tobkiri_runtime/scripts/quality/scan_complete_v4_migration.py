#!/usr/bin/env python3
"""Emit the non-negotiable complete-v4 migration gate evidence.

The scanner delegates the repository inventory rules to the dedicated test
module so the CI gate and the handoff evidence cannot drift apart.  It has no
historical exception input: every finding is measured against the v4 target.
"""

from __future__ import annotations

import argparse
import ast
import importlib.util
import json
import sys
from pathlib import Path
from types import ModuleType
from typing import Any


ROOT = Path(__file__).resolve().parents[3]
TEST_PATH = ROOT / "tobkiri_runtime" / "tests" / "test_complete_v4_migration_gate.py"
DEFAULT_OUTPUT = (
    ROOT
    / "tobkiri_runtime"
    / "scripts"
    / "quality"
    / "evidence"
    / "complete_v4_migration_red_64b2240e.json"
)


def _load_gate_module() -> ModuleType:
    """Load the dedicated gate helpers without importing application code."""
    spec = importlib.util.spec_from_file_location(
        "complete_v4_migration_gate", TEST_PATH
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load gate module: {TEST_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _nodeids() -> list[str]:
    """Return deterministic pytest nodeids from the dedicated test file."""
    tree = ast.parse(TEST_PATH.read_text(encoding="utf-8"), filename=str(TEST_PATH))
    relative = TEST_PATH.relative_to(ROOT).as_posix()
    return [
        f"{relative}::{node.name}"
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name.startswith("test_")
    ]


def _counts(report: dict[str, Any]) -> dict[str, Any]:
    """Flatten evidence lists into handoff-friendly deterministic counts."""
    findings = report["findings"]
    return {
        "production_pack_directories": report["pack_inventory"][
            "production_pack_directories"
        ],
        "v4_pack_artifacts": len(report["pack_inventory"]["v4_pack_artifacts"]),
        "v4_profile_artifacts": len(report["pack_inventory"]["v4_profile_artifacts"]),
        "v4_pack_manifest_compliance": len(
            report["pack_inventory"]["v4_pack_manifest_compliance"]
        ),
        "v4_profile_selection_shape": len(
            report["pack_inventory"]["v4_profile_selection_shape"]
        ),
        "authority_classification": report["pack_inventory"]["authority_counts"],
        **{
            key: len(value)
            for key, value in findings.items()
            if isinstance(value, list)
        },
    }


def build_evidence() -> dict[str, Any]:
    """Build the complete current-tree evidence document."""
    gate_module = _load_gate_module()
    report = gate_module._audit_snapshot()
    return {
        "schema": "io.tobkiri.quality.complete-v4-migration-evidence.v1",
        "source": {
            "test_file": TEST_PATH.relative_to(ROOT).as_posix(),
            "start_sha": report["start_sha"],
            "observed_head_sha": report["head_sha"],
        },
        "nodeids": _nodeids(),
        "counts": _counts(report),
        "gate": report["gate"],
        "pack_inventory": report["pack_inventory"],
        "findings": report["findings"],
    }


def main() -> int:
    """Write evidence and return non-zero while any migration gate is RED."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="evidence JSON destination (default: the checked-in quality evidence path)",
    )
    args = parser.parse_args()
    output = args.output if args.output.is_absolute() else ROOT / args.output
    evidence = build_evidence()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    counts = evidence["counts"]
    print(
        json.dumps(
            {
                "output": output.relative_to(ROOT).as_posix(),
                "status": evidence["gate"]["status"],
                "nodeids": len(evidence["nodeids"]),
                "counts": counts,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0 if evidence["gate"]["status"] == "GREEN" else 1


if __name__ == "__main__":
    raise SystemExit(main())
