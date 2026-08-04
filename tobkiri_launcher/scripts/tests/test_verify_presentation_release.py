from __future__ import annotations

import copy
import importlib.util
import json
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "verify_presentation_release.py"
SPEC = importlib.util.spec_from_file_location(
    "verify_presentation_release", SCRIPT_PATH
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_release_scanner_verifies_packaged_artifact_and_rejects_tampering() -> None:
    repository_root = Path(__file__).resolve().parents[3]
    source_catalog = json.loads(
        (
            repository_root
            / "tobkiri_launcher"
            / "src-tauri"
            / "bundled"
            / "presentation_catalog.json"
        ).read_text(encoding="utf-8")
    )
    catalog = copy.deepcopy(source_catalog)

    with TemporaryDirectory(prefix="tobkiri-presentation-release-scan-") as temp:
        resource_root = Path(temp) / "Resources" / "app"
        artifact = (
            resource_root
            / "bundled"
            / "presentation-artifacts"
            / "test"
            / "true"
        )
        artifact.parent.mkdir(parents=True)
        shutil.copyfile(Path(shutil.which("true") or "/usr/bin/true"), artifact)
        artifact.chmod(0o755)
        variant = catalog["shell_providers"][0]["artifact_variants"][0]
        variant["path"] = artifact.relative_to(resource_root).as_posix()
        variant["sha256"] = MODULE._artifact_digest(artifact)

        report = MODULE.verify_catalog(catalog, resource_root)
        assert variant["artifact_id"] in report["verified_artifact_ids"]
        assert report["blocked_uninstalled_artifact_count"] > 0

        artifact.write_bytes(artifact.read_bytes() + b"tamper")
        with pytest.raises(RuntimeError, match="digest mismatch"):
            MODULE.verify_catalog(catalog, resource_root)
