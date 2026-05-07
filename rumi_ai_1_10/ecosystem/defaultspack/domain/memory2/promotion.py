from __future__ import annotations


def should_promote(content: str, confidence: float = 1.0) -> bool:
    return bool(str(content).strip()) and confidence >= 0.5
