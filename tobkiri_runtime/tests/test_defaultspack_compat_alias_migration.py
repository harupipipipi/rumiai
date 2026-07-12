from __future__ import annotations

import json
import logging
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
for path in (str(ROOT), str(DEFAULTSPACK_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)


def test_every_remaining_compat_alias_has_migration_metadata_and_canonical_replacement():
    from domain.function_runtime.compat_aliases import (
        compat_alias_metadata_errors,
        load_compat_alias_config,
    )

    config = load_compat_alias_config()
    assert config["migration"]["current_stage"] == "warning"
    aliases = config["aliases"]
    assert aliases
    for alias, metadata in aliases.items():
        assert alias.startswith("defaults.")
        assert compat_alias_metadata_errors(alias, metadata) == []
        assert str(metadata["replacement"]).startswith("defaultspack.")


def test_new_compat_alias_without_migration_note_fails_metadata_guard():
    from domain.function_runtime.compat_aliases import compat_alias_metadata_errors

    errors = compat_alias_metadata_errors(
        "defaults.example.run",
        {
            "owner": "example",
            "replacement": "defaultspack.example.run",
            "remove_after": "v2.5",
        },
    )

    assert errors == ["compat alias missing migration note: defaults.example.run"]


def test_manifest_generation_does_not_create_unallowlisted_defaults_aliases():
    from domain.function_runtime.manifest_factory import _spec

    spec = _spec("unlisted_demo", "Demo.", ("demo",))

    assert "defaultspack.unlisted.demo" in spec.aliases
    assert not any(alias.startswith("defaults.") for alias in spec.aliases)


def test_verified_unused_model_runtime_compat_group_is_removed_but_canonical_aliases_remain():
    config_text = (DEFAULTSPACK_ROOT / "compat_aliases.yaml").read_text(encoding="utf-8")
    for function_id in (
        "ai_get_thinking_level",
        "ai_set_thinking_level",
        "ai_get_effective_thinking_level",
        "ai_normalize_thinking_level",
    ):
        manifest = json.loads(
            (DEFAULTSPACK_ROOT / "functions" / function_id / "manifest.json").read_text(
                encoding="utf-8"
            )
        )
        aliases = manifest["vocab_aliases"]
        assert not any(alias.startswith("defaults.model_runtime.") for alias in aliases)
        assert any(alias.startswith("defaultspack.model_runtime.") for alias in aliases)
    assert "prefix: defaults.model_runtime." in config_text
    assert "  defaults.model_runtime." not in config_text


def test_alias_telemetry_contains_metadata_only_and_external_warning_is_deduplicated(
    monkeypatch,
    caplog,
):
    import core_runtime.audit_logger as audit_module
    from domain.function_runtime.compat_aliases import (
        record_compat_alias_use,
        reset_compat_alias_warning_state,
    )

    audit = MagicMock()
    monkeypatch.setattr(audit_module, "get_audit_logger", lambda: audit)
    reset_compat_alias_warning_state()
    caplog.set_level(logging.WARNING)

    first = record_compat_alias_use("defaults.ai.set_thinking_level", internal_caller=False)
    second = record_compat_alias_use("defaults.ai.set_thinking_level", internal_caller=False)

    assert first == {
        "schema_version": 1,
        "alias": "defaults.ai.set_thinking_level",
        "replacement": "defaultspack.ai.set_thinking_level",
        "stage": "warning",
        "caller_kind": "external",
        "warning_emitted": True,
    }
    assert second["warning_emitted"] is False
    assert audit.log_system_event.call_count == 2
    details = audit.log_system_event.call_args.kwargs["details"]
    assert set(details) == {
        "schema_version",
        "alias",
        "replacement",
        "stage",
        "caller_kind",
        "warning_emitted",
    }
    assert sum("compat_alias_deprecated" in record.message for record in caplog.records) == 1


def test_internal_alias_usage_is_audited_without_deprecation_warning(monkeypatch, caplog):
    import core_runtime.audit_logger as audit_module
    from domain.function_runtime.compat_aliases import (
        record_compat_alias_use,
        reset_compat_alias_warning_state,
    )

    audit = MagicMock()
    monkeypatch.setattr(audit_module, "get_audit_logger", lambda: audit)
    reset_compat_alias_warning_state()
    caplog.set_level(logging.WARNING)

    details = record_compat_alias_use("defaults.ai.set_thinking_level", internal_caller=True)

    assert details["caller_kind"] == "internal"
    assert details["warning_emitted"] is False
    assert not caplog.records
    audit.log_system_event.assert_called_once()


def test_capability_executor_records_actual_defaultspack_alias_resolution(monkeypatch):
    import core_runtime.capability_executor as executor_module

    executor = executor_module.CapabilityExecutor()
    executor._initialized = True
    entry = SimpleNamespace(
        pack_id="defaultspack",
        function_id="ai_set_thinking_level",
    )
    registry = MagicMock()
    registry.get.return_value = None
    registry.resolve_by_alias.return_value = entry
    executor._function_registry = registry
    recorded = []
    monkeypatch.setattr(
        executor_module,
        "_record_defaultspack_compat_alias_use",
        lambda alias, principal_id: recorded.append((alias, principal_id)),
    )
    monkeypatch.setattr(
        executor,
        "_trusted_builtin_pack_path_verdict",
        lambda *_args: (_ for _ in ()).throw(RuntimeError("stop after telemetry")),
    )

    with pytest.raises(RuntimeError, match="stop after telemetry"):
        executor._execute_function_call(
            "external_pack",
            {
                "type": "function.call",
                "qualified_name": "defaults.ai.set_thinking_level",
                "args": {"sensitive": "must-not-be-observed"},
            },
            time.time(),
        )

    assert recorded == [("defaults.ai.set_thinking_level", "external_pack")]


def test_capability_executor_records_legacy_permission_alias_resolution(monkeypatch):
    import core_runtime.capability_executor as executor_module

    executor = executor_module.CapabilityExecutor()
    entry = SimpleNamespace(pack_id="defaultspack")
    monkeypatch.setattr(executor, "_resolve_entry", lambda _permission_id: entry)
    expected = executor_module.CapabilityResponse(success=True)
    monkeypatch.setattr(executor, "_unified_execute", lambda *_args: expected)
    recorded = []
    monkeypatch.setattr(
        executor_module,
        "_record_defaultspack_compat_alias_use",
        lambda alias, principal_id: recorded.append((alias, principal_id)),
    )

    result = executor.execute(
        "external_pack",
        {"permission_id": "defaults.ai.set_thinking_level", "args": {}},
    )

    assert result is expected
    assert recorded == [("defaults.ai.set_thinking_level", "external_pack")]


def test_executor_classifies_only_trusted_pack_principals_as_internal(monkeypatch):
    import core_runtime.capability_executor as executor_module
    from domain.function_runtime import compat_aliases

    calls = []
    monkeypatch.setattr(
        compat_aliases,
        "record_compat_alias_use",
        lambda alias, *, internal_caller: calls.append((alias, internal_caller)),
    )

    executor_module._record_defaultspack_compat_alias_use(
        "defaults.ai.set_thinking_level",
        "external_pack",
    )
    executor_module._record_defaultspack_compat_alias_use(
        "defaults.ai.set_thinking_level",
        "defaultspack",
    )

    assert calls == [
        ("defaults.ai.set_thinking_level", False),
        ("defaults.ai.set_thinking_level", True),
    ]
