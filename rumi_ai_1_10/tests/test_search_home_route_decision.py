from __future__ import annotations

import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
for candidate in (ROOT, DEFAULTSPACK_ROOT):
    value = str(candidate)
    if value not in sys.path:
        sys.path.insert(0, value)

from ecosystem.search_home_pack.domain.route_decision import (  # noqa: E402
    ASK_AI_WITH_SEARCH,
    GOOGLE_REDIRECT,
    RouteDecision,
)
from ecosystem.search_home_pack.domain.search_target_resolver import SearchTargetResolver  # noqa: E402


class FakeBridge:
    def __init__(self, *, search_results=None):
        self.search_results = [dict(item) for item in (search_results or [])]
        self.search_calls = []

    def web_search(self, query, *, limit=8, context=None, **kwargs):
        self.search_calls.append({"query": query, "limit": limit, "context": context})
        return [dict(item) for item in self.search_results]

    def judge_search_targets(self, user_query, candidates, *, context=None, **kwargs):
        return {"status": "error", "reason": "not configured"}


def _probe(candidate):
    url = str(candidate.get("url") or "")
    return {
        "final_url": url,
        "status": 200,
        "title": candidate.get("title") or url,
        "content_type": "text/html",
        "redirected": False,
        "looks_like_login": False,
        "looks_like_paywall": False,
        "looks_like_404": False,
        "looks_like_ad_heavy": False,
        "is_search_results": False,
    }


def test_route_decision_selected_candidate_and_dict_round_trip():
    decision = RouteDecision(
        route_type=GOOGLE_REDIRECT,
        query="openai docs",
        target_url="https://platform.openai.com/docs/overview",
        target_candidates=[
            {"url": "https://openai.com/", "title": "OpenAI"},
            {"url": "https://platform.openai.com/docs/overview", "title": "OpenAI Docs"},
        ],
        selected_index=1,
        fallback_url="https://www.google.com/search?q=openai+docs",
        resolution_reason="heuristic",
    )

    assert decision.selected_candidate()["title"] == "OpenAI Docs"
    assert decision.to_dict()["route_type"] == GOOGLE_REDIRECT
    assert decision.to_dict()["selected_index"] == 1


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("https://github.com", "https://github.com/"),
        ("github.com/harupipipipi/rumiai", "https://github.com/harupipipipi/rumiai"),
        ("localhost:3000", "http://localhost:3000/"),
    ],
)
def test_direct_url_inputs_resolve_without_search(raw: str, expected: str):
    bridge = FakeBridge()
    resolver = SearchTargetResolver(bridge=bridge, probe_fn=_probe)

    decision = resolver.resolve(raw)

    assert decision.route_type == GOOGLE_REDIRECT
    assert decision.target_url == expected
    assert decision.selected_index == 0
    assert bridge.search_calls == []


def test_question_like_input_routes_to_ai_with_search():
    resolver = SearchTargetResolver(bridge=FakeBridge(), probe_fn=_probe)

    decision = resolver.resolve("Go fmtって必要？")

    assert decision.route_type == ASK_AI_WITH_SEARCH
    assert decision.target_url == ""
    assert decision.metadata["selected_tools"] == ["web_search"]


def test_unsafe_direct_input_falls_back_to_safe_google_search():
    resolver = SearchTargetResolver(bridge=FakeBridge(), probe_fn=_probe)

    decision = resolver.resolve("javascript:alert(1)")

    assert decision.route_type == GOOGLE_REDIRECT
    assert decision.target_url == "https://www.google.com/search?q=javascript%3Aalert%281%29"
    assert decision.selected_index == -1


def test_safe_url_filtering_falls_back_when_no_candidate_survives():
    bridge = FakeBridge(
        search_results=[
            {"url": "file:///etc/passwd", "title": "bad", "summary": "bad"},
            {"url": "http://127.0.0.1:3000/private", "title": "local", "summary": "local"},
        ]
    )
    resolver = SearchTargetResolver(bridge=bridge, probe_fn=_probe)

    decision = resolver.resolve("private local secret")

    assert decision.target_url == "https://www.google.com/search?q=private+local+secret"
    assert decision.target_candidates == []
    assert decision.resolution_reason == "no_candidates_fallback"
