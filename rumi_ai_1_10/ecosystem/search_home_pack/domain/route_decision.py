from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal
from urllib.parse import quote_plus

from .safe_url import classify_direct_url, unsafe_scheme_reason


RouteKind = Literal[
    "URL_NAVIGATE",
    "GOOGLE_REDIRECT",
    "ASK_AI",
    "ASK_AI_WITH_SEARCH",
    "BLOCKED",
]

_CURRENT_INFO_HINTS = (
    "latest",
    "recent",
    "today",
    "current",
    "now",
    "news",
    "price",
    "stock",
    "weather",
    "schedule",
    "release",
    "version",
    "merge",
    "issue",
    "pull request",
    "最新",
    "最近",
    "今日",
    "現在",
    "今",
    "ニュース",
    "株価",
    "株",
    "価格",
    "値段",
    "天気",
    "日程",
    "おすすめ",
    "比較",
    "評価額",
    "法律",
)
_QUESTION_HINTS = (
    "?",
    "？",
    "what",
    "why",
    "how",
    "help",
    "compare",
    "should",
    "need",
    "error",
    "原因",
    "なぜ",
    "どう",
    "どうやって",
    "必要",
    "教えて",
    "とは",
    "設計",
    "作り方",
    "比較",
    "おすすめ",
)
_WEB_RESULTS_HINTS = (
    "site:",
    "画像検索",
    "image search",
    "公式サイト",
    "official site",
    "公式ページ",
    "docs ",
    "documentation",
)
_WEB_RESULTS_PREFIXES = ("github ", "gitlab ", "stackoverflow ", "wikipedia ", "youtube ")
_EXPLICIT_PREFIXES: tuple[tuple[str, RouteKind], ...] = (
    ("!g", "GOOGLE_REDIRECT"),
    ("g:", "GOOGLE_REDIRECT"),
    ("google:", "GOOGLE_REDIRECT"),
    ("!ai", "ASK_AI"),
    ("ai:", "ASK_AI"),
    ("ask:", "ASK_AI"),
    ("!url", "URL_NAVIGATE"),
    ("url:", "URL_NAVIGATE"),
)


@dataclass(slots=True)
class RouteDecision:
    route: RouteKind
    confidence: float
    normalized_query: str
    target_url: str | None = None
    reason: str = ""
    source: str = "rules"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def google_search_url(query: str) -> str:
    return f"https://www.google.com/search?q={quote_plus(str(query or '').strip())}"


def decide_route(raw: str, *, bridge: Any | None = None) -> RouteDecision:
    text = str(raw or "").strip()
    if not text:
        return RouteDecision(
            route="BLOCKED",
            confidence=1.0,
            normalized_query="",
            reason="input is empty",
        )

    blocked_reason = unsafe_scheme_reason(text)
    if blocked_reason:
        return RouteDecision(
            route="BLOCKED",
            confidence=1.0,
            normalized_query=text,
            reason=blocked_reason,
        )

    explicit = _match_explicit_prefix(text)
    if explicit is not None:
        return _explicit_decision(explicit["route"], explicit["query"])

    direct_url = classify_direct_url(text)
    if direct_url:
        if direct_url.get("blocked"):
            return RouteDecision(
                route="BLOCKED",
                confidence=1.0,
                normalized_query=text,
                reason=str(direct_url.get("reason") or "unsafe URL scheme is blocked"),
            )
        return RouteDecision(
            route="URL_NAVIGATE",
            confidence=0.99,
            normalized_query=text,
            target_url=str(direct_url["url"]),
            reason=str(direct_url.get("reason") or "recognized direct URL"),
        )

    if _looks_like_web_results_query(text) and not _looks_like_question(text):
        return RouteDecision(
            route="GOOGLE_REDIRECT",
            confidence=0.87,
            normalized_query=text,
            target_url=google_search_url(text),
            reason="query looks like a web results request",
        )

    if _needs_freshness(text):
        return RouteDecision(
            route="ASK_AI_WITH_SEARCH",
            confidence=0.92,
            normalized_query=text,
            reason="query likely needs fresh or external information",
        )

    if _looks_like_question(text):
        return RouteDecision(
            route="ASK_AI",
            confidence=0.88,
            normalized_query=text,
            reason="query looks like a question or reasoning request",
        )

    if bridge is not None:
        try:
            decision = bridge.classify_with_ai(text)
            return _finalize_ai_decision(decision, original_query=text)
        except Exception:
            pass

    return RouteDecision(
        route="ASK_AI_WITH_SEARCH",
        confidence=0.55,
        normalized_query=text,
        reason="ambiguous input defaults to AI with search",
    )


def _match_explicit_prefix(text: str) -> dict[str, Any] | None:
    lowered = text.casefold()
    for prefix, route in _EXPLICIT_PREFIXES:
        if lowered.startswith(prefix):
            query = text[len(prefix) :].strip()
            return {"route": route, "query": query}
    return None


def _explicit_decision(route: RouteKind, query: str) -> RouteDecision:
    if not query:
        return RouteDecision(
            route="BLOCKED",
            confidence=1.0,
            normalized_query="",
            reason="explicit prefix requires a non-empty query",
        )
    if route == "GOOGLE_REDIRECT":
        return RouteDecision(
            route=route,
            confidence=1.0,
            normalized_query=query,
            target_url=google_search_url(query),
            reason="explicit Google prefix",
        )
    if route == "ASK_AI":
        return RouteDecision(
            route=route,
            confidence=1.0,
            normalized_query=query,
            reason="explicit AI prefix",
        )
    direct_url = classify_direct_url(query)
    if direct_url and not direct_url.get("blocked"):
        return RouteDecision(
            route="URL_NAVIGATE",
            confidence=1.0,
            normalized_query=query,
            target_url=str(direct_url["url"]),
            reason="explicit URL prefix",
        )
    return RouteDecision(
        route="BLOCKED",
        confidence=1.0,
        normalized_query=query,
        reason="explicit URL prefix requires a direct URL or domain",
    )


def _finalize_ai_decision(decision: Any, *, original_query: str) -> RouteDecision:
    if isinstance(decision, RouteDecision):
        normalized = decision.normalized_query or original_query
        if decision.route == "GOOGLE_REDIRECT" and not decision.target_url:
            return RouteDecision(
                route=decision.route,
                confidence=decision.confidence,
                normalized_query=normalized,
                target_url=google_search_url(normalized),
                reason=decision.reason or "AI classifier requested Google results",
                source=decision.source or "ai",
            )
        if decision.route == "URL_NAVIGATE" and not decision.target_url:
            direct_url = classify_direct_url(normalized)
            if direct_url and not direct_url.get("blocked"):
                return RouteDecision(
                    route=decision.route,
                    confidence=decision.confidence,
                    normalized_query=normalized,
                    target_url=str(direct_url["url"]),
                    reason=decision.reason or "AI classifier recognized a direct URL",
                    source=decision.source or "ai",
                )
        return RouteDecision(
            route=decision.route,
            confidence=decision.confidence,
            normalized_query=normalized,
            target_url=decision.target_url,
            reason=decision.reason or "AI classifier decision",
            source=decision.source or "ai",
        )
    return RouteDecision(
        route="ASK_AI_WITH_SEARCH",
        confidence=0.55,
        normalized_query=original_query,
        reason="AI classifier returned an invalid result",
    )


def _needs_freshness(text: str) -> bool:
    lowered = text.casefold()
    if any(token in lowered for token in _CURRENT_INFO_HINTS):
        return True
    return "pr" in lowered and any(char.isdigit() for char in lowered)


def _looks_like_question(text: str) -> bool:
    lowered = text.casefold()
    return any(token in lowered for token in _QUESTION_HINTS)


def _looks_like_web_results_query(text: str) -> bool:
    lowered = text.casefold()
    if any(token in lowered for token in _WEB_RESULTS_HINTS):
        return True
    return any(lowered.startswith(prefix) for prefix in _WEB_RESULTS_PREFIXES)
