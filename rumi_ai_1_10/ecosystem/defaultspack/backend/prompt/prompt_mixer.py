"""Prompt mixing helpers."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from .prompt_manager import PromptDefinition, PromptManager


class PromptMixer:
    def __init__(self, manager: Optional[PromptManager] = None) -> None:
        self.manager = manager
        self._mix_ai_provider: Optional[str] = None
        self._mix_ai_model: Optional[str] = None

    def set_mix_ai(self, provider: str, model: str) -> None:
        self._mix_ai_provider = provider
        self._mix_ai_model = model

    def mix(
        self,
        prompts: Sequence[str | PromptDefinition],
        variables: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> str:
        prompt_list = list(prompts)
        manager = self.manager or PromptManager()
        mixed = manager.mix(prompt_list, variables=variables, context=context)
        if isinstance(mixed, dict):
            return str(mixed.get("mixed", ""))
        return str(mixed)

    def preview(
        self,
        prompts: Sequence[str | PromptDefinition],
        variables: Optional[Dict[str, Any]] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        prompt_list = list(prompts)
        mixed = self.mix(prompt_list, variables=variables, context=context)
        prompt_ids: List[str] = []
        for prompt in prompt_list:
            if isinstance(prompt, PromptDefinition):
                prompt_ids.append(prompt.prompt_id)
            else:
                prompt_ids.append(prompt)
        return {
            "preview": mixed,
            "prompt_count": len(prompt_list),
            "prompt_ids": prompt_ids,
            "total_length": len(mixed),
            "mix_ai": (
                {"provider": self._mix_ai_provider, "model": self._mix_ai_model}
                if self._mix_ai_provider
                else None
            ),
        }
