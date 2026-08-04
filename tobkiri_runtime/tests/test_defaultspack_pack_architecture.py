from __future__ import annotations

import hashlib
import json
import re
import sys
from dataclasses import replace
from pathlib import Path

import pytest
import yaml
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parent.parent
PACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(PACK_ROOT))

from domain.pack_architecture import (  # noqa: E402
    APP_SHELL_CONTRACT,
    CatalogError,
    PackCatalog,
    ProfileResolutionError,
    materialize_selected_artifacts,
    migrate_legacy_profile,
    resolve_profile,
)


ARCH_ROOT = PACK_ROOT / "domain" / "pack_architecture"
ASSETS_ROOT = ARCH_ROOT / "assets"
PROFILE_ROOT = PACK_ROOT / "profiles"


def _catalog() -> PackCatalog:
    return PackCatalog.from_assets_root(ASSETS_ROOT)


def _profile(name: str) -> dict:
    return yaml.safe_load((PROFILE_ROOT / name).read_text(encoding="utf-8"))


def test_catalog_contains_reusable_base_shell_application_and_toolchain_packs() -> None:
    catalog = _catalog()
    pack_ids = {pack.pack_id for pack in catalog.all()}
    assert {
        "defaults-basepack",
        "defaultspack",
        "shell.tauri.default",
        "shell.electron.default",
        "shell.cli.default",
        "runtime.tauri.application.default",
        "runtime.electron.application.default",
        "dev.tauri.toolchain.default",
        "dev.electron.toolchain.default",
    } <= pack_ids

    base = catalog.require("defaults-basepack")
    assert base.kind == "base"
    assert base.backend_provider_ids == ("defaultspack",)
    assert base.shell_contract is None
    assert base.raw["backend"]["implementation_pack"] == "defaultspack"
    assert "technology" not in base.raw
    assert "host_authority" not in base.raw
    for contribution in base.contributions:
        artifact_path = ASSETS_ROOT / "contributions" / Path(contribution.artifact_ref).name
        digest = "sha256:" + hashlib.sha256(artifact_path.read_bytes()).hexdigest()
        assert contribution.digest == digest


def test_shell_packs_are_exact_app_shell_providers_and_prebuilt_only() -> None:
    catalog = _catalog()
    for pack_id, family, technology in (
        ("shell.tauri.default", "graphical", "tauri"),
        ("shell.electron.default", "graphical", "electron"),
        ("shell.cli.default", "terminal", "cli"),
    ):
        pack = catalog.require(pack_id)
        assert pack.kind == "shell"
        assert pack.shell_contract == APP_SHELL_CONTRACT
        assert pack.presentation_family == family
        assert pack.technology == technology
        assert pack.raw["production"] == {
            **pack.raw["production"],
            "launchable": True,
            "prebuilt_only": True,
            "build_during_activation": False,
            "dev_commands_reachable": False,
        }
        assert {variant.variant_id for variant in pack.variants} == {
            "linux-x86_64",
            "macos-arm64",
            "macos-x86_64",
            "windows-x86_64",
        }
        for variant in pack.variants:
            artifact_path = pack.source_dir / variant.artifact_ref
            assert artifact_path.is_file()
            digest = "sha256:" + hashlib.sha256(artifact_path.read_bytes()).hexdigest()
            assert variant.digest == digest
            assert "dev" not in artifact_path.read_text(encoding="utf-8").lower()


def test_tauri_electron_cli_profiles_filter_only_selected_contributions() -> None:
    catalog = _catalog()
    tauri = resolve_profile(_profile("defaults-modern.profile.yaml"), catalog)
    electron = resolve_profile(_profile("defaults-modern-electron.profile.yaml"), catalog)
    cli = resolve_profile(_profile("defaults-modern-cli.profile.yaml"), catalog)

    graphical_ids = {"defaultspack.ui.graphical", "defaultspack.ui.panel"}
    cli_ids = {"defaultspack.cli.command", "defaultspack.cli.renderer"}
    assert {item.contribution_id for item in tauri.selected_contributions} == graphical_ids
    assert {item.contribution_id for item in electron.selected_contributions} == graphical_ids
    assert {item.contribution_id for item in cli.selected_contributions} == cli_ids
    assert set(tauri.omitted_contribution_ids) == cli_ids
    assert set(electron.omitted_contribution_ids) == cli_ids
    assert set(cli.omitted_contribution_ids) == graphical_ids
    assert all(item.presentation_family == "terminal" for item in cli.selected_contributions)
    assert all(
        item.presentation_family == "graphical"
        for item in tauri.selected_contributions + electron.selected_contributions
    )

    assert tauri.backend_identity == electron.backend_identity == cli.backend_identity
    assert tauri.state_owners == electron.state_owners == cli.state_owners
    assert tauri.backend_identity == ("defaultspack",)


def test_materializer_copies_selected_artifacts_and_not_omitted_contributions(
    tmp_path: Path,
) -> None:
    resolution = resolve_profile(_profile("defaults-modern-cli.profile.yaml"), _catalog())
    copied = materialize_selected_artifacts(resolution, tmp_path / "materialized")
    assert copied
    contribution_paths = [path for path in copied if "contributions" in path.parts]
    contribution_text = [path.read_text(encoding="utf-8") for path in contribution_paths]
    assert contribution_text
    assert len(contribution_paths) == 1
    assert all('"presentation_family": "terminal"' in content for content in contribution_text)
    assert not any('"presentation_family": "graphical"' in content for content in contribution_text)
    manifest = json.loads(
        (tmp_path / "materialized" / "materialization-manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["shell_provider"] == "shell.cli.default"
    assert set(manifest["omitted_contributions"]) == {
        "defaultspack.ui.graphical",
        "defaultspack.ui.panel",
    }
    assert not list((tmp_path / "materialized" / "defaultspack").glob("*graphical*"))


def test_profile_resolution_requires_exact_provider_and_never_falls_back() -> None:
    catalog = _catalog()
    profile = _profile("defaults-modern.profile.yaml")
    profile["shell"]["provider"] = "shell.missing"
    with pytest.raises(CatalogError, match="not cataloged"):
        resolve_profile(profile, catalog)

    profile = _profile("defaults-modern.profile.yaml")
    profile["shell"]["contract"] = "app.shell.v999"
    with pytest.raises(ProfileResolutionError, match="must be app.shell.v1"):
        resolve_profile(profile, catalog)

    profile = _profile("defaults-modern.profile.yaml")
    profile["shell"].pop("provider")
    with pytest.raises(ProfileResolutionError, match="exact provider"):
        resolve_profile(profile, catalog)

    profile = _profile("defaults-modern.profile.yaml")
    profile["shell"]["providers"] = "shell.electron.default"
    with pytest.raises(ProfileResolutionError, match="ambiguous"):
        resolve_profile(profile, catalog)

    profile = _profile("defaults-modern.profile.yaml")
    profile["base"]["technology"] = "tauri"
    with pytest.raises(ProfileResolutionError, match="cannot select a UI technology"):
        resolve_profile(profile, catalog)


def test_missing_platform_variant_is_fail_closed() -> None:
    profile = _profile("defaults-modern.profile.yaml")
    profile["platform"] = {"os": "freebsd", "architecture": "x86_64"}
    with pytest.raises(ProfileResolutionError, match="no exact prebuilt variant"):
        resolve_profile(profile, _catalog())

    profile = _profile("defaults-modern.profile.yaml")
    profile.pop("platform")
    with pytest.raises(ProfileResolutionError, match="platform.os"):
        resolve_profile(profile, _catalog())


def test_shell_production_flags_are_admission_checked() -> None:
    catalog = _catalog()
    shell = catalog.require("shell.tauri.default")
    raw = dict(shell.raw)
    raw["production"] = {**raw["production"], "dev_commands_reachable": True}
    altered_shell = replace(shell, raw=raw)
    altered_catalog = PackCatalog(
        altered_shell if pack.pack_id == shell.pack_id else pack for pack in catalog.all()
    )
    with pytest.raises(ProfileResolutionError, match="dev_commands_reachable"):
        resolve_profile(_profile("defaults-modern.profile.yaml"), altered_catalog)


def test_materializer_rejects_a_changed_selected_digest(tmp_path: Path) -> None:
    resolution = resolve_profile(_profile("defaults-modern.profile.yaml"), _catalog())
    altered_artifact = replace(resolution.selected_artifacts[0], digest="sha256:" + ("0" * 64))
    altered_resolution = replace(
        resolution,
        selected_artifacts=(altered_artifact,) + resolution.selected_artifacts[1:],
    )
    with pytest.raises(ProfileResolutionError, match="digest changed"):
        materialize_selected_artifacts(altered_resolution, tmp_path / "materialized")


def test_tauri_electron_application_runtime_and_dev_toolchain_are_separate() -> None:
    catalog = _catalog()
    for technology in ("tauri", "electron"):
        runtime = catalog.require(f"runtime.{technology}.application.default")
        dev = catalog.require(f"dev.{technology}.toolchain.default")
        assert runtime.kind == "application_runtime"
        assert dev.kind == "development_toolchain"
        assert runtime.raw["production"]["prebuilt_only"] is True
        assert runtime.raw["production"]["source_build"] is False
        assert runtime.raw["production"]["dev_commands_reachable"] is False
        assert runtime.raw["security"]["authority_mode"] == "lease_only"
        assert dev.raw["realm"] == "development"
        assert dev.raw["trust_class"] == "host_extension"
        assert dev.raw["production"]["launchable"] is False
        assert dev.raw["production"]["production_realm_reachable"] is False
        assert dev.raw["production"]["fallback_for_production_launch"] is False
        assert "cargo.tauri.dev" not in runtime.raw.get("development_operations", [])
        assert "npm.run.dev" not in runtime.raw.get("development_operations", [])


def test_legacy_desktop_command_is_inventory_only_and_requires_review() -> None:
    migrated = migrate_legacy_profile(
        {
            "profile_id": "legacy",
            "version": "rumi.profile.v1",
            "base_pack": "defaultspack",
            "launch": {
                "kind": "desktop_app",
                "desktop_app": {"command": "cargo tauri dev"},
            },
        }
    )
    assert migrated["base"]["pack"] == "defaults-basepack"
    assert "shell" not in migrated
    assert migrated["migration"]["status"] == "review_required"
    item = migrated["migration"]["legacy_inputs"][0]
    assert item["classification"] == "development_toolchain_candidate"
    assert item["execution"] == "inventory_only"
    assert item["production_launch"] == "forbidden"
    assert migrated["policy"]["legacy_commands_executable"] is False
    assert "cargo tauri dev" not in json.dumps(migrated.get("shell", {}))


def test_legacy_explicit_provider_can_migrate_without_command() -> None:
    migrated = migrate_legacy_profile(
        {
            "profile_id": "legacy-shell",
            "version": "rumi.profile.v1",
            "base_pack": "basepack",
            "launch": {"kind": "desktop_app", "shell_provider": "shell.tauri.default"},
        }
    )
    assert migrated["base"]["pack"] == "defaults-basepack"
    assert migrated["shell"] == {
        "contract": "app.shell.v1",
        "provider": "shell.tauri.default",
        "source": "legacy.explicit_shell_provider",
    }
    assert migrated["migration"]["status"] == "review_required"
    assert migrated["migration"]["selection_mode"] == "explicit_exact_provider"
    assert migrated["activation_eligible"] is False
    assert migrated["authority_minted"] is False


def test_legacy_unknown_shell_provider_is_rejected() -> None:
    with pytest.raises(ValueError, match="approved exact provider"):
        migrate_legacy_profile(
            {
                "profile_id": "legacy-shell",
                "base_pack": "defaultspack",
                "launch": {"shell_provider": "shell.custom"},
            }
        )


def test_modern_defaults_profiles_are_local_first_and_cloud_key_free() -> None:
    for path in sorted(PROFILE_ROOT.glob("defaults-modern*.profile.yaml")):
        profile = _profile(path.name)
        assert profile["schema"] == "io.tobkiri.profile.v4"
        assert profile["base"]["pack"] == "defaults-basepack"
        assert profile["shell"]["contract"] == "app.shell.v1"
        assert profile["local_first"]["default_model"] == "stub/default"
        assert profile["local_first"]["cloud_keys_required"] is False
        assert profile["local_first"]["required_secrets"] == []
        assert profile["local_first"]["required_network"] == []
        assert profile["policy"]["network_default"] == "deny"
        assert profile["policy"]["profile_may_mint_host_authority"] is False


def test_schema_and_example_assets_are_parseable_and_no_shell_has_dev_launch_fallback() -> None:
    for path in ASSETS_ROOT.rglob("*.json"):
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert isinstance(payload, dict), path
    for path in ASSETS_ROOT.rglob("*.yaml"):
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert isinstance(payload, dict), path

    schemas = {path.name for path in (ASSETS_ROOT / "schemas").glob("*.json")}
    assert {
        "app-shell.v1.schema.json",
        "base-pack.v1.schema.json",
        "presentation-contribution.v1.schema.json",
        "profile.v4.schema.json",
        "application-pack.v1.schema.json",
        "legacy-startup-input.v1.schema.json",
    } <= schemas
    schema_documents = {
        path.name: json.loads(path.read_text(encoding="utf-8"))
        for path in (ASSETS_ROOT / "schemas").glob("*.json")
    }
    for schema in schema_documents.values():
        Draft202012Validator.check_schema(schema)
    schema_cases = [
        ("base-pack.v1.schema.json", ASSETS_ROOT / "packs/defaults-basepack/pack.json"),
        ("app-shell.v1.schema.json", ASSETS_ROOT / "packs/shell.tauri.default/pack.json"),
        (
            "app-shell.v1.schema.json",
            ASSETS_ROOT / "packs/shell.electron.default/pack.json",
        ),
        ("app-shell.v1.schema.json", ASSETS_ROOT / "packs/shell.cli.default/pack.json"),
        (
            "presentation-contribution.v1.schema.json",
            ASSETS_ROOT / "contributions/defaultspack.graphical.json",
        ),
        (
            "presentation-contribution.v1.schema.json",
            ASSETS_ROOT / "contributions/defaultspack.cli.json",
        ),
        (
            "application-pack.v1.schema.json",
            ASSETS_ROOT / "examples/standalone-tauri-application.example.yaml",
        ),
        (
            "legacy-startup-input.v1.schema.json",
            ASSETS_ROOT / "legacy/legacy-desktop-app-command.example.yaml",
        ),
    ]
    for schema_name, asset_path in schema_cases:
        payload = (
            yaml.safe_load(asset_path.read_text(encoding="utf-8"))
            if asset_path.suffix in {".yaml", ".yml"}
            else json.loads(asset_path.read_text(encoding="utf-8"))
        )
        Draft202012Validator(schema_documents[schema_name]).validate(payload)
    profile_schema = Draft202012Validator(schema_documents["profile.v4.schema.json"])
    for profile_path in PROFILE_ROOT.glob("defaults-modern*.yaml"):
        profile_schema.validate(yaml.safe_load(profile_path.read_text(encoding="utf-8")))
    shell_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (ASSETS_ROOT / "packs").glob("shell.*/pack.json")
    )
    assert re.search(r"cargo\s+tauri\s+dev|npm\s+run\s+dev", shell_text) is None
