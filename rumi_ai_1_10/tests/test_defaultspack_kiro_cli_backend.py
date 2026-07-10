from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


def test_kiro_cli_is_coding_backend_not_llm_provider():
    from domain.ai_client.providers import get_provider_catalog_map
    from domain.components.registry import DomainComponentRegistry, build_domain_component_roots

    registry = DomainComponentRegistry(build_domain_component_roots(DEFAULTSPACK_ROOT))
    backend = registry.get("coding_backends", "kiro-cli")

    assert backend is not None
    assert backend.kind == "coding_backend"
    component = backend.as_dict()
    assert component["policy"]["do_not_treat_as_llm_provider"] is True
    assert component["policy"]["discovery_is_read_only"] is True
    assert component["capabilities"]["model_discovery"] is True
    assert component["capabilities"]["coding_session"] is False
    assert "kiro-cli" not in get_provider_catalog_map()


def test_normalize_kiro_models_preserves_exact_backend_scoped_ids():
    from domain.kiro.cli import normalize_kiro_models

    models = normalize_kiro_models(
        {
            "models": [
                {
                    "id": "auto",
                    "displayName": "Auto",
                    "contextWindow": 1_000_000,
                    "effortLevels": ["low", "high", "bogus"],
                    "status": "active",
                },
                {
                    "modelId": "anthropic/claude-sonnet-versioned",
                    "label": "Claude Sonnet",
                    "stage": "experimental",
                },
                {"id": "auto", "displayName": "duplicate"},
            ]
        },
        connection_id="account-a",
    )

    assert [item["agent_model_id"] for item in models] == [
        "auto",
        "anthropic/claude-sonnet-versioned",
    ]
    assert models[0]["qualified_agent_model_id"] == "acp/kiro-cli/account-a/auto"
    assert models[0]["context_window"] == 1_000_000
    assert models[0]["effort_values"] == ["low", "high"]
    assert models[1]["qualified_agent_model_id"] == (
        "acp/kiro-cli/account-a/anthropic/claude-sonnet-versioned"
    )
    assert models[1]["lifecycle"] == "experimental"


def test_kiro_headless_command_plan_is_structured_and_least_privilege():
    from domain.kiro.cli import build_kiro_headless_command

    argv = build_kiro_headless_command(
        "Review this diff",
        command="kiro-cli-test-command",
        trusted_tools=["read", "grep", "read"],
        effort="high",
        agent="reviewer",
    )

    assert argv == [
        "kiro-cli-test-command",
        "chat",
        "--no-interactive",
        "--trust-tools=read,grep",
        "--effort",
        "high",
        "--agent",
        "reviewer",
        "Review this diff",
    ]
    assert "--trust-all-tools" not in argv
