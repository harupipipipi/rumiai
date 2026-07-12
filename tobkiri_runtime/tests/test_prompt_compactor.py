from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


def test_prompt_compactor_preserves_permission_safety_sections():
    from domain.prompt.prompt_compactor import compact_prompt

    prompt = "Rule A\n\nPermission boundary: keep this.\n\nRule A\n\nSafety: keep this too."
    result = compact_prompt(prompt)

    assert "Permission boundary" in result["suggested_prompt"]
    assert "Safety" in result["suggested_prompt"]
    assert result["compact_chars"] < result["original_chars"]
