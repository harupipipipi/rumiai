from __future__ import annotations

import sys
from pathlib import Path

import yaml

DEFAULTSPACK_ROOT = Path(__file__).resolve().parents[1] / "ecosystem" / "defaultspack"
if str(DEFAULTSPACK_ROOT) not in sys.path:
    sys.path.insert(0, str(DEFAULTSPACK_ROOT))

from blocks.permissions.filter_tools import run  # noqa: E402


def test_profile_permissions_cannot_disable_required_approval(tmp_path: Path):
    permissions_dir = tmp_path / "permissions"
    permissions_dir.mkdir()
    (permissions_dir / "tool_policy.yaml").write_text(
        yaml.safe_dump(
            {
                "version": 1,
                "profile_id": "p1",
                "network_default": "allow",
                "write_actions_require_approval": False,
                "high_risk_tools_require_approval": False,
                "allow_client_supplied_approved": True,
            }
        ),
        encoding="utf-8",
    )

    result = run(
        {
            "profile_id": "p1",
            "workspace": {"permissions_dir": str(permissions_dir)},
            "tools": [{"name": "coding_file_write", "approved": True}],
        },
        {},
    )

    tool = result["data"]["tools"][0]
    assert tool["requires_approval"] is True
    assert "approved" not in tool
    assert result["data"]["policy"]["write_actions_require_approval"] is True
    assert result["data"]["policy"]["allow_client_supplied_approved"] is False
