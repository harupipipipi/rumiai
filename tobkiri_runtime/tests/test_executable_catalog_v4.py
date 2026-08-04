from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from tobkiri_host.artifact_compiler import compile_pack_root
from tobkiri_host.errors import InvalidArtifactError
from tobkiri_protocol.errors import SchemaValidationError


ROOT = Path(__file__).resolve().parent.parent


def test_canonical_executable_catalogs_compile_exact_declared_operations() -> None:
    conversation = compile_pack_root(ROOT / "ecosystem" / "defaultspack")
    inspect = compile_pack_root(ROOT / "ecosystem" / "rumi_file_inspect_pack")
    operations = {
        (operation.contract_id, operation.operation_id)
        for artifact in (conversation.artifact, inspect.artifact)
        for function in artifact.functions
        for operation in function.operations
    }
    assert operations == {
        ("conversation.turn.v1", "complete"),
        (
            "tobkiri.service.file.inspect.v1",
            "rumi_file_inspect_pack.file-inspect",
        ),
    }
    assert set(conversation.routes) == {("conversation.turn.v1", "complete")}
    assert set(inspect.routes) == {
        (
            "tobkiri.service.file.inspect.v1",
            "rumi_file_inspect_pack.file-inspect",
        )
    }


def test_compiler_rejects_tamper_missing_variant_and_source_swap(
    tmp_path: Path,
) -> None:
    copied = tmp_path / "defaultspack"
    shutil.copytree(ROOT / "ecosystem" / "defaultspack", copied)
    runtime = copied / "runtime" / "conversation.py"
    runtime.write_text(runtime.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    with pytest.raises(InvalidArtifactError, match="digest mismatch"):
        compile_pack_root(copied)

    shutil.rmtree(copied)
    shutil.copytree(ROOT / "ecosystem" / "defaultspack", copied)
    catalog_path = copied / "executables.v4.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    catalog["variants"] = []
    catalog_path.write_text(json.dumps(catalog), encoding="utf-8")
    with pytest.raises((InvalidArtifactError, SchemaValidationError)):
        compile_pack_root(copied)

    shutil.rmtree(copied)
    shutil.copytree(ROOT / "ecosystem" / "defaultspack", copied)
    catalog_path = copied / "executables.v4.json"
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    catalog["source_identity"] = "sha256:" + "0" * 64
    catalog_path.write_text(json.dumps(catalog), encoding="utf-8")
    with pytest.raises(InvalidArtifactError, match="source identity"):
        compile_pack_root(copied)
