from __future__ import annotations

from pathlib import Path

from backend_core.ecosystem import compat


class PromptLoader:
    """Legacy shim for prompt directory loading."""

    def __init__(self, prompt_dir: str | Path | None = None) -> None:
        resolved = Path(prompt_dir) if prompt_dir is not None else compat.get_prompts_dir()
        self.prompt_dir = resolved
        self.prompt_dir.mkdir(parents=True, exist_ok=True)
