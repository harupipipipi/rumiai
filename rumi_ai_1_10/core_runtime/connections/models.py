from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Literal, Mapping

LocalizedText = str | Mapping[str, str]
AuthType = Literal["oauth2", "api_key", "device_code", "none"]
ServiceKind = Literal["cloud", "google", "storage", "email", "mcp", "dev", "custom"]
ConnectionStatus = Literal[
    "connected",
    "not_connected",
    "needs_official_app",
    "missing_self_host_config",
    "expired",
    "error",
    "requires_profile_binding",
]
RiskLevel = Literal["none", "low", "medium", "high"]


@dataclass(frozen=True)
class ProviderCapability:
    id: str
    display_name: LocalizedText
    description: LocalizedText
    risk: RiskLevel = "none"

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "ProviderCapability":
        return cls(
            id=str(raw["id"]),
            display_name=raw.get("displayName", raw.get("display_name", raw["id"])),
            description=raw.get("description", ""),
            risk=raw.get("risk", "none"),
        )


@dataclass(frozen=True)
class OAuthConfig:
    authorization_url: str
    token_url: str
    revoke_url: str | None = None
    userinfo_url: str | None = None
    default_scopes: list[str] = field(default_factory=list)
    pkce_supported: bool = True
    token_endpoint_auth_method: str | None = None

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "OAuthConfig":
        return cls(
            authorization_url=str(raw["authorization_url"]),
            token_url=str(raw["token_url"]),
            revoke_url=raw.get("revoke_url"),
            userinfo_url=raw.get("userinfo_url"),
            default_scopes=list(raw.get("default_scopes", [])),
            pkce_supported=bool(raw.get("pkce_supported", True)),
            token_endpoint_auth_method=raw.get("token_endpoint_auth_method"),
        )


@dataclass(frozen=True)
class ConnectionProvider:
    provider_id: str
    display_name: LocalizedText
    description: LocalizedText
    icon: str
    service_kind: ServiceKind
    auth_type: AuthType
    official_broker_supported: bool
    self_host_client_supported: bool
    capabilities: list[ProviderCapability]
    priority: int
    oauth: OAuthConfig | None = None
    services: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> "ConnectionProvider":
        auth = raw.get("auth", {})
        return cls(
            provider_id=str(raw["provider_id"]),
            display_name=raw.get("display_name", raw["provider_id"]),
            description=raw.get("description", ""),
            icon=raw.get("icon", raw["provider_id"]),
            service_kind=raw.get("service_kind", "custom"),
            auth_type=auth.get("type", raw.get("auth_type", "none")),
            official_broker_supported=bool(auth.get("official_broker_supported", False)),
            self_host_client_supported=bool(auth.get("self_host_client_supported", False)),
            capabilities=[ProviderCapability.from_dict(item) for item in raw.get("capabilities", [])],
            priority=int(raw.get("settings", {}).get("priority", raw.get("priority", 100))),
            oauth=OAuthConfig.from_dict(auth["oauth"]) if "oauth" in auth else None,
            services=list(raw.get("services", [])),
            metadata=dict(raw.get("metadata", {})),
        )

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["providerId"] = data.pop("provider_id")
        data["displayName"] = data.pop("display_name")
        data["serviceKind"] = data.pop("service_kind")
        data["authType"] = data.pop("auth_type")
        data["officialBrokerSupported"] = data.pop("official_broker_supported")
        data["selfHostClientSupported"] = data.pop("self_host_client_supported")
        data["pkceSupported"] = bool(self.oauth.pkce_supported) if self.oauth else False
        data["capabilities"] = [
            {
                "id": capability.id,
                "displayName": capability.display_name,
                "description": capability.description,
                "risk": capability.risk,
            }
            for capability in self.capabilities
        ]
        return data


@dataclass(frozen=True)
class CredentialRef:
    credential_id: str
    provider_id: str
    connection_id: str
    key_version: str


@dataclass(frozen=True)
class Connection:
    connection_id: str
    provider_id: str
    account_label: str
    status: ConnectionStatus
    scopes_granted: list[str] = field(default_factory=list)
    capabilities_granted: list[str] = field(default_factory=list)
    credential_ref: CredentialRef | None = None
    profile_bindings: list[str] = field(default_factory=list)
    created_at: str | None = None
    updated_at: str | None = None
    error_message: str | None = None

    def safe_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data.pop("credential_ref", None)
        data["connectionId"] = data.pop("connection_id")
        data["providerId"] = data.pop("provider_id")
        data["accountLabel"] = data.pop("account_label")
        data["scopesGranted"] = data.pop("scopes_granted")
        data["capabilitiesGranted"] = data.pop("capabilities_granted")
        data["profileBindings"] = data.pop("profile_bindings")
        data["createdAt"] = data.pop("created_at")
        data["updatedAt"] = data.pop("updated_at")
        data["errorMessage"] = data.pop("error_message")
        return data
