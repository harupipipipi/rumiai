from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(DEFAULTSPACK_ROOT))

from domain.templates.lifecycle import (  # noqa: E402
    TemplateLifecycleStore,
    apply_template_lifecycle,
    plan_template_lifecycle,
)
from domain.templates.migration import migrate_template_dict  # noqa: E402


def _template(lifecycle: dict) -> dict:
    return {
        "id": "template.lifecycle",
        "schema_version": 1,
        "kind": "frontend",
        "version": "1.2.0",
        "status": "active",
        "lifecycle": lifecycle,
    }


def test_v0_template_migration_is_pure_data_transform():
    migrated, diagnostics = migrate_template_dict(
        {
            "id": "legacy.template",
            "kind": "frontend",
            "template_version": "1.0.0",
            "template_status": "active",
            "template_pieces": [],
        }
    )

    assert migrated["schema_version"] == 1
    assert migrated["version"] == "1.0.0"
    assert migrated["status"] == "active"
    assert migrated["pieces"] == []
    assert [diagnostic.code for diagnostic in diagnostics] == ["template.migration.applied"]


def test_future_template_migration_does_not_downgrade():
    migrated, diagnostics = migrate_template_dict({"id": "future", "schema_version": 99})

    assert migrated["schema_version"] == 99
    assert diagnostics[0].code == "template.migration.future_schema_version"


def test_lifecycle_fresh_install_writes_state_atomically(tmp_path):
    template = _template(
        {
            "install": [
                {"op": "set_default_if_missing", "key": "preferred_model", "value": "stub/default"}
            ]
        }
    )
    settings: dict[str, object] = {}

    plan = apply_template_lifecycle(
        template,
        action="install",
        settings=settings,
        defaultspack_root=tmp_path,
        source_generation="gen-a",
    )

    assert plan.ok
    assert settings["preferred_model"] == "stub/default"
    state_path = tmp_path / "user_data" / "shared" / "templates" / "template-state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    entry = state["templates"]["template.lifecycle"]
    assert entry["installed_version"] == "1.2.0"
    assert entry["schema_version"] == 1
    assert entry["source_generation"] == "gen-a"


def test_lifecycle_state_save_skips_directory_fsync_when_unavailable(tmp_path, monkeypatch):
    monkeypatch.delattr(os, "O_DIRECTORY", raising=False)
    store = TemplateLifecycleStore(tmp_path)
    state = {"templates": {"template.lifecycle": {"installed_version": "1.2.0"}}}

    store.save(state)

    assert json.loads(store.path.read_text(encoding="utf-8")) == state


def test_lifecycle_reapply_is_idempotent_and_preserves_existing_value(tmp_path):
    template = _template(
        {
            "install": [
                {"op": "set_default_if_missing", "key": "preferred_model", "value": "new/default"}
            ]
        }
    )
    settings = {"preferred_model": "user/model"}

    first = apply_template_lifecycle(
        template,
        action="install",
        settings=settings,
        defaultspack_root=tmp_path,
    )
    second = apply_template_lifecycle(
        template,
        action="install",
        settings=settings,
        defaultspack_root=tmp_path,
    )

    assert first.ok and second.ok
    assert settings["preferred_model"] == "user/model"
    assert second.results[0].skipped is True


def test_lifecycle_setting_rename_and_uninstall_archive(tmp_path):
    template = _template(
        {
            "upgrade": [{"op": "rename_setting", "from": "old_model", "to": "preferred_model"}],
            "uninstall": {
                "orphan_policy": "archive",
                "operations": [{"op": "archive_setting", "key": "preferred_model"}],
            },
        }
    )
    settings = {"old_model": "stub/default"}

    upgrade = apply_template_lifecycle(
        template,
        action="upgrade",
        settings=settings,
        defaultspack_root=tmp_path,
    )
    uninstall = apply_template_lifecycle(
        template,
        action="uninstall",
        settings=settings,
        defaultspack_root=tmp_path,
    )

    assert upgrade.ok and uninstall.ok
    assert "preferred_model" not in settings
    assert settings["_archived_settings"]["archived.preferred_model"] == "stub/default"


def test_lifecycle_failure_rolls_back_settings_and_state(tmp_path):
    template = _template(
        {
            "install": [
                {"op": "set_default_if_missing", "key": "preferred_model", "value": "stub/default"},
                {"op": "run_python", "module": "evil"},
            ]
        }
    )
    settings: dict[str, object] = {}

    plan = apply_template_lifecycle(
        template,
        action="install",
        settings=settings,
        defaultspack_root=tmp_path,
    )

    assert not plan.ok
    assert settings == {}
    assert not (tmp_path / "user_data" / "shared" / "templates" / "template-state.json").exists()


def test_lifecycle_rejects_path_escape_and_secret_field_operations(tmp_path):
    with pytest.raises(ValueError):
        TemplateLifecycleStore(tmp_path, state_path=tmp_path.parent / "template-state.json")

    template = _template(
        {
            "upgrade": [
                {
                    "op": "rename_setting",
                    "from": "provider_api_key",
                    "to": "preferred_model",
                }
            ]
        }
    )
    settings = {"provider_api_key": "secret"}
    plan = apply_template_lifecycle(
        template,
        action="upgrade",
        settings=settings,
        defaultspack_root=tmp_path,
    )

    assert not plan.ok
    assert settings == {"provider_api_key": "secret"}
    assert plan.diagnostics[0]["code"] == "template.lifecycle.secret_operation_rejected"


def test_lifecycle_dry_run_does_not_mutate_settings(tmp_path):
    template = _template(
        {"install": [{"op": "set_default_if_missing", "key": "preferred_model", "value": "stub"}]}
    )
    settings: dict[str, object] = {}

    plan = plan_template_lifecycle(
        template,
        action="install",
        settings=settings,
        defaultspack_root=tmp_path,
    )

    assert plan.ok
    assert settings == {}
    assert plan.results[0].changed is True
