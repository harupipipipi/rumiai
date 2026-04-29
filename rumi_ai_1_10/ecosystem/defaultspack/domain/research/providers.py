from __future__ import annotations

import json
import re
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable


FetchFn = Callable[[str, float], str]


def _default_fetch(url: str, timeout: float) -> str:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "RumiDefaultspack/1.0 (+local-first research)",
            "Accept": "application/json,text/html;q=0.9,*/*;q=0.8",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")


def _strip_html(value: str, limit: int = 500) -> str:
    value = re.sub(r"<script\b[^>]*>.*?</script>", " ", value, flags=re.I | re.S)
    value = re.sub(r"<style\b[^>]*>.*?</style>", " ", value, flags=re.I | re.S)
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value[:limit]


def _html_title(value: str) -> str:
    match = re.search(r"<title[^>]*>(.*?)</title>", value, flags=re.I | re.S)
    if not match:
        return ""
    return _strip_html(match.group(1), limit=160)


@dataclass
class ProviderResult:
    query: str
    provider: str
    sources: list[dict[str, Any]]
    summary: str
    network_enabled: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "query": self.query,
            "provider": self.provider,
            "sources": self.sources,
            "summary": self.summary,
            "network_enabled": self.network_enabled,
        }


class ExternalWebProvider:
    """Small network-search provider with a fetchable URL fallback.

    The provider is intentionally interface-driven: search adapters can be
    swapped by replacing the fetcher or by adding another provider class.
    """

    provider_id = "external_web"

    def __init__(self, fetcher: FetchFn | None = None) -> None:
        self._fetcher = fetcher or _default_fetch

    def search(self, query: str, *, limit: int = 5, allow_network: bool = True, timeout: float = 8.0) -> ProviderResult:
        query = str(query or "").strip()
        if not query:
            raise ValueError("'query' is required")
        if not allow_network:
            return ProviderResult(query, self.provider_id, [], "External web access is disabled.", False)

        url = query if query.startswith(("http://", "https://")) else "https://duckduckgo.com/html/?" + urllib.parse.urlencode({"q": query})
        try:
            body = self._fetcher(url, timeout)
        except Exception as exc:
            return ProviderResult(query, self.provider_id, [], f"External web request failed: {exc}", True)

        sources = self._parse_duckduckgo(body, query, limit)
        if not sources and url.startswith(("http://", "https://")):
            title = _html_title(body) or url
            sources.append(self._source(query, title, url, _strip_html(body)))
        return ProviderResult(query, self.provider_id, sources[:limit], f"Found {len(sources[:limit])} external web sources.", True)

    def _parse_duckduckgo(self, body: str, query: str, limit: int) -> list[dict[str, Any]]:
        matches = re.findall(r'<a[^>]+class="result__a"[^>]+href="([^"]+)"[^>]*>(.*?)</a>', body, flags=re.I | re.S)
        snippets = re.findall(r'<a[^>]+class="result__snippet"[^>]*>(.*?)</a>|<div[^>]+class="result__snippet"[^>]*>(.*?)</div>', body, flags=re.I | re.S)
        sources: list[dict[str, Any]] = []
        for index, (href, title_html) in enumerate(matches[:limit]):
            title = _strip_html(title_html, limit=180) or f"Result {index + 1}"
            parsed_href = urllib.parse.unquote(href)
            url = parsed_href
            if "uddg=" in parsed_href:
                params = urllib.parse.parse_qs(urllib.parse.urlparse(parsed_href).query)
                url = params.get("uddg", [parsed_href])[0]
            snippet_parts = snippets[index] if index < len(snippets) else ("", "")
            snippet = _strip_html(" ".join(part for part in snippet_parts if part), limit=500)
            sources.append(self._source(query, title, url, snippet))
        return sources

    def _source(self, query: str, title: str, url: str, summary: str) -> dict[str, Any]:
        return {
            "source_id": "web:" + url,
            "type": "external_web",
            "title": title,
            "url": url,
            "trust_level": "medium",
            "summary": summary,
            "provider": self.provider_id,
            "retrieved_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "metadata": {"query": query},
        }


class RedditProvider:
    provider_id = "reddit"

    def __init__(self, fetcher: FetchFn | None = None) -> None:
        self._fetcher = fetcher or _default_fetch

    def search(
        self,
        query: str,
        *,
        subreddit: str | None = None,
        sort: str = "relevance",
        limit: int = 10,
        allow_network: bool = True,
        timeout: float = 8.0,
    ) -> ProviderResult:
        query = str(query or "").strip()
        if not query:
            raise ValueError("'query' is required")
        if not allow_network:
            return ProviderResult(query, self.provider_id, [], "Reddit access is disabled.", False)
        subreddit = str(subreddit or "").strip().strip("/")
        base = f"https://www.reddit.com/r/{urllib.parse.quote(subreddit)}/search.json" if subreddit else "https://www.reddit.com/search.json"
        params = {"q": query, "sort": sort or "relevance", "limit": max(1, min(int(limit), 50)), "restrict_sr": "1" if subreddit else "0"}
        url = base + "?" + urllib.parse.urlencode(params)
        try:
            payload = json.loads(self._fetcher(url, timeout))
        except Exception as exc:
            return ProviderResult(query, self.provider_id, [], f"Reddit request failed: {exc}", True)

        sources: list[dict[str, Any]] = []
        for child in payload.get("data", {}).get("children", [])[: params["limit"]]:
            data = child.get("data", {}) if isinstance(child, dict) else {}
            permalink = str(data.get("permalink") or "")
            full_url = "https://www.reddit.com" + permalink if permalink.startswith("/") else str(data.get("url") or "")
            title = str(data.get("title") or "Reddit post")
            sources.append(
                {
                    "source_id": "reddit:" + str(data.get("id") or full_url),
                    "type": "reddit_post",
                    "title": title,
                    "url": full_url,
                    "trust_level": "community",
                    "summary": _strip_html(str(data.get("selftext") or data.get("subreddit_name_prefixed") or title)),
                    "provider": self.provider_id,
                    "retrieved_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "metadata": {
                        "subreddit": data.get("subreddit"),
                        "score": data.get("score"),
                        "num_comments": data.get("num_comments"),
                    },
                }
            )
        return ProviderResult(query, self.provider_id, sources, f"Found {len(sources)} Reddit sources.", True)


class ResearchProviderRegistry:
    def __init__(self, fetcher: FetchFn | None = None) -> None:
        self._providers = {
            "external_web": ExternalWebProvider(fetcher),
            "reddit": RedditProvider(fetcher),
        }

    def get(self, provider_id: str) -> ExternalWebProvider | RedditProvider:
        provider = self._providers.get(provider_id)
        if provider is None:
            raise KeyError(provider_id)
        return provider

    def list(self) -> list[dict[str, str]]:
        return [{"id": key, "name": provider.provider_id} for key, provider in self._providers.items()]
