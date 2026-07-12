from __future__ import annotations

from typing import Any

from domain.prompt.prompt_linter import MUST_KEEP_RE, lint_prompt


def compact_prompt(prompt: str, *, target_chars: int | None = None) -> dict[str, Any]:
    text = str(prompt or "")
    target = int(target_chars or max(1000, int(len(text) * 0.7))) if text else 0
    sections = [section.strip() for section in text.split("\n\n") if section.strip()]
    seen: set[str] = set()
    compact_sections = []
    duplicate_sections = []
    for index, section in enumerate(sections):
        key = " ".join(section.casefold().split())[:240]
        if key in seen and not MUST_KEEP_RE.search(section):
            duplicate_sections.append({"index": index, "preview": section[:160]})
            continue
        seen.add(key)
        compact_sections.append(section)
    suggested = "\n\n".join(compact_sections)
    if len(suggested) > target:
        suggested = _soft_trim(suggested, target)
    diagnostics = lint_prompt(text)
    return {
        "original_chars": len(text),
        "compact_chars": len(suggested),
        "duplicate_sections": duplicate_sections or diagnostics.get("duplicate_sections", []),
        "must_keep_sections": diagnostics.get("must_keep_sections", []),
        "suggested_prompt": suggested,
        "risk": "low",
    }


def _soft_trim(text: str, target: int) -> str:
    if len(text) <= target:
        return text
    paragraphs = [paragraph for paragraph in text.split("\n\n") if paragraph.strip()]
    kept = []
    total = 0
    for paragraph in paragraphs:
        if MUST_KEEP_RE.search(paragraph):
            kept.append(paragraph)
            total += len(paragraph)
            continue
        if total + len(paragraph) + 2 <= target:
            kept.append(paragraph)
            total += len(paragraph) + 2
    return "\n\n".join(kept) or text[:target]
