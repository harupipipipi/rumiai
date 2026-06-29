"""Account connection and OAuth registry foundation."""

from .models import Connection, ConnectionProvider, CredentialRef, OAuthConfig, ProviderCapability
from .oauth_service import InMemoryOAuthStateStore, OAuthClientConfig, OAuthService
from .registry import ConnectionsRegistry

__all__ = [
    "Connection",
    "ConnectionProvider",
    "ConnectionsRegistry",
    "CredentialRef",
    "InMemoryOAuthStateStore",
    "OAuthClientConfig",
    "OAuthConfig",
    "OAuthService",
    "ProviderCapability",
]
