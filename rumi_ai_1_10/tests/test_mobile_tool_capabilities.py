from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK))


def test_mobile_tool_records_tag_compatible_tools() -> None:
    from domain.mobile.tools import MOBILE_COMPATIBLE_TAG, mobile_tool_records

    records = mobile_tool_records(
        [
            {
                "tool_id": "web_search",
                "name": "web_search",
                "summary": "Search the web",
                "tags": ["web"],
            }
        ]
    )

    assert records[0]["mobile_compatible"] is True
    assert MOBILE_COMPATIBLE_TAG in records[0]["tags"]
    assert records[0]["mobile"]["execution_location"] == "pc"
    assert records[0]["mobile"]["platforms"] == ["ios", "android"]
    assert "pc-defaultspack-runtime" in records[0]["mobile"]["runtime_layers"]
    assert records[0]["callable"] is True
    assert records[0]["execution_route"] == "pc"
    assert records[0]["automatic_routing"]["one_tool_surface"] is True


def test_mobile_tool_records_explain_host_bound_tools() -> None:
    from domain.mobile.tools import MOBILE_COMPATIBLE_TAG, mobile_tool_records

    records = mobile_tool_records(
        [
            {
                "tool_id": "desktop_input",
                "name": "desktop_input",
                "summary": "Control desktop input",
                "tags": ["desktop", "computer_use"],
            }
        ]
    )

    assert records[0]["mobile_compatible"] is False
    assert MOBILE_COMPATIBLE_TAG not in records[0]["tags"]
    assert "スマホ単体では" in records[0]["mobile_unavailable_reason"]
    assert records[0]["mobile"]["implementation_status"] == "pc_only"
    assert records[0]["mobile"]["platforms"] == []
    assert records[0]["callable"] is False
    assert records[0]["execution_route"] == "unavailable"


def test_mobile_tool_summary_includes_defaultspack_agent_template() -> None:
    from domain.mobile.tools import mobile_tool_records, mobile_tool_summary

    records = mobile_tool_records([{"tool_id": "web_search", "name": "web_search"}])
    summary = mobile_tool_summary(records)

    assert summary["compatible_count"] == 1
    assert summary["agent_template"]["template_id"] == "rumi.composer.default"
    assert summary["agent_template"]["ai_input_id"] == "rumi.composer.default:default_ai_input"
    assert summary["platform_tags"]["ios"] == "mobile-ios"
    assert summary["tool_surface"]["mode"] == "unified"
    assert summary["tool_surface"]["one_tool_surface"] is True
