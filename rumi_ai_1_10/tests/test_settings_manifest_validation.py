from pathlib import Path

from core_runtime.settings.models import SettingContribution, SettingSectionId
from core_runtime.settings.validators import validate_contribution
from scripts.validate_settings_manifests import (
    validate_provider_manifest,
    validate_settings_manifest,
)


def test_rejects_mimo_raw_label():
    contribution = SettingContribution(
        id="legacy.mimo",
        owner="legacy",
        title="mimo",
        description="Raw legacy option",
        section=SettingSectionId.MODELS_API,
        priority=50,
        frequency="rare",
        audience="normal",
        risk="none",
        component="LegacyMimoSetting",
    )
    assert any("raw/internal" in error for error in validate_contribution(contribution))


def test_computer_control_section_is_computer_automation():
    contribution = SettingContribution(
        id="core.computer.control",
        owner="core",
        title="Computer Control",
        description="Computer operations",
        section=SettingSectionId.COMPUTER_AUTOMATION,
        priority=20,
        frequency="weekly",
        audience="normal",
        risk="high",
        component="ComputerAutomationPanel.ComputerControlCard",
    )
    assert validate_contribution(contribution) == []


def test_debug_settings_must_live_in_diagnostics():
    contribution = SettingContribution(
        id="debug.raw_state",
        owner="core",
        title="Raw state",
        description="Debug raw state",
        section=SettingSectionId.ADVANCED,
        priority=120,
        frequency="debug",
        audience="developer",
        risk="medium",
        component="DiagnosticsPanel.RawState",
    )
    assert any("debug setting" in error for error in validate_contribution(contribution))


def test_defaultspack_settings_control_center_manifests_validate():
    root = Path(__file__).resolve().parents[1] / "ecosystem" / "defaultspack" / "config" / "settings_control_center"
    errors: list[str] = []
    for path in root.rglob("*.settings.json"):
        errors.extend(validate_settings_manifest(path))
    for path in root.rglob("*.connection.json"):
        errors.extend(validate_provider_manifest(path))
    assert errors == []
