from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .event import ExternalEvent
from .rate_limit import GLOBAL_RATE_LIMITER, SlidingWindowRateLimiter


@dataclass
class AudienceDecision:
    allowed: bool
    reason: str
    matched_rule_id: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "reason": self.reason,
            "matched_rule_id": self.matched_rule_id,
        }


class AudiencePolicy:
    def __init__(self, policy: dict[str, Any] | None = None, *, limiter: SlidingWindowRateLimiter | None = None) -> None:
        self.policy = policy if isinstance(policy, dict) else {}
        self.limiter = limiter or GLOBAL_RATE_LIMITER

    def evaluate(self, event: ExternalEvent, *, mentioned: bool = False) -> AudienceDecision:
        require = self.policy.get("require") if isinstance(self.policy.get("require"), dict) else {}
        if bool(require.get("verified")) and not event.verified:
            return AudienceDecision(False, "verification required")
        if bool(require.get("mention")) and not mentioned:
            return AudienceDecision(False, "mention required")
        required_types = require.get("message_types")
        if isinstance(required_types, list) and required_types:
            message_type = str(event.event.get("message_type") or event.event.get("type") or "")
            if message_type not in {str(item) for item in required_types}:
                return AudienceDecision(False, "message type not allowed")

        rate = self.policy.get("rate_limit") if isinstance(self.policy.get("rate_limit"), dict) else {}
        actor_limit = int(rate.get("per_actor_per_minute") or 0)
        if actor_limit and not self.limiter.allow(f"actor:{event.provider}:{event.actor.id}", actor_limit):
            return AudienceDecision(False, "actor rate limit exceeded")
        scope_limit = int(rate.get("per_scope_per_minute") or 0)
        if scope_limit and not self.limiter.allow(f"scope:{event.provider}:{event.scope.type}:{event.scope.id}", scope_limit):
            return AudienceDecision(False, "scope rate limit exceeded")

        for index, rule in enumerate(self._rules("deny")):
            if self._matches_rule(rule, event):
                return AudienceDecision(False, "matched deny rule", self._rule_id(rule, index, "deny"))

        for index, rule in enumerate(self._rules("allow")):
            if self._matches_rule(rule, event):
                return AudienceDecision(True, "matched allow rule", self._rule_id(rule, index, "allow"))

        default = str(self.policy.get("default") or "deny").strip().lower()
        if default == "allow":
            return AudienceDecision(True, "default allow")
        return AudienceDecision(False, "default deny")

    def _rules(self, key: str) -> list[dict[str, Any]]:
        rules = self.policy.get(key)
        return [rule for rule in rules if isinstance(rule, dict)] if isinstance(rules, list) else []

    @staticmethod
    def _rule_id(rule: dict[str, Any], index: int, kind: str) -> str:
        return str(rule.get("id") or f"{kind}:{index}")

    @staticmethod
    def _matches_rule(rule: dict[str, Any], event: ExternalEvent) -> bool:
        provider = rule.get("provider")
        if provider and str(provider) != event.provider:
            return False
        for attr in ("workspace", "scope", "actor"):
            expected = rule.get(attr)
            if isinstance(expected, dict):
                principal = getattr(event, attr)
                expected_type = expected.get("type")
                expected_id = expected.get("id")
                if expected_type and str(expected_type) != principal.type:
                    return False
                if expected_id and str(expected_id) != principal.id:
                    return False
        return True


def evaluate_audience_policy(policy: dict[str, Any] | None, event: ExternalEvent, *, mentioned: bool = False) -> dict[str, Any]:
    return AudiencePolicy(policy).evaluate(event, mentioned=mentioned).as_dict()
