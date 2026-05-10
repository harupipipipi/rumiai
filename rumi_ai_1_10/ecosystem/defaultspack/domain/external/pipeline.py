from __future__ import annotations

from typing import Any

from domain.external.audience_policy import AudiencePolicy
from domain.external.event import ExternalEvent
from domain.external.input_profile_engine import InputProfileEngine
from domain.external.input_profile_registry import InputProfileRegistry
from domain.external.response import RumiResponse
from domain.external.response_planner import ResponsePlanner
from domain.input.submit import submit_input


def dispatch_external_event(
    event: ExternalEvent,
    *,
    input_profile_id: str | None = None,
    audience_policy: dict[str, Any] | None = None,
    context: dict[str, Any] | None = None,
    send_response: bool = False,
) -> dict[str, Any]:
    policy = AudiencePolicy(audience_policy or {"default": "allow"})
    decision = policy.evaluate(event)
    if not decision.allowed:
        return {
            "status": "denied",
            "assistant_text": "",
            "policy": decision.as_dict(),
            "event": event.as_dict(),
        }

    registry = InputProfileRegistry()
    profile = registry.get(input_profile_id or "") if input_profile_id else registry.default_for_provider(event.provider)
    if profile is None:
        return {"status": "error", "assistant_text": "", "error": f"input profile not found for {event.provider}"}
    engine = InputProfileEngine(profile)
    if not engine.matches(event):
        return {"status": "ignored", "assistant_text": "", "reason": "input profile did not match", "input_profile_id": profile.id}

    envelope = engine.to_envelope(event)
    result = submit_input(envelope, context or {})
    result["external_event"] = event.as_dict()
    result["policy"] = decision.as_dict()
    result["input_profile_id"] = profile.id
    if send_response:
        result["response_plan"] = ResponsePlanner(event.provider).plan(RumiResponse.from_result(result))
    return result
