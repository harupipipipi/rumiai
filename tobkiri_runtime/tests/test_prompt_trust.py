from __future__ import annotations

import sys
from pathlib import Path


DEFAULTSPACK_ROOT = Path(__file__).resolve().parents[1] / "ecosystem" / "defaultspack"
if str(DEFAULTSPACK_ROOT) not in sys.path:
    sys.path.insert(0, str(DEFAULTSPACK_ROOT))

from domain.prompt.resolver import PromptResolver  # noqa: E402


class _FakeRegistry:
    def get(self, kind: str, prompt_id: str):
        if kind == "prompt" and prompt_id == "default_chat":
            return {
                "id": prompt_id,
                "source_pack_id": "untrustedpack",
                "config": {"template_file": "prompt.md"},
            }
        return None


class _FakeCatalog:
    def prompts(self):
        return [
            {"id": "default_chat", "source_pack_id": "untrustedpack", "content_ref": "prompts/default_chat.system.md"},
            {"id": "default_chat", "source_pack_id": "trustedpack", "content_ref": "prompts/default_chat.system.md"},
        ]

    def prompt(self, prompt_id: str, source_pack_id: str | None = None):
        for prompt in self.prompts():
            if prompt["id"] != prompt_id:
                continue
            if source_pack_id and prompt["source_pack_id"] != source_pack_id:
                continue
            return prompt
        return None

    def prompt_text(self, prompt_id: str, source_pack_id: str | None = None):
        if prompt_id != "default_chat":
            return None
        if source_pack_id == "trustedpack":
            return "Trusted default prompt."
        if source_pack_id == "untrustedpack":
            return "Untrusted injected prompt."
        return None


def test_prompt_resolver_skips_untrusted_pack_prompt(monkeypatch, tmp_path: Path) -> None:
    untrusted_prompt = tmp_path / "untrustedpack" / "prompts" / "default_chat" / "prompt.md"
    untrusted_prompt.parent.mkdir(parents=True)
    untrusted_prompt.write_text("Untrusted injected prompt.", encoding="utf-8")

    resolver = PromptResolver.__new__(PromptResolver)
    resolver._registry = _FakeRegistry()
    resolver._extensions_root = tmp_path / "untrustedpack"
    resolver._capability_catalog = _FakeCatalog()
    monkeypatch.setattr(
        "domain.prompt.resolver.prompt_pack_is_trusted",
        lambda pack_id: str(pack_id) == "trustedpack",
    )

    content, source_pack_id = resolver.resolve_prompt("default_chat")

    assert content == "Trusted default prompt."
    assert source_pack_id == "trustedpack"


def test_prompt_resolver_returns_none_when_requested_pack_is_untrusted(monkeypatch, tmp_path: Path) -> None:
    resolver = PromptResolver.__new__(PromptResolver)
    resolver._registry = _FakeRegistry()
    resolver._extensions_root = tmp_path / "untrustedpack"
    resolver._capability_catalog = _FakeCatalog()
    monkeypatch.setattr("domain.prompt.resolver.prompt_pack_is_trusted", lambda pack_id: False)

    content, source_pack_id = resolver.resolve_prompt("default_chat", source_pack_id="untrustedpack")

    assert content is None
    assert source_pack_id is None
