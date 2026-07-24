from __future__ import annotations

import json
import importlib.util
from pathlib import Path

import pytest

from core_runtime.pack_sdk import (
    PackSdkError,
    PackSdkGenerator,
    scaffold_pack,
    validate_pack_manifest,
)

ROOT = Path(__file__).resolve().parent.parent
PACK_SCHEMA = ROOT / "schemas" / "pack_manifest_v3.schema.json"
CONTRACT_SCHEMA = ROOT / "schemas" / "global_contract_types.schema.json"


def test_sdk_generation_is_deterministic_and_detects_drift(tmp_path: Path) -> None:
    output = tmp_path / "generated"
    generator = PackSdkGenerator([PACK_SCHEMA, CONTRACT_SCHEMA])

    first = generator.generate(output)
    second = generator.generate(output, check=True)

    assert first == second
    index = json.loads((output / "contract_index.json").read_text(encoding="utf-8"))
    assert len(index["schemas"]) == 2
    assert all(record["sha256"] for record in index["schemas"])
    assert "packSchemaIds" in (output / "contract_ids.dart").read_text(
        encoding="utf-8"
    )
    spec = importlib.util.spec_from_file_location(
        "generated_command_models",
        output / "command_protocol_models.py",
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.CommandInvocationRequest

    (output / "contractIds.ts").write_text("// manually edited\n", encoding="utf-8")
    with pytest.raises(PackSdkError, match="drift"):
        generator.generate(output, check=True)

    generator.generate(output)
    (output / "stale_generated.ts").write_text("// stale\n", encoding="utf-8")
    with pytest.raises(PackSdkError, match="stale_generated"):
        generator.generate(output, check=True)


def test_scaffold_is_strictly_valid_and_untrusted(tmp_path: Path) -> None:
    manifest_path = scaffold_pack(
        tmp_path / "example",
        pack_id="example.echo",
        display_name="Echo",
    )

    manifest = validate_pack_manifest(manifest_path, schema_path=PACK_SCHEMA)

    assert manifest["pack"]["id"] == "example.echo"
    assert manifest["provenance"]["trust_class"] == "untrusted"
    assert manifest["permissions"] == []


def test_manifest_validation_rejects_unknown_security_fields(
    tmp_path: Path,
) -> None:
    manifest_path = scaffold_pack(
        tmp_path / "example",
        pack_id="example.echo",
        display_name="Echo",
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["provenance"]["trusted"] = True
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(PackSdkError, match="Additional properties"):
        validate_pack_manifest(manifest_path, schema_path=PACK_SCHEMA)
