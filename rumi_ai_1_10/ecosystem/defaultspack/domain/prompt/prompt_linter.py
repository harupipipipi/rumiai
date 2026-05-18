from __future__ import annotations

import re
from typing import Any


MUST_KEEP_RE = re.compile(r"(permission|approval|safety|security|secret|token|権限|承認|安全|秘密|credential)", re.IGNORECASE)


def lint_prompt(prompt: str, *, token_budget: int | None = None) -> dict[str, Any]:
    text = str(prompt or "")
    sections = _sections(text)
    duplicates = _duplicate_sections(sections)
    must_keep = [
        {"index": index, "preview": section[:160]}
        for index, section in enumerate(sections)
        if MUST_KEEP_RE.search(section)
    ]
    estimated_tokens = max(1, len(text) // 4) if text else 0
    warnings = []
    if token_budget and estimated_tokens > token_budget:
        warnings.append("prompt_exceeds_token_budget")
    if duplicates:
        warnings.append("duplicate_sections_detected")
    return {
        "original_chars": len(text),
        "estimated_tokens": estimated_tokens,
        "token_budget": token_budget,
        "duplicate_sections": duplicates,
        "must_keep_sections": must_keep,
        "warnings": warnings,
        "risk": "low" if not warnings or must_keep else "medium",
    }


def _sections(prompt: str) -> list[str]:
    chunks = [chunk.strip() for chunk in re.split(r"\n{2,}|^#{1,6}\s+", prompt, flags=re.MULTILINE) if chunk.strip()]
    if chunks:
        return chunks
    return [line.strip() for line in prompt.splitlines() if line.strip()]


def _duplicate_sections(sections: list[str]) -> list[dict[str, Any]]:
    seen: dict[str, int] = {}
    duplicates = []
    for index, section in enumerate(sections):
        key = _normalize(section)
        if not key:
            continue
        if key in seen:
            duplicates.append({"first_index": seen[key], "duplicate_index": index, "preview": section[:160]})
        else:
            seen[key] = index
    return duplicates


def _normalize(section: str) -> str:
    return " ".join(section.casefold().split())[:240]
