"""Boundary tests for presentation verification after Python packaging retirement."""

from __future__ import annotations

import ast
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1]
VERIFY_SCRIPT = SCRIPTS / "verify_presentation_release.py"
PACKAGE_SCRIPT = SCRIPTS / "package_presentation_artifact.py"


def test_release_verifier_has_no_direct_packager_dependency() -> None:
    """Release verification cannot resurrect the retired Python producer."""
    source = VERIFY_SCRIPT.read_text(encoding="utf-8")
    assert "package_presentation_artifact" not in source
    assert "TOBKIRI_PACKAGING_SOURCE_PROVENANCE_FILE" not in source
    ast.parse(source, filename=str(VERIFY_SCRIPT))


def test_retired_packager_is_a_single_fail_closed_boundary() -> None:
    """The old script is not a pathname-based producer/consumer bridge."""
    source = PACKAGE_SCRIPT.read_text(encoding="utf-8")
    assert source.count("_reject_direct_caller") >= 2
    assert "verified_catalog" in source
    assert "lease" in source
    assert "exec_module" not in source
    assert "subprocess" not in source
