from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))

from domain.components.registry import DomainComponentRegistry, build_domain_component_roots  # noqa: E402
from domain.prompt.manager import PromptManager  # noqa: E402
from domain.prompt.resolver import PromptResolver  # noqa: E402


def test_prompt_and_template_components_are_discoverable():
    registry = DomainComponentRegistry(build_domain_component_roots(DEFAULTSPACK_ROOT))

    assert registry.get("prompts", "default_chat").id == "default_chat"
    assert registry.get("prompts", "coding").id == "coding"
    assert registry.get("prompts", "response_policy").id == "response_policy"
    assert registry.get("templates", "plain_text_prompt").id == "plain_text_prompt"


def test_prompt_resolver_reads_component_backed_prompts():
    resolver = PromptResolver()

    assert "default chat assistant" in resolver.resolve_prompt_text("default_chat")
    assert "coding assistant" in resolver.resolve_prompt_text("coding")
    assert "store only" in resolver.resolve_prompt_text("response_policy")
    assert resolver.render("coding", {}) == resolver.resolve_prompt_text("coding")


def test_prompt_resolver_reads_pack_backed_prompt_when_source_pack_is_known():
    resolver = PromptResolver()

    content = resolver.resolve_prompt_text(
        "mimo_coding_company",
        source_pack_id="rumi_operations_company_pack",
    )

    assert content is not None
    assert "MiMo Coding Company" in content


def test_prompt_manager_lists_component_prompts_and_preserves_custom_persistence(tmp_path, monkeypatch):
    import domain.prompt.manager as manager_module  # noqa: E402

    monkeypatch.setattr(manager_module, "_PROMPTS_DIR", str(tmp_path))
    manager = PromptManager()
    created = manager.create_prompt({"name": "custom_component_test", "content": "Hello {{ name }}"})

    prompt_ids = {prompt["id"] for prompt in manager.list_prompts()}
    reloaded = PromptManager().get_prompt(created["id"])

    assert {"default_chat", "coding", "response_policy"} <= prompt_ids
    assert reloaded["body"] == "Hello {{ name }}"


def test_prompt_layer_remains_provider_and_tool_independent():
    prompt_sources = [
        DEFAULTSPACK_ROOT / "domain" / "prompt" / "component_prompts.py",
        DEFAULTSPACK_ROOT / "domain" / "prompt" / "effective.py",
        DEFAULTSPACK_ROOT / "domain" / "prompt" / "resolver.py",
        DEFAULTSPACK_ROOT / "domain" / "prompt" / "template.py",
    ]
    source = "\n".join(path.read_text(encoding="utf-8") for path in prompt_sources)

    assert "domain.tool" not in source
    assert "ai_client" not in source
