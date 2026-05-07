from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))

from domain.runtime_config import get_runtime_config, merged_tool_policy  # noqa: E402


def test_default_runtime_config_loads_from_config_dir(monkeypatch):
    monkeypatch.delenv("RUMI_DEFAULTSPACK_RUNTIME_CONFIG_PATH", raising=False)

    config = get_runtime_config()

    assert config["tool_policy"]["allow_shell"] is False
    assert config["scheduler"]["allow_no_agent_scripts"] is False


def test_user_runtime_config_overrides_default(tmp_path, monkeypatch):
    config_path = tmp_path / "runtime_config.json"
    config_path.write_text(
        json.dumps({"tool_policy": {"allow_shell": True}, "scheduler": {"enabled": False}}),
        encoding="utf-8",
    )
    monkeypatch.setenv("RUMI_DEFAULTSPACK_RUNTIME_CONFIG_PATH", str(config_path))

    config = get_runtime_config()
    policy = merged_tool_policy({"profile_policy": {"allow_file_write": False}})

    assert config["tool_policy"]["allow_shell"] is True
    assert config["scheduler"]["enabled"] is False
    assert policy["allow_shell"] is True
    assert policy["allow_file_write"] is False
