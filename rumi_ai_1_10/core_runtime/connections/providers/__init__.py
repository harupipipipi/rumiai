"""Built-in connection provider definitions."""

from .cloudflare import CLOUDFLARE_PROVIDER
from .google import GOOGLE_PROVIDER

__all__ = ["CLOUDFLARE_PROVIDER", "GOOGLE_PROVIDER"]
