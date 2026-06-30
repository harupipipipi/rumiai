"""Built-in connection provider definitions."""

from .cloudflare import CLOUDFLARE_PROVIDER
from .github import GITHUB_PROVIDER
from .google import GOOGLE_PROVIDER

__all__ = ["CLOUDFLARE_PROVIDER", "GITHUB_PROVIDER", "GOOGLE_PROVIDER"]
