from __future__ import annotations


class ExternalInputError(ValueError):
    """Base error for external input framework failures."""


class ExternalVerificationError(ExternalInputError):
    """Raised when an inbound provider signature or token fails verification."""


class ExternalPolicyDenied(ExternalInputError):
    """Raised when an audience policy denies an inbound event."""
