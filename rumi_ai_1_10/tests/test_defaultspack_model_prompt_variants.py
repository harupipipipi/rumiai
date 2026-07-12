from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import pytest


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))

from domain.ai_client import request_planner  # noqa: E402
from domain.chat.ir import RumiChatIR, RumiIRMessage  # noqa: E402
from domain.chat.ir_blocks import RumiIRBlock  # noqa: E402
from domain.prompt import model_variants, variant_catalog  # noqa: E402
from domain.prompt.variant_selector import (  # noqa: E402
    PromptVariantCandidate,
    normalize_model_prompt_preferences,
    normalize_prompt_variant_metadata,
    select_prompt_variants,
)


def _candidate(
    prompt_id: str,
    *,
    tags: tuple[str, ...] = (),
    priority: int = 0,
    fallback: bool = False,
    explicit: bool = False,
    mode: str = "best_match",
    already_active: bool = False,
    text: str | None = None,
) -> PromptVariantCandidate:
    return PromptVariantCandidate(
        prompt_id=prompt_id,
        slot="model_instruction_adapter",
        tags=tags,
        priority=priority,
        fallback=fallback,
        explicit=explicit,
        selection_mode=mode,
        text=text or f"prompt:{prompt_id}",
        source=f"test.{prompt_id}",
        source_type="pack_default",
        metadata={"already_active": already_active},
    )


def _system_ir(text: str = "base") -> RumiChatIR:
    return RumiChatIR(
        conversation_id="c1",
        messages=[
            RumiIRMessage(
                conversation_id="c1",
                role="system",
                content=[RumiIRBlock(type="text", text=text)],
            ),
            RumiIRMessage(
                conversation_id="c1",
                role="user",
                content=[RumiIRBlock(type="text", text="hello")],
            ),
        ],
    )


def test_model_preferences_normalize_positive_weights_and_tags() -> None:
    normalized = normalize_model_prompt_preferences(
        {
            "prefer": {
                "Instruction.Explicit": 120,
                "format.strict": True,
                "bad tag": 999,
                "negative": -10,
            },
            "avoid": ["instruction.implicit", "FORMAT.FREEFORM"],
        }
    )

    assert normalized == {
        "prefer": {
            "instruction.explicit": 120,
            "format.strict": 100,
        },
        "avoid": {
            "instruction.implicit": 100,
            "format.freeform": 100,
        },
    }


def test_strict_candidate_wins_for_explicit_preferences() -> None:
    result = select_prompt_variants(
        [
            _candidate(
                "strict",
                tags=("instruction.explicit", "format.strict"),
            ),
            _candidate(
                "autonomous",
                tags=("instruction.concise", "autonomy.high"),
            ),
        ],
        {
            "prefer": {
                "instruction.explicit": 100,
                "format.strict": 80,
            }
        },
        model="deepseek/deepseek-chat",
        provider_id="deepseek",
    )

    assert [item["prompt_id"] for item in result["selected"]] == ["strict"]
    assert result["selected"][0]["reason"] == "positive_trait_match"
    assert result["selected"][0]["score"] == 180


def test_avoid_penalty_changes_the_winner() -> None:
    result = select_prompt_variants(
        [
            _candidate(
                "strict-but-repetitive",
                tags=("format.strict", "instruction.repetitive"),
            ),
            _candidate("strict", tags=("format.strict",)),
        ],
        {
            "prefer": {"format.strict": 100},
            "avoid": {"instruction.repetitive": 80},
        },
    )

    assert result["selected"][0]["prompt_id"] == "strict"
    rejected = result["disabled"][0]
    assert rejected["matched_avoid"] == ["instruction.repetitive"]


def test_fallback_is_used_only_when_no_positive_match_exists() -> None:
    result = select_prompt_variants(
        [
            _candidate("fallback", fallback=True, priority=-20),
            _candidate("unmatched", tags=("autonomy.high",), priority=500),
        ],
        {"prefer": {"format.strict": 100}},
    )

    assert result["selected"][0]["prompt_id"] == "fallback"
    assert result["selected"][0]["reason"] == "fallback_no_positive_match"


def test_explicit_candidate_outranks_trait_match() -> None:
    result = select_prompt_variants(
        [
            _candidate("pinned", tags=("format.light",), explicit=True),
            _candidate("strict", tags=("format.strict",)),
        ],
        {"prefer": {"format.strict": 1000}},
    )

    assert result["selected"][0]["prompt_id"] == "pinned"
    assert result["selected"][0]["reason"] == "explicit_profile_selection"


def test_additive_slot_keeps_all_candidates_in_stable_order() -> None:
    result = select_prompt_variants(
        [
            _candidate("b", mode="all", priority=1),
            _candidate("a", mode="additive", priority=2),
        ],
        {},
    )

    assert [item["prompt_id"] for item in result["selected"]] == ["a", "b"]
    assert not result["disabled"]


def test_tie_break_is_independent_of_candidate_order() -> None:
    candidates = [
        _candidate("zeta", tags=("format.strict",)),
        _candidate("alpha", tags=("format.strict",)),
    ]
    first = select_prompt_variants(
        candidates,
        {"prefer": {"format.strict": 100}},
    )
    second = select_prompt_variants(
        list(reversed(candidates)),
        {"prefer": {"format.strict": 100}},
    )

    assert first["selected"][0]["prompt_id"] == "alpha"
    assert second["selected"][0]["prompt_id"] == "alpha"


def test_generic_metadata_aliases_require_prompt_selection_namespace() -> None:
    generic = normalize_prompt_variant_metadata(
        {"tags": ["format.strict"], "slot": "adapter"}
    )
    namespaced = normalize_prompt_variant_metadata(
        {
            "prompt_selection": {
                "tags": ["format.strict"],
                "slot": "adapter",
            }
        }
    )

    assert generic["tags"] == []
    assert generic["slot"] == ""
    assert namespaced["tags"] == ["format.strict"]
    assert namespaced["slot"] == "adapter"


def test_mixed_slot_modes_fail_safe_to_best_match() -> None:
    result = select_prompt_variants(
        [
            _candidate("strict", tags=("format.strict",), mode="all"),
            _candidate("light", tags=("format.light",)),
        ],
        {"prefer": {"format.strict": 100}},
    )

    assert [item["prompt_id"] for item in result["selected"]] == ["strict"]
    assert any(
        item["code"] == "prompt_variant_mixed_selection_modes"
        for item in result["diagnostics"]
    )


def test_exact_model_preferences_override_provider_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        variant_catalog,
        "_model_catalog_records",
        lambda model: (
            {
                "provider_id": "deepseek",
                "metadata": {
                    "prompt_preferences": {
                        "prefer": {"format.strict": 200}
                    }
                },
            },
            {
                "provider_id": "deepseek",
                "metadata": {
                    "config": {
                        "prompt_preferences": {
                            "prefer": {
                                "format.strict": 20,
                                "instruction.explicit": 50,
                            },
                            "avoid": ["format.freeform"],
                        }
                    }
                },
            },
        ),
    )

    resolved = variant_catalog.resolve_model_prompt_preferences(
        "deepseek/deepseek-chat"
    )

    assert resolved["prefer"] == {
        "format.strict": 200,
        "instruction.explicit": 50,
    }
    assert resolved["avoid"] == {"format.freeform": 100}
    assert resolved["source_chain"] == ["provider", "model"]


def test_profile_candidates_merge_manifest_profile_and_active_selection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    effective: dict[str, dict[str, Any]] = {
        "strict": {
            "content": "strict body",
            "source": "pack.strict",
            "source_type": "pack_default",
            "metadata": {},
        },
        "fallback": {
            "content": "fallback body",
            "source": "pack.fallback",
            "source_type": "pack_default",
            "metadata": {},
        },
        "active": {
            "content": "active body",
            "source": "pack.active",
            "source_type": "pack_default",
            "metadata": {
                "prompt_selection": {
                    "slot": "model_instruction_adapter",
                    "tags": ["autonomy.high"],
                }
            },
        },
    }
    monkeypatch.setattr(variant_catalog, "_profile_workspace", lambda profile: {})
    monkeypatch.setattr(
        variant_catalog,
        "_resolve_effective_candidate",
        lambda **kwargs: effective[kwargs["prompt_id"]],
    )
    profile = {
        "profile_id": "p1",
        "base_pack": "defaultspack",
        "metadata": {
            "prompt_selection": {
                "slots": {
                    "model_instruction_adapter": {
                        "candidates": ["strict"],
                        "fallback_prompt_id": "fallback",
                    }
                },
                "prompts": {
                    "strict": {
                        "tags": ["format.strict"],
                        "priority": 40,
                    }
                },
            }
        },
    }
    context = {
        "prompt_usage": {
            "segments": [
                {
                    "kind": "prompt",
                    "status": "active",
                    "prompt_id": "active",
                }
            ]
        }
    }

    candidates, diagnostics = variant_catalog.resolve_profile_prompt_candidates(
        profile,
        context,
    )
    by_id = {candidate.prompt_id: candidate for candidate in candidates}

    assert diagnostics == []
    assert set(by_id) == {"strict", "fallback", "active"}
    assert by_id["strict"].tags == ("format.strict",)
    assert by_id["fallback"].fallback is True
    assert by_id["active"].explicit is True
    assert by_id["active"].metadata["already_active"] is True


def test_runtime_uses_final_routed_model_and_keeps_original_ir(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        model_variants,
        "_load_active_profile",
        lambda context: {"profile_id": "p1"},
    )
    monkeypatch.setattr(
        model_variants,
        "resolve_model_prompt_preferences",
        lambda model: {
            "prefer": {"format.strict": 100},
            "avoid": {},
            "provider_id": "deepseek",
            "source_chain": ["model"],
        },
    )
    monkeypatch.setattr(
        model_variants,
        "resolve_profile_prompt_candidates",
        lambda profile, context: (
            [
                _candidate(
                    "strict",
                    tags=("format.strict",),
                    text="STRICT ADAPTER",
                ),
                _candidate(
                    "autonomous",
                    tags=("autonomy.high",),
                    text="AUTONOMOUS ADAPTER",
                ),
            ],
            [],
        ),
    )
    monkeypatch.setattr(
        model_variants,
        "_record_prompt_selection",
        lambda context, selection: None,
    )
    original = _system_ir()
    context = {
        "model_routing": {
            "original_model": "anthropic/claude-sonnet",
            "selected_model": "deepseek/deepseek-chat",
        }
    }

    adapted, selection = model_variants.apply_model_prompt_variants(
        original,
        "deepseek/deepseek-chat",
        context,
    )

    assert original.messages[0].content[0].text == "base"
    assert adapted.messages[0].content[0].text == "base\n\nSTRICT ADAPTER"
    assert selection["model"] == "deepseek/deepseek-chat"
    assert selection["original_model"] == "anthropic/claude-sonnet"
    assert context["model_prompt_selection"]["selected"][0][
        "prompt_id"
    ] == "strict"
    assert "text" not in context["model_prompt_selection"]["selected"][0]
    assert "source" not in context["model_prompt_selection"]["selected"][0]


def test_already_active_explicit_variant_is_not_duplicated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        model_variants,
        "_load_active_profile",
        lambda context: {"profile_id": "p1"},
    )
    monkeypatch.setattr(
        model_variants,
        "resolve_model_prompt_preferences",
        lambda model: {
            "prefer": {"format.strict": 100},
            "avoid": {},
            "provider_id": "deepseek",
            "source_chain": ["model"],
        },
    )
    monkeypatch.setattr(
        model_variants,
        "resolve_profile_prompt_candidates",
        lambda profile, context: (
            [
                _candidate(
                    "pinned",
                    tags=("format.light",),
                    explicit=True,
                    already_active=True,
                    text="PINNED",
                ),
                _candidate(
                    "strict",
                    tags=("format.strict",),
                    text="STRICT",
                ),
            ],
            [],
        ),
    )
    monkeypatch.setattr(
        model_variants,
        "_record_prompt_selection",
        lambda context, selection: None,
    )
    original = _system_ir("base already contains PINNED")

    adapted, selection = model_variants.apply_model_prompt_variants(
        original,
        "deepseek/deepseek-chat",
        {},
    )

    assert adapted is original
    assert selection["status"] == "selected_existing"
    assert selection["selected"][0]["prompt_id"] == "pinned"


def test_runtime_failure_is_fail_soft_and_does_not_expose_error_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail(context: Mapping[str, Any]) -> dict[str, Any]:
        raise RuntimeError("secret path and token")

    monkeypatch.setattr(model_variants, "_load_active_profile", fail)
    original = _system_ir()
    context: dict[str, Any] = {}

    adapted, result = model_variants.apply_model_prompt_variants(
        original,
        "deepseek/deepseek-chat",
        context,
    )

    assert adapted is original
    assert result["status"] == "selection_error"
    assert result["diagnostics"][0]["error_type"] == "RuntimeError"
    assert "secret" not in str(result)


def test_disabled_and_existing_variants_do_not_inflate_token_totals() -> None:
    selection = {
        "model": "deepseek/deepseek-chat",
        "original_model": "deepseek/deepseek-chat",
        "selected": [
            {
                "prompt_id": "existing",
                "slot": "model_instruction_adapter",
                "text": "already counted",
                "already_active": True,
                "source_type": "pack_default",
            },
            {
                "prompt_id": "new",
                "slot": "extra_adapter",
                "text": "new text",
                "already_active": False,
                "source_type": "pack_default",
            },
        ],
        "disabled": [
            {
                "prompt_id": "rejected",
                "slot": "model_instruction_adapter",
                "text": "not sent",
                "source_type": "pack_default",
            }
        ],
    }

    segments = model_variants._selection_usage_segments(selection)
    by_id = {segment["prompt_id"]: segment for segment in segments}

    assert by_id["existing"]["tokens"] == 0
    assert by_id["new"]["tokens"] > 0
    assert by_id["rejected"]["tokens"] == 0
    assert by_id["rejected"]["metadata"]["candidate_tokens"] > 0


def test_request_planner_applies_variants_after_final_model_selection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original = _system_ir()
    adapted = _system_ir("adapted")
    seen: dict[str, Any] = {}

    def apply(ir: Any, model: str, context: dict[str, Any]):
        seen["applied_model"] = model
        seen["context"] = context
        return adapted, {"status": "applied"}

    def degrade(ir: Any, **kwargs: Any):
        seen["degraded_ir"] = ir
        seen["degraded_model"] = kwargs["model"]
        seen["degraded_context"] = kwargs["context"]
        return "planned"

    monkeypatch.setattr(request_planner, "apply_model_prompt_variants", apply)
    monkeypatch.setattr(request_planner, "degrade_request", degrade)
    context = {
        "model_routing": {
            "original_model": "anthropic/claude-sonnet",
            "selected_model": "deepseek/deepseek-chat",
        }
    }

    result = request_planner.plan_model_request(
        original,
        "deepseek/deepseek-chat",
        {},
        [],
        {},
        context,
    )

    assert result == "planned"
    assert seen["applied_model"] == "deepseek/deepseek-chat"
    assert seen["degraded_model"] == "deepseek/deepseek-chat"
    assert seen["degraded_ir"] is adapted
    assert seen["degraded_context"] is context
