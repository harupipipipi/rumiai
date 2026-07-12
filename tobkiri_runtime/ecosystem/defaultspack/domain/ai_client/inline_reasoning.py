from __future__ import annotations

import re


_INLINE_REASONING_PATTERN = re.compile(
    r"<(?P<tag>think|thought)>(?P<body>.*?)</(?P=tag)>",
    flags=re.DOTALL | re.IGNORECASE,
)


def split_inline_reasoning(text: str) -> tuple[list[str], str]:
    thoughts: list[str] = []

    def collect(match: re.Match[str]) -> str:
        thought = str(match.group("body") or "").strip()
        if thought:
            thoughts.append(thought)
        return ""

    visible = _INLINE_REASONING_PATTERN.sub(collect, str(text or ""))
    return thoughts, visible.strip()
