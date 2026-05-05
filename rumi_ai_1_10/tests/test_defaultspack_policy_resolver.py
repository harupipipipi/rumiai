from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


def test_policy_resolver_precedence_and_deny_wins():
    from domain.agent.policy_resolver import PolicyResolver

    policy = PolicyResolver().resolve(
        {"tool_allowlist": ["todo", "coding_file_write"], "model_allowlist": ["stub/default", "openai/gpt-5.4"]},
        {"tool_denylist": ["coding_file_write"], "model_denylist": ["openai/gpt-5.4"]},
        {"allowed_tools": ["browser_use"]},
    )

    assert "coding_file_write" not in policy["tool_allowlist"]
    assert "coding_file_write" in policy["tool_denylist"]
    assert "openai/gpt-5.4" not in policy["model_allowlist"]
    assert PolicyResolver().tool_allowed("todo", policy) is True
    assert PolicyResolver().tool_allowed("coding_file_write", policy) is False
