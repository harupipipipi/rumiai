from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Literal, Mapping

LocalizedText = str | Mapping[str, str]


class SettingSectionId(str, Enum):
    QUICK_SETUP = "quick_setup"
    MODELS_API = "models_api"
    ACCOUNTS_CONNECTIONS = "accounts_connections"
    TOOLS_MCP = "tools_mcp"
    COMPUTER_AUTOMATION = "computer_automation"
    WORKSPACE_UI = "workspace_ui"
    PROFILES = "profiles"
    PRIVACY_SECURITY = "privacy_security"
    PACKS_EXTENSIONS = "packs_extensions"
    ADVANCED = "advanced"
    DIAGNOSTICS = "diagnostics"


SettingFrequency = Literal["daily", "weekly", "rare", "debug"]
SettingAudience = Literal["normal", "power", "developer"]
SettingRisk = Literal["none", "low", "medium", "high"]
SettingStatus = Literal["configured", "missing", "disabled", "unapproved", "error", "not_available"]


@dataclass(frozen=True)
class SettingSection:
    id: SettingSectionId
    title: LocalizedText
    description: LocalizedText
    icon: str
    order: int

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["id"] = self.id.value
        return data


@dataclass(frozen=True)
class SettingContribution:
    id: str
    owner: str
    title: LocalizedText
    description: LocalizedText
    section: SettingSectionId
    priority: int
    frequency: SettingFrequency
    audience: SettingAudience
    risk: SettingRisk
    component: str
    requires: list[str] = field(default_factory=list)
    visible_when: dict[str, Any] = field(default_factory=dict)
    profile_aware: bool = False
    search_keywords: list[str] = field(default_factory=list)
    status: SettingStatus | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "SettingContribution":
        return cls(
            id=str(raw["id"]),
            owner=str(raw["owner"]),
            title=raw["title"],
            description=raw["description"],
            section=SettingSectionId(str(raw["section"])),
            priority=int(raw["priority"]),
            frequency=raw.get("frequency", "rare"),
            audience=raw.get("audience", "normal"),
            risk=raw.get("risk", "none"),
            component=str(raw["component"]),
            requires=list(raw.get("requires", [])),
            visible_when=dict(raw.get("visibleWhen", raw.get("visible_when", {}))),
            profile_aware=bool(raw.get("profileAware", raw.get("profile_aware", False))),
            search_keywords=list(raw.get("searchKeywords", raw.get("search_keywords", []))),
            status=raw.get("status"),
            metadata=dict(raw.get("metadata", {})),
        )

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["section"] = self.section.value
        data["visibleWhen"] = data.pop("visible_when")
        data["profileAware"] = data.pop("profile_aware")
        data["searchKeywords"] = data.pop("search_keywords")
        return data


SETTING_SECTIONS: list[SettingSection] = [
    SettingSection(SettingSectionId.QUICK_SETUP, {"en": "Quick Setup", "ja": "クイック設定"}, {"en": "Fix setup blockers first.", "ja": "最初に必要な設定です。"}, "sparkles", 10),
    SettingSection(SettingSectionId.MODELS_API, {"en": "Models & API", "ja": "モデルとAPI"}, {"en": "Models, providers, API keys, routing, and fallback.", "ja": "モデル、APIキー、ルーティングを管理します。"}, "brain", 20),
    SettingSection(SettingSectionId.ACCOUNTS_CONNECTIONS, {"en": "Accounts & Connections", "ja": "アカウント連携"}, {"en": "OAuth and API-key account connections.", "ja": "OAuth/APIキー連携を管理します。"}, "plug", 30),
    SettingSection(SettingSectionId.TOOLS_MCP, {"en": "Tools & MCP", "ja": "ツールとMCP"}, {"en": "Tools, MCP servers, and tool permission policy.", "ja": "ツール、MCP、許可設定です。"}, "wrench", 40),
    SettingSection(SettingSectionId.COMPUTER_AUTOMATION, {"en": "Computer & Automation", "ja": "コンピューター操作"}, {"en": "Computer control, browser automation, and cloud integrations.", "ja": "画面操作、自動化、クラウド連携です。"}, "monitor", 50),
    SettingSection(SettingSectionId.WORKSPACE_UI, {"en": "Workspace & UI", "ja": "ワークスペースとUI"}, {"en": "Theme, layout, panes, shortcuts, and visual indicators.", "ja": "テーマ、レイアウト、表示です。"}, "layout", 60),
    SettingSection(SettingSectionId.PROFILES, {"en": "Profiles", "ja": "プロファイル"}, {"en": "Profile-specific runtime presets.", "ja": "実行環境プリセットです。"}, "user-cog", 70),
    SettingSection(SettingSectionId.PRIVACY_SECURITY, {"en": "Privacy & Security", "ja": "プライバシーとセキュリティ"}, {"en": "Credentials, approvals, audit logs, and retention.", "ja": "認証情報、承認、監査、保持設定です。"}, "shield", 80),
    SettingSection(SettingSectionId.PACKS_EXTENSIONS, {"en": "Packs & Extensions", "ja": "パックと拡張"}, {"en": "Pack install/update/enable and extension settings.", "ja": "パックと拡張の管理です。"}, "package", 90),
    SettingSection(SettingSectionId.ADVANCED, {"en": "Advanced", "ja": "高度な設定"}, {"en": "Rare power-user settings.", "ja": "高度な設定です。"}, "sliders", 100),
    SettingSection(SettingSectionId.DIAGNOSTICS, {"en": "Diagnostics", "ja": "診断"}, {"en": "Logs, health checks, debug state, and migrations.", "ja": "ログ、診断、移行結果です。"}, "activity", 110),
]

SECTION_ORDER = {section.id: section.order for section in SETTING_SECTIONS}
