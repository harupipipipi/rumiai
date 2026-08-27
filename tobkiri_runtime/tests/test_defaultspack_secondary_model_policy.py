from __future__ import annotations

import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))

from domain.ai_client.secondary_model_policy import (  # noqa: E402
    ModelPolicyResolutionError,
    resolve_secondary_model_policy,
)


def _profile(
    profile_id: str,
    *,
    configured: bool = True,
    supports_thinking: bool = True,
    thinking_levels: list[str] | None = None,
    **capabilities: bool,
) -> dict:
    return {
        "profile_id": profile_id,
        "provider_id": profile_id.split("/", 1)[0],
        "model_id": profile_id.split("/", 1)[-1],
        "configured": configured,
        "availability": {
            "active": configured,
            "configured": configured,
            "status": "configured" if configured else "missing_api_key",
        },
        "supports_thinking": supports_thinking,
        "thinking_levels": thinking_levels or ["none", "low", "medium", "high"],
        **capabilities,
    }


def test_inherit_conversation_resolves_again_for_each_invocation() -> None:
    profiles = [_profile("openai/first"), _profile("openai/second")]

    first = resolve_secondary_model_policy(
        {"mode": "inherit_conversation"},
        {"mode": "inherit_conversation"},
        context={
            "conversation_model": "openai/first",
            "conversation_thinking_level": "low",
        },
        profiles=profiles,
    )
    second = resolve_secondary_model_policy(
        {"mode": "inherit_conversation"},
        {"mode": "inherit_conversation"},
        context={
            "conversation_model": "openai/second",
            "conversation_thinking_level": "high",
        },
        profiles=profiles,
    )

    assert first["resolved_profile_id"] == "openai/first"
    assert first["thinking_level"] == "low"
    assert second["resolved_profile_id"] == "openai/second"
    assert second["thinking_level"] == "high"


def test_snapshot_captures_once_and_ignores_later_conversation_changes() -> None:
    profiles = [_profile("openai/first"), _profile("openai/second")]
    captured = resolve_secondary_model_policy(
        {"mode": "snapshot"},
        context={"conversation_model": "openai/first"},
        profiles=profiles,
    )

    replayed = resolve_secondary_model_policy(
        {
            "mode": "snapshot",
            "snapshot_profile_id": captured["snapshot_profile_id"],
        },
        context={"conversation_model": "openai/second"},
        profiles=profiles,
    )

    assert captured["snapshot_captured"] is True
    assert replayed["resolved_profile_id"] == "openai/first"
    assert replayed["snapshot_captured"] is False


def test_fixed_profile_uses_only_declared_fallback_when_unavailable() -> None:
    profiles = [
        _profile("openai/pinned", configured=False),
        _profile("local/fallback"),
    ]

    receipt = resolve_secondary_model_policy(
        {
            "mode": "fixed",
            "profile_id": "openai/pinned",
            "fallback_profile_id": "local/fallback",
        },
        profiles=profiles,
    )

    assert receipt["resolved_profile_id"] == "local/fallback"
    assert receipt["resolution_source"] == "fallback_profile"
    assert receipt["fallback_reason"].startswith("MODEL_API_KEY_MISSING:")


def test_fixed_profile_fails_closed_for_missing_api_key_without_fallback() -> None:
    with pytest.raises(ModelPolicyResolutionError) as captured:
        resolve_secondary_model_policy(
            {"mode": "fixed", "profile_id": "openai/pinned"},
            profiles=[_profile("openai/pinned", configured=False)],
        )

    assert captured.value.code == "MODEL_API_KEY_MISSING"
    assert captured.value.receipt["error"]["code"] == "MODEL_API_KEY_MISSING"


def test_required_capabilities_are_checked_before_fixed_invocation() -> None:
    with pytest.raises(ModelPolicyResolutionError) as captured:
        resolve_secondary_model_policy(
            {
                "mode": "fixed",
                "profile_id": "local/text",
                "required_capabilities": ["model.image_input"],
            },
            profiles=[_profile("local/text", supports_image_input=False)],
        )

    assert captured.value.code == "MODEL_CAPABILITY_UNSATISFIED"


def test_auto_route_skips_unavailable_and_capability_incompatible_profiles() -> None:
    receipt = resolve_secondary_model_policy(
        {
            "mode": "auto_route",
            "required_capabilities": ["model.image_input"],
        },
        context={"preferred_model": "openai/missing-key"},
        profiles=[
            _profile("openai/missing-key", configured=False, supports_image_input=True),
            _profile("local/text", supports_image_input=False),
            _profile("local/vision", supports_image_input=True),
        ],
    )

    assert receipt["resolved_profile_id"] == "local/vision"
    assert receipt["resolution_source"] == "canonical_catalog_fallback"
    assert receipt["fallback_reason"].startswith("MODEL_API_KEY_MISSING:")


def test_auto_route_fails_before_invocation_when_no_profile_meets_requirements() -> None:
    with pytest.raises(ModelPolicyResolutionError) as captured:
        resolve_secondary_model_policy(
            {
                "mode": "auto_route",
                "required_capabilities": ["model.audio_input"],
            },
            context={"preferred_model": "local/text"},
            profiles=[_profile("local/text", supports_audio_input=False)],
        )

    assert captured.value.code == "MODEL_CAPABILITY_UNSATISFIED"


def test_unsupported_fixed_thinking_level_fails_before_invocation() -> None:
    with pytest.raises(ModelPolicyResolutionError) as captured:
        resolve_secondary_model_policy(
            {"mode": "fixed", "profile_id": "local/text"},
            {"mode": "fixed", "level": "high"},
            profiles=[
                _profile(
                    "local/text",
                    supports_thinking=False,
                    thinking_levels=["none"],
                )
            ],
        )

    assert captured.value.code == "MODEL_THINKING_UNSUPPORTED"


def test_deterministic_replay_uses_recorded_concrete_profile() -> None:
    profiles = [_profile("openai/recorded"), _profile("openai/current")]
    receipt = resolve_secondary_model_policy(
        {"mode": "inherit_conversation"},
        context={
            "replay_mode": "deterministic",
            "conversation_model": "openai/current",
        },
        profiles=profiles,
        replay_receipt={"resolved_profile_id": "openai/recorded"},
    )

    assert receipt["resolved_profile_id"] == "openai/recorded"
    assert receipt["resolution_source"] == "replay_receipt"
    assert receipt["replay"] is True


def test_receipt_records_requested_and_resolved_thinking_policy() -> None:
    receipt = resolve_secondary_model_policy(
        {"mode": "fixed", "profile_id": "local/reasoner"},
        {"mode": "fixed", "level": "medium"},
        profiles=[_profile("local/reasoner")],
    )

    assert receipt["requested_model_policy"]["mode"] == "fixed"
    assert receipt["requested_thinking_policy"] == {
        "mode": "fixed",
        "level": "medium",
    }
    assert receipt["thinking_translation"] == {
        "requested": "medium",
        "resolved": "medium",
        "translated": False,
    }
