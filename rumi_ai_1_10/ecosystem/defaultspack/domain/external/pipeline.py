from __future__ import annotations

from typing import Any

from domain.external.audience_policy import AudienceDecision, AudiencePolicy
from domain.external.event import ExternalEvent
from domain.external.input_profile_engine import InputProfileEngine
from domain.external.input_profile_registry import InputProfileRegistry
from domain.external.output_profile_registry import OutputProfileRegistry
from domain.external.response import RumiResponse
from domain.external.response_planner import ResponsePlanner
from domain.external.response_prompt_policy import ResponsePromptDecision, ResponsePromptPolicy
from domain.external.trigger_decision import TriggerDecisionService
from domain.input.submit import submit_input


def dispatch_external_event(
    event: ExternalEvent,
    *,
    input_profile_id: str | None = None,
    audience_policy: dict[str, Any] | None = None,
    audience_decision: AudienceDecision | dict[str, Any] | None = None,
    context: dict[str, Any] | None = None,
    send_response: bool = False,
    mentioned: bool = False,
) -> dict[str, Any]:
    policy = AudiencePolicy(audience_policy or {"default": "allow"})
    decision = _coerce_audience_decision(audience_decision) or policy.evaluate(event, mentioned=mentioned)
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

    runtime_context = dict(context or {})
    profile_policy = profile.spec.get("policy") if isinstance(getattr(profile, "spec", None), dict) else None
    if isinstance(profile_policy, dict) and profile_policy:
        runtime_context["profile_policy"] = {
            **profile_policy,
            **(runtime_context.get("profile_policy") if isinstance(runtime_context.get("profile_policy"), dict) else {}),
        }
    envelope = engine.to_envelope(event)
    trigger_decision = TriggerDecisionService.from_profile(profile, runtime_context).decide(
        event,
        envelope=envelope,
        context=runtime_context,
        requested_send_response=send_response,
    )
    pipeline_metadata = {
        "fire": bool(trigger_decision.fire),
        "send": bool(trigger_decision.send_response),
        "requested_send_response": bool(send_response),
        "trigger_action": trigger_decision.action,
    }
    runtime_context["trigger_decision"] = trigger_decision.as_dict()
    runtime_context["external_pipeline"] = pipeline_metadata
    if not trigger_decision.fire:
        ignored = {
            "status": "ignored",
            "assistant_text": "",
            "reason": trigger_decision.reason or "trigger decision did not fire",
            "external_event": event.as_dict(),
            "policy": decision.as_dict(),
            "input_profile_id": profile.id,
            "trigger_decision": trigger_decision.as_dict(),
            "metadata": {"external_pipeline": pipeline_metadata},
        }
        if send_response:
            ignored["response_plan"] = _suppressed_response_plan(event.provider, trigger_decision)
        return ignored
    result = submit_input(envelope, runtime_context)
    result["external_event"] = event.as_dict()
    result["policy"] = decision.as_dict()
    result["input_profile_id"] = profile.id
    result["trigger_decision"] = trigger_decision.as_dict()
    _result_metadata(result)["external_pipeline"] = pipeline_metadata
    prompt_decision = None
    if bool(trigger_decision.send_response):
        output_profile = _resolve_output_profile(event.provider, runtime_context)
        output_provider = output_profile.provider if output_profile is not None else event.provider
        if output_profile is not None:
            result["output_profile_id"] = output_profile.id
            metadata = _result_metadata(result)
            output_metadata = metadata.get("output") if isinstance(metadata.get("output"), dict) else {}
            metadata["output"] = output_metadata
            output_metadata.setdefault("output_profile_id", output_profile.id)
            output_metadata.setdefault("provider", output_profile.provider)
            mode = str(output_profile.spec.get("mode") or "").strip()
            if mode:
                output_metadata.setdefault("send_mode", mode)
        response = RumiResponse.from_result(result)
        prompt_decision = decide_response_prompt_policy(
            event=event,
            envelope=envelope,
            response=response,
            profile=profile,
            context=runtime_context,
        )
        if prompt_decision is not None:
            result["response_prompt_decision"] = prompt_decision.as_dict()
            _result_metadata(result)["response_prompt_decision"] = prompt_decision.as_dict()
            response.metadata["response_prompt_decision"] = prompt_decision.as_dict()
        result["response_plan"] = ResponsePlanner(output_provider).plan(response, prompt_decision=prompt_decision)
    elif send_response:
        result["response_plan"] = _suppressed_response_plan(event.provider, trigger_decision)
    return result


def _coerce_audience_decision(value: AudienceDecision | dict[str, Any] | None) -> AudienceDecision | None:
    if isinstance(value, AudienceDecision):
        return value
    if not isinstance(value, dict):
        return None
    if "allowed" not in value:
        return None
    return AudienceDecision(
        allowed=bool(value.get("allowed")),
        reason=str(value.get("reason") or ""),
        matched_rule_id=str(value.get("matched_rule_id") or ""),
    )


def _result_metadata(result: dict[str, Any]) -> dict[str, Any]:
    metadata = result.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}
        result["metadata"] = metadata
    return metadata


def _resolve_output_profile(provider: str, context: dict[str, Any]) -> Any:
    profile_id = str(context.get("output_profile_id") or context.get("response_profile_id") or "").strip()
    endpoint = context.get("webhook_endpoint") if isinstance(context.get("webhook_endpoint"), dict) else {}
    if not profile_id:
        profile_id = str(endpoint.get("response_profile_id") or "").strip()
    registry = OutputProfileRegistry()
    if profile_id:
        profile = registry.get(profile_id)
        if profile is not None:
            return profile
    return registry.default_for_provider(provider)


def _suppressed_response_plan(provider: str, trigger_decision) -> dict[str, Any]:
    decision = trigger_decision.as_dict() if hasattr(trigger_decision, "as_dict") else {}
    return {
        "provider": provider,
        "messages": [],
        "files": [],
        "fallbacks": [],
        "metadata": {
            "trigger_decision": decision,
            "response_action_plan": {
                "type": "trigger_suppressed_send",
                "external_reply": False,
                "reason": decision.get("reason") or "trigger decision disabled external send",
            },
            "external_pipeline": {
                "fire": bool(decision.get("fire", True)),
                "send": False,
                "trigger_action": decision.get("action"),
            },
        },
        "safe_defaults": ResponsePlanner(provider)._safe_defaults({}),
    }


def decide_response_prompt_policy(
    *,
    event: ExternalEvent,
    envelope,
    response: RumiResponse,
    profile,
    context: dict[str, Any] | None = None,
) -> ResponsePromptDecision | None:
    policy = ResponsePromptPolicy.from_profile(profile)
    if not policy.enabled:
        return None
    return policy.decide(event=event, envelope=envelope, response=response, context=context or {})
