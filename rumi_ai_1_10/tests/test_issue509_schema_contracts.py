from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft7Validator


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
SCHEMA_DIR = ROOT / "backend_core" / "ecosystem" / "spec" / "schema"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_index(path: Path) -> dict[str, Any]:
    if path.suffix == ".json":
        return _load_json(path)
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _schema(name: str) -> dict[str, Any]:
    return _load_json(SCHEMA_DIR / f"{name}.schema.json")


def _error_messages(validator: Draft7Validator, payload: Any) -> list[str]:
    return [error.message for error in sorted(validator.iter_errors(payload), key=str)]


def _assert_valid(validator: Draft7Validator, payload: Any, label: str) -> None:
    errors = _error_messages(validator, payload)
    assert not errors, f"{label} failed schema validation:\n" + "\n".join(errors)


def _assert_invalid(validator: Draft7Validator, payload: Any, *expected: str) -> None:
    errors = _error_messages(validator, payload)
    assert errors
    joined = "\n".join(errors)
    for token in expected:
        assert token in joined


def _flat_categories(categories: dict[str, Any]) -> set[str]:
    return {
        item
        for values in categories.values()
        if isinstance(values, list)
        for item in values
        if isinstance(item, str)
    }


def test_declarative_runtime_types_are_supported_by_existing_manifests() -> None:
    schema = _schema("ecosystem")
    runtime_type_enum = set(schema["properties"]["runtime"]["properties"]["type"]["enum"])
    metadata_runtime_type_enum = set(
        schema["properties"]["metadata"]["properties"]["runtime_type"]["enum"]
    )
    expected = {"declarative_pack", "declarative_setup_pack"}

    assert expected <= runtime_type_enum
    assert expected <= metadata_runtime_type_enum

    validator = Draft7Validator(schema)
    declarative_paths: list[Path] = []
    for path in sorted((ROOT / "ecosystem").glob("*/ecosystem.json")):
        payload = _load_json(path)
        runtime_type = (payload.get("runtime") or {}).get("type")
        metadata_runtime_type = (payload.get("metadata") or {}).get("runtime_type")
        if runtime_type in expected:
            declarative_paths.append(path)
            _assert_valid(validator, payload, str(path.relative_to(ROOT)))
        if metadata_runtime_type:
            assert metadata_runtime_type in metadata_runtime_type_enum, path

    assert declarative_paths, "expected at least one declarative runtime manifest"


def test_addon_schema_rejects_broad_and_underspecified_patch_contracts() -> None:
    validator = Draft7Validator(_schema("addon"))

    valid = {
        "addon_id": "strict_target",
        "version": "1.0.0",
        "targets": [
            {
                "pack_identity": "github:haru/default-pack",
                "component": {"type": "chat", "id": "chat_v1"},
                "apply": [
                    {
                        "kind": "manifest_json_patch",
                        "patch": [{"op": "add", "path": "/extensions/test", "value": True}],
                    }
                ],
            }
        ],
    }
    _assert_valid(validator, valid, "valid addon")

    missing_discriminator = {
        **valid,
        "targets": [{"apply": valid["targets"][0]["apply"]}],
    }
    _assert_invalid(validator, missing_discriminator, "not valid")

    missing_patch = {
        **valid,
        "targets": [
            {
                "pack_identity": "github:haru/default-pack",
                "apply": [{"kind": "manifest_json_patch"}],
            }
        ],
    }
    _assert_invalid(validator, missing_patch, "'patch' is a required property")

    file_patch_without_file = {
        **valid,
        "targets": [
            {
                "pack_identity": "github:haru/default-pack",
                "apply": [
                    {
                        "kind": "file_json_patch",
                        "patch": [{"op": "replace", "path": "/x", "value": 1}],
                    }
                ],
            }
        ],
    }
    _assert_invalid(validator, file_patch_without_file, "'file' is a required property")

    patch_value_missing = {
        **valid,
        "targets": [
            {
                "pack_identity": "github:haru/default-pack",
                "apply": [
                    {
                        "kind": "manifest_json_patch",
                        "patch": [{"op": "replace", "path": "/x"}],
                    }
                ],
            }
        ],
    }
    _assert_invalid(validator, patch_value_missing, "'value' is a required property")

    empty_patch = {
        **valid,
        "targets": [
            {
                "pack_identity": "github:haru/default-pack",
                "apply": [{"kind": "manifest_json_patch", "patch": []}],
            }
        ],
    }
    _assert_invalid(validator, empty_patch, "should be non-empty")


def test_high_risk_exec_tool_manifests_match_runtime_required_inputs() -> None:
    tools = {
        "sandbox_exec": {
            "valid": [{"argv": ["pwd"]}, {"command": "pwd"}, {"command": ["pwd"]}],
            "invalid": [{}, {"argv": []}, {"argv": [""], "unknown": True}],
        },
        "python_exec": {
            "valid": [{"code": "print(1)"}, {"script_path": "scripts/task.py"}],
            "invalid": [{}, {"code": ""}, {"code": "print(1)", "unknown": True}],
        },
        "node_exec": {
            "valid": [{"code": "console.log(1)"}, {"script_path": "scripts/task.js"}],
            "invalid": [{}, {"script_path": ""}, {"script_path": "a.js", "unknown": True}],
        },
    }

    for tool_id, expectations in tools.items():
        manifest = _load_json(DEFAULTSPACK_ROOT / "tools" / tool_id / "manifest.json")
        parameters = manifest["config"]["schema"]["parameters"]
        assert parameters["type"] == "object"
        assert parameters["additionalProperties"] is False
        assert "anyOf" in parameters
        assert parameters.get("required", []) == []
        validator = Draft7Validator(parameters)
        for payload in expectations["valid"]:
            _assert_valid(validator, payload, f"{tool_id} valid payload")
        for payload in expectations["invalid"]:
            _assert_invalid(validator, payload)

    sandbox_parameters = _load_json(
        DEFAULTSPACK_ROOT / "tools" / "sandbox_exec" / "manifest.json"
    )["config"]["schema"]["parameters"]
    command = sandbox_parameters["properties"]["command"]
    assert "oneOf" in command
    assert sandbox_parameters["properties"]["argv"]["items"]["type"] == "string"


def test_asset_index_shapes_are_explicit_and_semantically_consistent() -> None:
    ecosystem_schema = _schema("ecosystem")
    category_validator = Draft7Validator(ecosystem_schema["definitions"]["asset_index_categories"])
    wrapped_validator = Draft7Validator(_schema("asset_index"))

    for ecosystem_path in sorted((ROOT / "ecosystem").glob("*/ecosystem.json")):
        pack_dir = ecosystem_path.parent
        metadata_index = (_load_json(ecosystem_path).get("metadata") or {}).get("asset_index")
        if isinstance(metadata_index, dict):
            _assert_valid(category_validator, metadata_index, f"{pack_dir.name} metadata index")

        wrapped_indexes: dict[str, dict[str, Any]] = {}
        for index_path in sorted(pack_dir.glob("asset_index.*")):
            payload = _load_index(index_path)
            _assert_valid(wrapped_validator, payload, str(index_path.relative_to(ROOT)))
            wrapped = payload["asset_index"]
            assert wrapped["pack_id"] == pack_dir.name
            wrapped_indexes[index_path.suffix] = wrapped
            if isinstance(metadata_index, dict):
                assert _flat_categories(metadata_index) == _flat_categories(wrapped["categories"])

        if ".json" in wrapped_indexes and ".yaml" in wrapped_indexes:
            assert wrapped_indexes[".json"]["categories"] == wrapped_indexes[".yaml"]["categories"]
            assert wrapped_indexes[".json"].get("invariants", {}) == wrapped_indexes[".yaml"].get(
                "invariants", {}
            )


def test_default_runtime_config_uses_integer_byte_limit() -> None:
    config = _load_json(DEFAULTSPACK_ROOT / "config" / "default_runtime_config.json")
    schema = _load_json(DEFAULTSPACK_ROOT / "config" / "runtime_config.schema.json")
    _assert_valid(Draft7Validator(schema), config, "default runtime config")

    limit = config["context"]["compression"]["max_active_transcript_bytes"]
    assert limit == 20 * 1024 * 1024
    assert isinstance(limit, int)
