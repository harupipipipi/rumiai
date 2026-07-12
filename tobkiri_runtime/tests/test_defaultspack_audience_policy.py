from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))

from domain.external.audience_policy import AudiencePolicy  # noqa: E402
from domain.external.normalizer import normalize_line_event  # noqa: E402
from domain.external.rate_limit import SlidingWindowRateLimiter  # noqa: E402


def _event(verified=True):
    return normalize_line_event(
        {
            "type": "message",
            "webhookEventId": "evt",
            "source": {"type": "group", "groupId": "C123", "userId": "U123"},
            "message": {"id": "m1", "type": "text", "text": "hello"},
        },
        verified=verified,
    )


def test_allow_deny_and_default_deny():
    policy = AudiencePolicy(
        {
            "default": "deny",
            "allow": [{"id": "allow-group", "provider": "line", "scope": {"type": "group", "id": "C123"}}],
            "deny": [{"id": "deny-user", "provider": "line", "actor": {"type": "user", "id": "U999"}}],
        }
    )

    decision = policy.evaluate(_event())
    assert decision.allowed is True
    assert decision.matched_rule_id == "allow-group"


def test_verified_required_and_rate_limit():
    policy = AudiencePolicy(
        {
            "default": "allow",
            "require": {"verified": True},
            "rate_limit": {"per_actor_per_minute": 1},
        },
        limiter=SlidingWindowRateLimiter(),
    )

    assert policy.evaluate(_event(verified=False)).allowed is False
    assert policy.evaluate(_event()).allowed is True
    assert policy.evaluate(_event()).reason == "actor rate limit exceeded"
