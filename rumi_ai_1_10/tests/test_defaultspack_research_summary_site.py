from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


def test_research_summary_site_writes_sanitized_local_html(tmp_path: Path) -> None:
    from blocks.research.summary_site import run

    result = run(
        {
            "title": "MiMo V2.5 Pro deep research",
            "query": "tool harness debugging",
            "summary": "A durable summary for a large coding run.",
            "output_path": "research/mimo-summary.html",
            "sections": [
                {
                    "title": "Harness finding",
                    "body": "Terminal approvals and local artifacts should stay visible.",
                    "bullets": ["Keep source cards close to findings."],
                    "sources": [1],
                }
            ],
            "sources": [
                {
                    "title": "<script>alert(1)</script> Official notes",
                    "url": "javascript:alert(1)",
                    "summary": "Use structured artifacts instead of a flat transcript.",
                    "provider": "local",
                    "trust_level": "high",
                }
            ],
        },
        {"artifact_root": str(tmp_path)},
    )

    assert result["status"] == "ok"
    data = result["data"]
    assert data["path"] == "research/mimo-summary.html"
    assert data["artifact"]["mime_type"] == "text/html"
    assert data["source_count"] == 1
    assert data["section_count"] == 1

    html = (tmp_path / "research" / "mimo-summary.html").read_text(encoding="utf-8")
    assert "<script" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt; Official notes" in html
    assert 'href="javascript:alert(1)"' not in html
    assert '<a class="badge" href="#source-1">Source 1</a>' in html
    assert "MiMo V2.5 Pro deep research" in html


def test_research_summary_site_rejects_bad_inputs_and_path_escape(tmp_path: Path) -> None:
    from blocks.research.summary_site import run

    bad_sources = run({"summary": "x", "sources": "not a list"}, {"artifact_root": str(tmp_path)})
    assert bad_sources["status"] == "error"
    assert bad_sources["error"]["code"] == "INVALID_INPUT"

    escaping_path = run({"summary": "x", "output_path": "../escape.html"}, {"artifact_root": str(tmp_path)})
    assert escaping_path["status"] == "error"
    assert escaping_path["error"]["code"] == "INVALID_INPUT"


def test_research_summary_site_function_dispatch_and_tool_handler(tmp_path: Path) -> None:
    from domain.function_runtime.dispatcher import run_defaultspack_function
    from domain.tool.research_tools import research_summary_site

    payload = {
        "title": "Local research matome",
        "summary": "Findings can be browsed after a deep research run.",
        "output_path": "research/function-summary.html",
    }
    function_result = run_defaultspack_function(
        "research_summary_site",
        payload,
        {"artifact_root": str(tmp_path)},
    )
    assert function_result["status"] == "ok"
    assert function_result["data"]["path"] == "research/function-summary.html"

    tool_result = research_summary_site(
        {**payload, "output_path": "research/tool-summary.html"},
        {"artifact_root": str(tmp_path)},
    )
    assert tool_result["is_error"] is False
    assert tool_result["widget"]["data"]["path"] == "research/tool-summary.html"
    assert (tmp_path / "research" / "tool-summary.html").is_file()
