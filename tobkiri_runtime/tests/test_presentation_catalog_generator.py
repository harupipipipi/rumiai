from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
PACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(PACK_ROOT))

from domain.pack_architecture import (  # noqa: E402
    PackCatalog,
    generate_presentation_catalog,
    presentation_catalog_drift,
    resolve_profile,
)

CATALOG_PATH = (
    ROOT.parent / "tobkiri_launcher" / "src-tauri" / "bundled" / ("presentation_catalog.json")
)
ASSETS_ROOT = PACK_ROOT / "domain" / "pack_architecture" / "assets"


def _sha256(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def test_bundled_launcher_catalog_is_reproducible_and_manifest_driven() -> None:
    assert presentation_catalog_drift(ROOT.parent) is False
    generated = generate_presentation_catalog(ROOT.parent)
    bundled = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    assert bundled == generated
    assert bundled["default_selection"] == {
        "base_pack_id": "defaults-basepack",
        "shell_provider_id": "shell.tauri.default",
    }
    assert {item["provider_id"] for item in bundled["shell_providers"]} == {
        "shell.tauri.default",
        "shell.electron.default",
        "shell.cli.default",
    }


def test_catalog_contains_exact_production_variants_and_no_placeholder_installation() -> None:
    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    expected_variants = {
        "macos-arm64",
        "linux-x86_64",
        "windows-x86_64",
    }
    pack_catalog = PackCatalog.from_assets_root(ASSETS_ROOT)
    for shell_descriptor in catalog["shell_providers"]:
        shell = pack_catalog.require(shell_descriptor["provider_id"])
        assert {
            item["variant"] for item in shell_descriptor["artifact_variants"]
        } == expected_variants
        for variant in shell_descriptor["artifact_variants"]:
            source = shell.source_dir / variant["artifact_ref"]
            assert variant["descriptor_digest"] == _sha256(source)
            assert variant["artifact_id"] == f"{shell.pack_id}.{variant['variant']}"
            assert variant["path"] is None
            assert variant["sha256"] is None
            assert variant["development_command"] is None
            assert variant["prebuilt"] is True
            assert variant["production"] is True

    assert {item["provider_id"] for item in catalog["shell_providers"]} == {
        "shell.tauri.default",
        "shell.electron.default",
        "shell.cli.default",
    }


def test_catalog_pins_contracts_approval_and_backend_identity() -> None:
    catalog = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    base = catalog["base_packs"][0]
    assert base["backend_provider_ids"] == ["defaultspack"]
    assert base["state_owners"] == [
        "defaultspack.conversation",
        "defaultspack.agent",
        "defaultspack.tool_catalog",
        "defaultspack.local_settings",
    ]
    assert base["approval"]["state"] == "verified"
    assert base["approval"]["provider_trust"] == "verified"
    assert base["approval"]["grant_state"] == "not_minted"
    assert base["approval"]["authority_mode"] == "none"

    revisions = {item["contract_id"]: item for item in catalog["contract_revisions"]}
    for revision in revisions.values():
        assert revision["digest"] == _sha256(ROOT.parent / revision["source_path"])
    assert {"app.shell.v1", "cli.io.v1", "ui.route.contribution.v1"} <= set(revisions)
    for shell in catalog["shell_providers"]:
        assert shell["contract_revision_digest"] == revisions["app.shell.v1"]["digest"]
        assert shell["approval"]["provider_trust"] == "verified"
        assert shell["approval"]["grant_state"] == "not_minted"
        assert shell["approval"]["authority_mode"] == "lease_only"
        assert all(item["materialization"] == "selected_only" for item in shell["contributions"])


def test_new_setup_profile_is_explicit_and_surface_switches_preserve_identity() -> None:
    profile = yaml.safe_load(
        (PACK_ROOT / "profiles" / "defaults-modern.profile.yaml").read_text(encoding="utf-8")
    )
    assert profile["metadata"]["default_for_new_setups"] is True
    assert profile["base"]["pack"] == "defaults-basepack"
    assert profile["shell"] == {
        "contract": "app.shell.v1",
        "provider": "shell.tauri.default",
    }
    assert "desktop_app" not in profile
    assert "command" not in profile

    pack_catalog = PackCatalog.from_assets_root(ASSETS_ROOT)
    resolved = [
        resolve_profile(
            yaml.safe_load((PACK_ROOT / "profiles" / filename).read_text(encoding="utf-8")),
            pack_catalog,
        )
        for filename in (
            "defaults-modern.profile.yaml",
            "defaults-modern-electron.profile.yaml",
            "defaults-modern-cli.profile.yaml",
        )
    ]
    assert {item.backend_identity for item in resolved} == {("defaultspack",)}
    assert {item.state_owners for item in resolved} == {
        (
            "defaultspack.conversation",
            "defaultspack.agent",
            "defaultspack.tool_catalog",
            "defaultspack.local_settings",
        )
    }
