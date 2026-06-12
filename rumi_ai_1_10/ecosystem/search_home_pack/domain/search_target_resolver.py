from __future__ import annotations

import html
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Any, Callable

from .defaultspack_bridge import DefaultspackBridge
from .route_decision import ASK_AI_WITH_SEARCH, GOOGLE_REDIRECT, RouteDecision
from .safe_url import (
    build_google_fallback_url,
    classify_direct_url,
    query_explicitly_targets_localhost,
    unsafe_scheme_reason,
    validate_candidate_url,
)


ProbeFn = Callable[[dict[str, Any]], dict[str, Any]]
ScreenshotFn = Callable[[dict[str, Any]], dict[str, Any] | None]

_MAX_PROBE_BYTES = 196_608
_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)
_META_DESCRIPTION_RE = re.compile(
    r'<meta[^>]+(?:name|property)=["\'](?:description|og:description)["\'][^>]+content=["\'](.*?)["\']',
    re.IGNORECASE | re.DOTALL,
)
_CANONICAL_RE = re.compile(
    r'<link[^>]+rel=["\']canonical["\'][^>]+href=["\'](.*?)["\']',
    re.IGNORECASE | re.DOTALL,
)
_STRIP_RE = re.compile(r"<[^>]+>")
_SCRIPT_STYLE_RE = re.compile(r"<(script|style)\b[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)
_SPACE_RE = re.compile(r"\s+")
_SEARCH_PAGE_HOSTS = {
    "www.google.com",
    "google.com",
    "www.bing.com",
    "bing.com",
    "duckduckgo.com",
    "www.duckduckgo.com",
    "html.duckduckgo.com",
    "lite.duckduckgo.com",
    "search.yahoo.com",
}
_SITE_HINT_RE = re.compile(r"(公式|サイト|ホームページ|新聞|website|web\s*site|official\s+site|news\s+site)", re.IGNORECASE)
_ASCII_BRAND_RE = re.compile(r"(?<![a-z0-9-])([a-z][a-z0-9-]{2,31})(?![a-z0-9-])", re.IGNORECASE)
_SITE_GUESS_STOPWORDS = {
    "official",
    "site",
    "website",
    "web",
    "news",
    "newspaper",
    "homepage",
    "home",
}
_ANSWER_INTENT_RE = re.compile(
    r"(\?|？|教えて|おしえて|説明して|まとめて|要約して|調べて|とは|何|なに|どうして|なぜ|"
    r"今日のニュース|最新ニュース|ニュースを|today'?s?\s+news|latest\s+news|what\s+is|what's|why|how\s+to)",
    re.IGNORECASE,
)


class _ValidatingRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validation = validate_candidate_url(newurl)
        if not validation.ok:
            raise urllib.error.HTTPError(newurl, code, validation.reason, headers, fp)
        return super().redirect_request(req, fp, code, msg, headers, validation.normalized_url)


@dataclass(slots=True)
class ShortcutResolution:
    alias: str = ""
    tail: str = ""
    direct_url: str = ""
    direct_reason: str = ""
    synthetic_candidates: list[dict[str, Any]] = field(default_factory=list)
    forced_search_query: str = ""
    official_domains: set[str] = field(default_factory=set)
    immediate: bool = False


class SearchTargetResolver:
    def __init__(
        self,
        *,
        bridge: DefaultspackBridge | None = None,
        probe_fn: ProbeFn | None = None,
        screenshot_fn: ScreenshotFn | None = None,
        max_search_results: int = 8,
        max_probe_candidates: int = 5,
        max_visual_candidates: int = 0,
        ai_confidence_floor: float = 0.55,
    ) -> None:
        self._bridge = bridge or DefaultspackBridge()
        self._probe_fn = probe_fn or self._probe_candidate
        self._screenshot_fn = screenshot_fn
        self._max_search_results = max(1, min(int(max_search_results or 8), 10))
        self._max_probe_candidates = max(1, min(int(max_probe_candidates or 5), 5))
        self._max_visual_candidates = max(0, min(int(max_visual_candidates), 3))
        self._ai_confidence_floor = max(0.0, min(float(ai_confidence_floor or 0.55), 1.0))

    def resolve(self, query: str, *, context: dict[str, Any] | None = None) -> RouteDecision:
        cleaned = self._normalize_query(query)
        fallback_url = build_google_fallback_url(cleaned)
        if not cleaned:
            return RouteDecision(
                route_type=GOOGLE_REDIRECT,
                query="",
                target_url=fallback_url,
                fallback_url=fallback_url,
                resolution_reason="empty_query_fallback",
            )

        direct_url = self._direct_url_query(cleaned)
        if direct_url:
            public = [self._public_candidate({"url": direct_url, "final_url": direct_url, "title": direct_url, "domain": self._domain(direct_url), "source": "direct_url"})]
            return RouteDecision(
                route_type=GOOGLE_REDIRECT,
                query=cleaned,
                target_url=direct_url,
                target_candidates=public,
                selected_index=0,
                fallback_url=fallback_url,
                resolution_reason="direct_url_input",
            )

        shortcut = self._resolve_shortcut(cleaned)
        if shortcut.immediate and shortcut.direct_url:
            direct = self._safe_candidate(
                {
                    "url": shortcut.direct_url,
                    "title": shortcut.alias,
                    "snippet": shortcut.direct_reason,
                    "source": "shortcut",
                    "domain": self._domain(shortcut.direct_url),
                    "official": True,
                },
                user_query=cleaned,
            )
            public = [self._public_candidate(direct)] if direct else []
            return RouteDecision(
                route_type=GOOGLE_REDIRECT,
                query=cleaned,
                target_url=shortcut.direct_url,
                target_candidates=public,
                selected_index=0 if public else -1,
                fallback_url=fallback_url,
                resolution_reason=shortcut.direct_reason or f"shortcut:{shortcut.alias}",
            )

        if self._should_answer_with_ai(cleaned):
            return RouteDecision(
                route_type=ASK_AI_WITH_SEARCH,
                query=cleaned,
                target_url="",
                target_candidates=[],
                selected_index=-1,
                fallback_url=fallback_url,
                resolution_reason="answer_intent:defaultspack_chat_node",
                used_ai_judge=True,
                metadata={
                    "answer_required": True,
                    "defaultspack_node": "blocks.chat.send",
                    "selected_tools": ["web_search"],
                },
            )

        search_query = shortcut.forced_search_query or cleaned
        candidates = self._seed_candidates(cleaned, search_query, shortcut, context=context)
        if not candidates:
            return RouteDecision(
                route_type=GOOGLE_REDIRECT,
                query=cleaned,
                target_url=fallback_url,
                target_candidates=[],
                selected_index=-1,
                fallback_url=fallback_url,
                resolution_reason="no_candidates_fallback",
            )

        probed_candidates = self._probe_candidates(candidates, user_query=cleaned)
        self._attach_screenshots(probed_candidates, context=context)

        preferred_model = str((context or {}).get("preferred_model") or "").strip()
        judge = self._bridge.judge_search_targets(cleaned, probed_candidates, preferred_model=preferred_model, context=context)
        best_index: int | None = None
        resolution_reason = ""
        used_ai_judge = False
        used_visual_judge = False
        if judge.get("status") == "ok":
            judged_index = self._valid_index(judge.get("best_index"), len(probed_candidates))
            if judged_index is not None and float(judge.get("confidence") or 0.0) >= self._ai_confidence_floor:
                best_index = judged_index
                resolution_reason = str(judge.get("reason") or "").strip() or "ai_judge_selected"
                used_ai_judge = True
                used_visual_judge = bool(judge.get("used_visual_judge"))

        if best_index is None:
            best_index, resolution_reason = self._heuristic_select(probed_candidates, cleaned, shortcut)

        if best_index is None:
            return RouteDecision(
                route_type=GOOGLE_REDIRECT,
                query=cleaned,
                target_url=fallback_url,
                target_candidates=[],
                selected_index=-1,
                fallback_url=fallback_url,
                resolution_reason="no_viable_target_fallback",
                used_ai_judge=used_ai_judge,
                used_visual_judge=used_visual_judge,
            )

        target_url = str(probed_candidates[best_index].get("final_url") or probed_candidates[best_index].get("url") or fallback_url)
        public = [self._public_candidate(candidate) for candidate in probed_candidates]
        return RouteDecision(
            route_type=GOOGLE_REDIRECT,
            query=cleaned,
            target_url=target_url,
            target_candidates=public,
            selected_index=best_index,
            fallback_url=fallback_url,
            resolution_reason=resolution_reason,
            used_ai_judge=used_ai_judge,
            used_visual_judge=used_visual_judge,
            metadata={
                "shortcut": shortcut.alias or "",
                "explicit_localhost": query_explicitly_targets_localhost(cleaned),
                "candidate_count": len(public),
            },
        )

    @staticmethod
    def _normalize_query(query: str) -> str:
        text = str(query or "").strip()
        if text.casefold().startswith("!g "):
            return text[3:].strip()
        if text.casefold() == "!g":
            return ""
        return text

    def _seed_candidates(
        self,
        raw_query: str,
        search_query: str,
        shortcut: ShortcutResolution,
        *,
        context: dict[str, Any] | None,
    ) -> list[dict[str, Any]]:
        candidates: list[dict[str, Any]] = []
        for synthetic in shortcut.synthetic_candidates:
            safe = self._safe_candidate(synthetic, user_query=raw_query)
            if safe:
                candidates.append(safe)

        for guessed in self._site_guess_candidates(raw_query):
            safe = self._safe_candidate(guessed, user_query=raw_query)
            if safe:
                candidates.append(safe)

        search_results = self._bridge.web_search(search_query, limit=self._max_search_results, context=context)
        for index, item in enumerate(search_results):
            url = str(item.get("url") or "").strip()
            safe = self._safe_candidate(
                {
                    "url": url,
                    "title": item.get("title") or "",
                    "snippet": item.get("summary") or item.get("snippet") or "",
                    "source": "web_search",
                    "search_rank": index,
                    "official": self._domain(url) in shortcut.official_domains,
                },
                user_query=raw_query,
            )
            if safe:
                candidates.append(safe)
        return self._dedupe_candidates(candidates)

    def _safe_candidate(self, candidate: dict[str, Any], *, user_query: str) -> dict[str, Any] | None:
        validation = validate_candidate_url(str(candidate.get("url") or ""), user_query=user_query)
        if not validation.ok:
            return None
        prepared = dict(candidate)
        prepared["url"] = validation.normalized_url
        prepared.setdefault("final_url", validation.normalized_url)
        prepared["domain"] = self._domain(validation.normalized_url)
        if prepared.get("source") == "web_search" and self._is_general_search_page_url(validation.normalized_url):
            return None
        return prepared

    def _site_guess_candidates(self, query: str) -> list[dict[str, Any]]:
        if not _SITE_HINT_RE.search(query):
            return []
        brands = [
            match.group(1).casefold()
            for match in _ASCII_BRAND_RE.finditer(query)
            if match.group(1).casefold() not in _SITE_GUESS_STOPWORDS
        ]
        unique = []
        seen: set[str] = set()
        for brand in brands:
            if brand in seen:
                continue
            seen.add(brand)
            unique.append(brand)
        if len(unique) != 1:
            return []
        brand = unique[0]
        return [
            {
                "url": f"https://www.{brand}.com/",
                "title": f"{brand} official site",
                "snippet": "Site-like query candidate guessed from the brand token.",
                "source": "site_guess",
            }
        ]

    @staticmethod
    def _dedupe_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
        seen: set[str] = set()
        deduped: list[dict[str, Any]] = []
        for item in candidates:
            key = str(item.get("url") or "").strip()
            if not key or key in seen:
                continue
            seen.add(key)
            deduped.append(item)
        return deduped

    @staticmethod
    def _direct_url_query(query: str) -> str:
        direct = classify_direct_url(query)
        if not direct or direct.get("blocked"):
            return ""
        validation = validate_candidate_url(str(direct.get("url") or ""), user_query=query)
        return validation.normalized_url if validation.ok else ""

    def _resolve_shortcut(self, query: str) -> ShortcutResolution:
        lowered = query.casefold()
        alias_map = [
            ("youtube", {"aliases": ["youtube", "yt"], "home": "https://www.youtube.com/", "search": "https://www.youtube.com/results?search_query={query}", "immediate": True}),
            ("github", {"aliases": ["github", "gh"], "home": "https://github.com/", "search": "https://github.com/search?q={query}", "immediate": True}),
            ("x", {"aliases": ["twitter", "x"], "home": "https://x.com/", "search": "https://x.com/search?q={query}", "immediate": True}),
            ("reddit", {"aliases": ["reddit"], "home": "https://www.reddit.com/", "search": "https://www.reddit.com/search/?q={query}", "immediate": True}),
            ("wikipedia", {"aliases": ["wikipedia", "wiki"], "home": "https://en.wikipedia.org/wiki/Main_Page", "search": "https://en.wikipedia.org/w/index.php?search={query}", "immediate": True}),
            ("gmail", {"aliases": ["gmail"], "home": "https://mail.google.com/mail/u/0/#inbox", "search": "https://mail.google.com/mail/u/0/#search/{query}", "immediate": True}),
            ("amazon", {"aliases": ["amazon"], "home": "https://www.amazon.com/", "search": "https://www.amazon.com/s?k={query}", "immediate": True}),
            ("npm", {"aliases": ["npm"], "home": "https://www.npmjs.com/", "search": "https://www.npmjs.com/search?q={query}", "immediate": True}),
            ("pypi", {"aliases": ["pypi"], "home": "https://pypi.org/", "search": "https://pypi.org/search/?q={query}", "immediate": True}),
            ("rustdocs", {"aliases": ["rust docs", "rustdocs", "rustdoc"], "home": "https://doc.rust-lang.org/", "search": "https://doc.rust-lang.org/std/?search={query}", "immediate": True}),
            ("mdn", {"aliases": ["mdn"], "home": "https://developer.mozilla.org/", "search": "https://developer.mozilla.org/en-US/search?q={query}", "immediate": True}),
        ]
        for name, spec in alias_map:
            for alias in spec["aliases"]:
                alias_lower = alias.casefold()
                if lowered == alias_lower or lowered.startswith(alias_lower + " "):
                    tail = query[len(alias):].strip()
                    if tail:
                        direct_url = spec["search"].format(query=urllib.parse.quote_plus(tail))
                        reason = f"shortcut:{name}:search"
                    else:
                        direct_url = spec["home"]
                        reason = f"shortcut:{name}:home"
                    return ShortcutResolution(
                        alias=name,
                        tail=tail,
                        direct_url=direct_url,
                        direct_reason=reason,
                        immediate=bool(spec["immediate"]),
                        official_domains={self._domain(spec["home"])},
                    )
        if lowered.startswith("openai docs"):
            tail = query[len("openai docs"):].strip()
            home = "https://platform.openai.com/docs/overview"
            forced = "site:platform.openai.com/docs " + (tail or "OpenAI docs")
            return ShortcutResolution(
                alias="openai_docs",
                tail=tail,
                synthetic_candidates=[
                    {
                        "url": home,
                        "title": "OpenAI Docs",
                        "snippet": "Official OpenAI documentation.",
                        "source": "shortcut",
                        "official": True,
                    }
                ],
                forced_search_query=forced,
                official_domains={"platform.openai.com"},
            )
        if lowered.startswith("openai"):
            tail = query[len("openai"):].strip()
            forced = "site:openai.com OR site:platform.openai.com " + (tail or "OpenAI")
            return ShortcutResolution(
                alias="openai",
                tail=tail,
                synthetic_candidates=[
                    {
                        "url": "https://openai.com/",
                        "title": "OpenAI",
                        "snippet": "Official OpenAI site.",
                        "source": "shortcut",
                        "official": True,
                    },
                    {
                        "url": "https://platform.openai.com/docs/overview",
                        "title": "OpenAI Docs",
                        "snippet": "Official OpenAI docs.",
                        "source": "shortcut",
                        "official": True,
                    },
                ],
                forced_search_query=forced,
                official_domains={"openai.com", "platform.openai.com"},
            )
        pr_match = re.search(r"\bpr\s+#?(?P<number>\d+)\b", lowered)
        if pr_match:
            forced = f"site:github.com {query}"
            return ShortcutResolution(
                alias="github_pr",
                tail=pr_match.group("number"),
                forced_search_query=forced,
                official_domains={"github.com"},
            )
        if lowered.startswith("google docs"):
            tail = query[len("google docs"):].strip()
            home = "https://docs.google.com/document/u/0/"
            direct_url = "https://drive.google.com/drive/search?q=" + urllib.parse.quote_plus(tail + " type:document") if tail else home
            return ShortcutResolution(
                alias="google_docs",
                tail=tail,
                direct_url=direct_url,
                direct_reason="shortcut:google_docs",
                immediate=True,
                official_domains={"docs.google.com", "drive.google.com"},
            )
        if lowered.startswith("google drive"):
            tail = query[len("google drive"):].strip()
            home = "https://drive.google.com/drive/home"
            direct_url = "https://drive.google.com/drive/search?q=" + urllib.parse.quote_plus(tail) if tail else home
            return ShortcutResolution(
                alias="google_drive",
                tail=tail,
                direct_url=direct_url,
                direct_reason="shortcut:google_drive",
                immediate=True,
                official_domains={"drive.google.com"},
            )
        return ShortcutResolution(official_domains=self._official_domains_for_query(query))

    @staticmethod
    def _should_answer_with_ai(query: str) -> bool:
        text = str(query or "").strip()
        if not text:
            return False
        if unsafe_scheme_reason(text) is not None:
            return False
        if classify_direct_url(text):
            return False
        lowered = text.casefold()
        navigational_prefixes = (
            "youtube",
            "yt ",
            "github",
            "gh ",
            "x ",
            "twitter",
            "reddit",
            "wikipedia",
            "wiki",
            "gmail",
            "amazon",
            "npm",
            "pypi",
            "rust docs",
            "rustdoc",
            "rustdocs",
            "mdn",
            "google docs",
            "google drive",
            "openai",
        )
        if any(lowered == item.strip() or lowered.startswith(item) for item in navigational_prefixes):
            return False
        if _ANSWER_INTENT_RE.search(text):
            return True
        return False

    def _official_domains_for_query(self, query: str) -> set[str]:
        lowered = query.casefold()
        domains: set[str] = set()
        if "openai" in lowered:
            domains.update({"openai.com", "platform.openai.com"})
        if "github" in lowered or re.search(r"\bpr\s+#?\d+\b", lowered):
            domains.add("github.com")
        if "reddit" in lowered:
            domains.add("www.reddit.com")
        if "wikipedia" in lowered or "wiki" in lowered:
            domains.add("en.wikipedia.org")
        if "mdn" in lowered:
            domains.add("developer.mozilla.org")
        if "pypi" in lowered:
            domains.add("pypi.org")
        if "npm" in lowered:
            domains.add("www.npmjs.com")
        return domains

    def _probe_candidates(self, candidates: list[dict[str, Any]], *, user_query: str) -> list[dict[str, Any]]:
        results = [dict(item) for item in candidates]
        top = results[: self._max_probe_candidates]
        if not top:
            return results
        indexed_results: dict[int, dict[str, Any]] = {}
        with ThreadPoolExecutor(max_workers=min(len(top), self._max_probe_candidates)) as executor:
            future_map = {
                executor.submit(self._probe_fn, dict(candidate)): index
                for index, candidate in enumerate(top)
            }
            for future in as_completed(future_map):
                index = future_map[future]
                try:
                    probe = future.result()
                except Exception as exc:
                    probe = {"probe_error": str(exc)}
                indexed_results[index] = probe
        for index, candidate in enumerate(top):
            candidate.update(indexed_results.get(index, {}))
            final_validation = validate_candidate_url(str(candidate.get("final_url") or candidate.get("url") or ""), user_query=user_query)
            if final_validation.ok:
                candidate["final_url"] = final_validation.normalized_url
                candidate["domain"] = self._domain(candidate["final_url"])
            else:
                candidate["final_url"] = str(candidate.get("url") or "")
        return results

    def _attach_screenshots(self, candidates: list[dict[str, Any]], *, context: dict[str, Any] | None) -> None:
        if self._max_visual_candidates <= 0:
            return
        if not self._context_allows_visual_capture(context):
            return
        top = candidates[: self._max_visual_candidates]
        lock = threading.Lock()
        with ThreadPoolExecutor(max_workers=min(len(top), self._max_visual_candidates)) as executor:
            future_map = {
                executor.submit(self._capture_screenshot_safe, dict(candidate), context): candidate
                for candidate in top
            }
            for future in as_completed(future_map):
                candidate = future_map[future]
                capture = future.result()
                if not isinstance(capture, dict):
                    continue
                with lock:
                    if isinstance(capture.get("data_url"), str) and capture.get("data_url"):
                        candidate["screenshot_data_url"] = capture["data_url"]
                    if isinstance(capture.get("path"), str) and capture.get("path"):
                        candidate["screenshot_path"] = capture["path"]
                    if capture.get("screenshot_error"):
                        candidate["screenshot_error"] = capture.get("screenshot_error")

    def _capture_screenshot_safe(self, candidate: dict[str, Any], context: dict[str, Any] | None) -> dict[str, Any]:
        try:
            if self._screenshot_fn is not None:
                return self._screenshot_fn(dict(candidate)) or {}
            return self._capture_candidate_screenshot(dict(candidate), context=context) or {}
        except Exception as exc:
            return {"screenshot_error": str(exc)}

    @classmethod
    def _context_allows_visual_capture(cls, context: dict[str, Any] | None) -> bool:
        if not isinstance(context, dict):
            return False
        if context.get("_tool_server_approval_token_valid") is True:
            return True
        policies: list[dict[str, Any]] = []
        for key in ("profile_policy", "tool_policy"):
            value = context.get(key)
            if isinstance(value, dict):
                policies.append(value)
        runtime_profile = context.get("runtime_profile")
        if isinstance(runtime_profile, dict) and isinstance(runtime_profile.get("policy"), dict):
            policies.append(runtime_profile["policy"])
        return any(cls._truthy(policy.get("yolo_mode")) for policy in policies)

    @staticmethod
    def _truthy(value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return value != 0
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "y", "on", "allow", "allowed"}
        return False

    def _capture_candidate_screenshot(self, candidate: dict[str, Any], *, context: dict[str, Any] | None) -> dict[str, Any]:
        url = str(candidate.get("final_url") or candidate.get("url") or "").strip()
        if not url:
            return {"screenshot_error": "missing_candidate_url"}
        companion = self._capture_with_browser_companion(url, context=context)
        if isinstance(companion, dict) and companion.get("data_url"):
            companion.setdefault("provider", "browser_companion")
            return companion
        reason = str(companion.get("screenshot_error") or "") if isinstance(companion, dict) else ""
        return {"screenshot_error": reason or "no_screenshot_provider_available"}

    def _capture_with_browser_companion(self, url: str, *, context: dict[str, Any] | None) -> dict[str, Any]:
        try:
            from ecosystem.rumi_default_tools_pack.domain.tool.browser_companion import BrowserCompanionController
        except Exception as exc:
            return {"screenshot_error": f"browser_companion_import_failed:{exc}"}

        browser_context = dict(context or {})
        controller = BrowserCompanionController()
        tabs_result = controller.run("browser.tabs", {}, context=browser_context)
        tabs = tabs_result.get("tabs") if isinstance(tabs_result, dict) else None
        if not isinstance(tabs, list):
            return {"screenshot_error": str(tabs_result.get("reason") or "browser_companion_tabs_unavailable") if isinstance(tabs_result, dict) else "browser_companion_tabs_unavailable"}

        matched_tab = None
        for tab in tabs:
            if not isinstance(tab, dict):
                continue
            tab_url = str(tab.get("url") or "")
            if tab_url == url or url.startswith(tab_url) or tab_url.startswith(url):
                matched_tab = tab
                break
        if matched_tab is None:
            return {"screenshot_error": "browser_companion_no_matching_tab"}

        snapshot = controller.run(
            "page.snapshot",
            {"tab_id": matched_tab.get("id"), "include_capture": True},
            context=browser_context,
        )
        if isinstance(snapshot, dict) and snapshot.get("requires_approval"):
            return {"screenshot_error": "browser_companion_capture_requires_approval"}
        if not isinstance(snapshot, dict) or snapshot.get("is_error"):
            return {"screenshot_error": str(snapshot.get("reason") or "browser_companion_capture_failed") if isinstance(snapshot, dict) else "browser_companion_capture_failed"}
        result = {
            "data_url": snapshot.get("data_url"),
            "path": snapshot.get("path"),
            "provider": "browser_companion",
        }
        if snapshot.get("path"):
            result["path"] = snapshot.get("path")
        return result

    def _heuristic_select(
        self,
        candidates: list[dict[str, Any]],
        query: str,
        shortcut: ShortcutResolution,
    ) -> tuple[int | None, str]:
        if not candidates:
            return None, "heuristic_no_candidates"
        scores: list[tuple[float, int, str]] = []
        official_domains = set(shortcut.official_domains) | self._official_domains_for_query(query)
        for index, candidate in enumerate(candidates):
            score, reason = self._heuristic_score(candidate, query, official_domains=official_domains)
            candidate["heuristic_score"] = score
            scores.append((score, index, reason))
        scores.sort(key=lambda item: (-item[0], item[1]))
        if not scores:
            return None, "heuristic_no_scores"
        score, best_index, reason = scores[0]
        return best_index, f"heuristic:{score:.1f}:{reason}"

    def _heuristic_score(self, candidate: dict[str, Any], query: str, *, official_domains: set[str]) -> tuple[float, str]:
        score = 0.0
        reasons: list[str] = []
        title = str(candidate.get("title") or "").casefold()
        domain = str(candidate.get("domain") or "").casefold()
        url = str(candidate.get("final_url") or candidate.get("url") or "").casefold()
        extracted = str(candidate.get("extracted_text") or "").casefold()
        tokens = [item for item in re.split(r"\s+", query.casefold()) if item]

        if domain in {item.casefold() for item in official_domains}:
            score += 35
            reasons.append("official_domain")
        if bool(candidate.get("official")):
            score += 20
            reasons.append("shortcut_official")
        if str(candidate.get("source") or "") == "site_guess":
            score += 18
            reasons.append("site_guess")
        title_hits = sum(1 for token in tokens if token in title)
        if title_hits:
            score += 8 * title_hits
            reasons.append("title_match")
        content_hits = sum(1 for token in tokens if token in extracted or token in url)
        if content_hits:
            score += min(content_hits * 3, 15)
            reasons.append("content_match")
        if candidate.get("canonical_url"):
            score += 6
            reasons.append("canonical")
        if "2026" in title or "2025" in title:
            score += 2
        if bool(candidate.get("redirected")) and not bool(candidate.get("is_search_results")):
            score += 2
        if bool(candidate.get("is_search_results")):
            score -= 40
            reasons.append("search_results_penalty")
        if bool(candidate.get("looks_like_login")):
            score -= 20
            reasons.append("login_penalty")
        if bool(candidate.get("looks_like_paywall")):
            score -= 18
            reasons.append("paywall_penalty")
        if bool(candidate.get("looks_like_404")):
            score -= 30
            reasons.append("not_found_penalty")
        if bool(candidate.get("looks_like_ad_heavy")):
            score -= 15
            reasons.append("ad_penalty")
        if any(shortener in domain for shortener in ("t.co", "bit.ly", "tinyurl", "goo.gl")):
            score -= 20
            reasons.append("shortener_penalty")
        return score, ",".join(reasons) or "generic"

    def _public_candidate(self, candidate: dict[str, Any]) -> dict[str, Any]:
        return {
            "url": candidate.get("url") or "",
            "final_url": candidate.get("final_url") or candidate.get("url") or "",
            "title": candidate.get("title") or "",
            "snippet": candidate.get("snippet") or "",
            "domain": candidate.get("domain") or "",
            "source": candidate.get("source") or "web_search",
            "status": candidate.get("status"),
            "canonical_url": candidate.get("canonical_url") or "",
            "content_type": candidate.get("content_type") or "",
            "redirected": bool(candidate.get("redirected")),
            "looks_like_login": bool(candidate.get("looks_like_login")),
            "looks_like_paywall": bool(candidate.get("looks_like_paywall")),
            "looks_like_404": bool(candidate.get("looks_like_404")),
            "looks_like_ad_heavy": bool(candidate.get("looks_like_ad_heavy")),
            "is_search_results": bool(candidate.get("is_search_results")),
            "heuristic_score": candidate.get("heuristic_score"),
            "screenshot_path": candidate.get("screenshot_path") or "",
        }

    @staticmethod
    def _domain(url: str) -> str:
        return urllib.parse.urlparse(str(url or "")).hostname or ""

    @staticmethod
    def _valid_index(value: Any, limit: int) -> int | None:
        try:
            index = int(value)
        except (TypeError, ValueError):
            return None
        if 0 <= index < limit:
            return index
        return None

    def _probe_candidate(self, candidate: dict[str, Any]) -> dict[str, Any]:
        url = str(candidate.get("url") or "")
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": "RumiSearchHome/1.0 (+intent resolver)",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            },
        )
        opener = urllib.request.build_opener(_ValidatingRedirectHandler)
        started = time.time()
        try:
            with opener.open(request, timeout=6.0) as response:
                status = getattr(response, "status", 200)
                final_url = response.geturl()
                content_type = response.headers.get("Content-Type", "")
                raw_body = response.read(_MAX_PROBE_BYTES)
                redirected = final_url != url
        except urllib.error.HTTPError as exc:
            status = int(getattr(exc, "code", 0) or 0)
            final_url = exc.geturl() or url
            content_type = exc.headers.get("Content-Type", "") if exc.headers else ""
            try:
                raw_body = exc.read(_MAX_PROBE_BYTES)
            except Exception:
                raw_body = b""
            redirected = final_url != url
        except Exception as exc:
            return {
                "final_url": url,
                "status": 0,
                "content_type": "",
                "probe_error": str(exc),
                "probe_ms": int((time.time() - started) * 1000),
            }

        text_body = self._decode_body(raw_body, content_type)
        parsed = self._parse_body(text_body, base_url=final_url)
        return {
            "final_url": final_url,
            "status": status,
            "title": parsed.get("title") or candidate.get("title") or "",
            "meta_description": parsed.get("meta_description") or "",
            "canonical_url": parsed.get("canonical_url") or "",
            "extracted_text": parsed.get("extracted_text") or "",
            "content_type": content_type.split(";", 1)[0].strip().lower(),
            "redirected": redirected,
            "looks_like_login": self._looks_like_login(final_url, parsed),
            "looks_like_paywall": self._looks_like_paywall(parsed),
            "looks_like_404": self._looks_like_404(status, parsed),
            "looks_like_ad_heavy": self._looks_like_ad_heavy(parsed),
            "is_search_results": self._looks_like_search_results(final_url, parsed),
            "probe_ms": int((time.time() - started) * 1000),
        }

    @staticmethod
    def _decode_body(raw_body: bytes, content_type: str) -> str:
        charset = "utf-8"
        match = re.search(r"charset=([^\s;]+)", content_type, re.IGNORECASE)
        if match:
            charset = match.group(1).strip("\"'")
        try:
            return raw_body.decode(charset, errors="replace")
        except LookupError:
            return raw_body.decode("utf-8", errors="replace")

    def _parse_body(self, body: str, *, base_url: str) -> dict[str, str]:
        title = self._extract_first(_TITLE_RE, body)
        meta_description = self._extract_first(_META_DESCRIPTION_RE, body)
        canonical = self._extract_first(_CANONICAL_RE, body)
        if canonical:
            canonical = urllib.parse.urljoin(base_url, canonical)
        cleaned = _SCRIPT_STYLE_RE.sub(" ", body)
        cleaned = _STRIP_RE.sub(" ", cleaned)
        cleaned = html.unescape(cleaned)
        cleaned = _SPACE_RE.sub(" ", cleaned).strip()
        return {
            "title": title,
            "meta_description": meta_description,
            "canonical_url": canonical,
            "extracted_text": cleaned[:6000],
        }

    @staticmethod
    def _extract_first(pattern: re.Pattern[str], body: str) -> str:
        match = pattern.search(body)
        if not match:
            return ""
        value = html.unescape(_SPACE_RE.sub(" ", match.group(1))).strip()
        return value[:300]

    @staticmethod
    def _looks_like_login(url: str, parsed: dict[str, str]) -> bool:
        text = " ".join([url, parsed.get("title", ""), parsed.get("meta_description", ""), parsed.get("extracted_text", "")[:500]]).casefold()
        return any(token in text for token in ("sign in", "log in", "login", "ログイン", "auth"))

    @staticmethod
    def _looks_like_paywall(parsed: dict[str, str]) -> bool:
        text = " ".join([parsed.get("title", ""), parsed.get("meta_description", ""), parsed.get("extracted_text", "")[:700]]).casefold()
        return any(token in text for token in ("subscribe to continue", "subscriber-only", "subscription required", "paywall"))

    @staticmethod
    def _looks_like_404(status: int, parsed: dict[str, str]) -> bool:
        if status == 404:
            return True
        text = " ".join([parsed.get("title", ""), parsed.get("meta_description", ""), parsed.get("extracted_text", "")[:400]]).casefold()
        return "not found" in text or "404" in text

    @staticmethod
    def _looks_like_ad_heavy(parsed: dict[str, str]) -> bool:
        text = parsed.get("extracted_text", "")[:1500].casefold()
        return sum(text.count(token) for token in ("advertisement", "sponsored", "buy now")) >= 3

    def _looks_like_search_results(self, url: str, parsed: dict[str, str]) -> bool:
        if self._is_general_search_page_url(url):
            return True
        parsed_url = urllib.parse.urlparse(url)
        host = parsed_url.hostname or ""
        if host in _SEARCH_PAGE_HOSTS:
            return True
        title = parsed.get("title", "").casefold()
        path = parsed_url.path.casefold()
        return ("search" in path or "results" in path) and ("search" in title or "results" in title)

    @staticmethod
    def _is_general_search_page_url(url: str) -> bool:
        parsed_url = urllib.parse.urlparse(url)
        host = (parsed_url.hostname or "").casefold()
        path = parsed_url.path.casefold()
        query = urllib.parse.parse_qs(parsed_url.query)
        if host in _SEARCH_PAGE_HOSTS:
            return True
        normalized_host = host[4:] if host.startswith("www.") else host
        if normalized_host.startswith("google.") and (path in {"", "/", "/search", "/webhp"} or "q" in query):
            return True
        if normalized_host in {"duckduckgo.com"} or normalized_host.endswith(".duckduckgo.com"):
            return True
        if normalized_host in {"bing.com"} and (path.startswith("/search") or "q" in query):
            return True
        if normalized_host == "yahoo.com" or normalized_host.endswith(".yahoo.com"):
            return path.startswith("/search") or "p" in query
        return False
