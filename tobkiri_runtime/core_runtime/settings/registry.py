from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from .models import SECTION_ORDER, SETTING_SECTIONS, SettingContribution, SettingSectionId
from .validators import assert_valid_contributions


class SettingsRegistry:
    """Registry for core and pack Settings contributions.

    Packs must register Settings through this class. Direct UI mutation is not allowed.
    """

    def __init__(self) -> None:
        self._contributions: dict[str, SettingContribution] = {}

    def register(self, contribution: SettingContribution) -> None:
        assert_valid_contributions([contribution])
        if contribution.id in self._contributions:
            raise ValueError(f"Duplicate Settings contribution id: {contribution.id}")
        self._contributions[contribution.id] = contribution

    def register_many(self, contributions: Iterable[SettingContribution]) -> None:
        items = list(contributions)
        assert_valid_contributions(items)
        for item in items:
            self.register(item)

    def load_manifest(self, manifest_path: str | Path) -> list[SettingContribution]:
        path = Path(manifest_path)
        raw = json.loads(path.read_text(encoding="utf-8"))
        contributions = [SettingContribution.from_dict(item) for item in raw.get("contributions", [])]
        self.register_many(contributions)
        return contributions

    def load_manifest_dir(self, root: str | Path) -> None:
        for path in Path(root).rglob("*.settings.json"):
            self.load_manifest(path)

    def list_sections(self) -> list[dict]:
        return [section.to_dict() for section in sorted(SETTING_SECTIONS, key=lambda s: s.order)]

    def list_contributions(self, section: SettingSectionId | None = None) -> list[dict]:
        items = list(self._contributions.values())
        if section is not None:
            items = [item for item in items if item.section == section]
        items.sort(key=lambda item: (SECTION_ORDER.get(item.section, 999), _status_weight(item.status), item.priority, item.id))
        return [item.to_dict() for item in items]


def _status_weight(status: str | None) -> int:
    if status in {"missing", "unapproved"}:
        return -20
    if status == "error":
        return -10
    return 0


def build_default_registry() -> SettingsRegistry:
    registry = SettingsRegistry()
    registry.register_many(
        [
            SettingContribution(
                id="core.quick.default_model",
                owner="core",
                title={"en": "Default model", "ja": "デフォルトモデル"},
                description={"en": "Choose the model Rumi uses for normal conversations.", "ja": "通常会話で使うモデルを選びます。"},
                section=SettingSectionId.QUICK_SETUP,
                priority=10,
                frequency="daily",
                audience="normal",
                risk="none",
                component="QuickSetupPanel.DefaultModelCard",
                status="missing",
            ),
            SettingContribution(
                id="core.connections.cloudflare",
                owner="core",
                title="Cloudflare",
                description="Run cloud-capable sandbox work in your Cloudflare account and bridge PC-bound tools through a named Tunnel.",
                section=SettingSectionId.ACCOUNTS_CONNECTIONS,
                priority=30,
                frequency="weekly",
                audience="normal",
                risk="medium",
                component="AccountsConnectionsPanel.CloudflareCard",
                profile_aware=True,
                status="missing",
            ),
            SettingContribution(
                id="core.computer.control",
                owner="core",
                title={"en": "Computer Control", "ja": "コンピューター操作"},
                description="Allow Rumi to observe and operate the local computer with explicit approval controls.",
                section=SettingSectionId.COMPUTER_AUTOMATION,
                priority=20,
                frequency="weekly",
                audience="normal",
                risk="high",
                component="ComputerAutomationPanel.ComputerControlCard",
                profile_aware=True,
                status="unapproved",
            ),
            SettingContribution(
                id="core.workspace.automation_indicator",
                owner="core",
                title={"en": "Automation visual indicator", "ja": "自動操作の表示"},
                description="Choose how Rumi shows that computer automation is active.",
                section=SettingSectionId.WORKSPACE_UI,
                priority=80,
                frequency="rare",
                audience="power",
                risk="none",
                component="WorkspaceUiPanel.AutomationIndicatorCard",
                status="configured",
            ),
        ]
    )
    return registry
