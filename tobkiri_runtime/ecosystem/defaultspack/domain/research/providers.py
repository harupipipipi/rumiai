from __future__ import annotations

import html
import json
import ipaddress
import re
import socket
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable


FetchFn = Callable[[str, float], str]
MAX_RESPONSE_BYTES = 1024 * 1024
MAX_SEARCH_SCAN_RESULTS = 20
ENRICHED_SUMMARY_LIMIT = 500
DEFAULT_TOKEN_CHAR_RATIO = 4
ALLOWED_CONTENT_PREFIXES = (
    "application/json",
    "application/x-json",
    "text/html",
    "text/plain",
)
OFFICIAL_DOMAIN_HINTS: dict[str, tuple[str, ...]] = {
    "anthropic": ("anthropic.com", "docs.anthropic.com"),
    "cerebras": ("cerebras.ai", "docs.cerebras.ai", "inference-docs.cerebras.ai"),
    "cloudflare": ("cloudflare.com", "developers.cloudflare.com"),
    "docker": ("docker.com", "docs.docker.com"),
    "github": ("github.com", "docs.github.com"),
    "google": ("google.com", "ai.google.dev", "developers.google.com"),
    "groq": ("groq.com", "console.groq.com"),
    "nextjs": ("nextjs.org", "vercel.com"),
    "node": ("nodejs.org",),
    "npm": ("npmjs.com", "docs.npmjs.com"),
    "openai": ("openai.com", "platform.openai.com"),
    "playwright": ("playwright.dev",),
    "python": ("python.org", "docs.python.org"),
    "react": ("react.dev",),
    "supabase": ("supabase.com", "supabase.com/docs"),
    "typescript": ("typescriptlang.org", "www.typescriptlang.org"),
    "vercel": ("vercel.com", "nextjs.org"),
    "xiaomi": ("xiaomimimo.com", "platform.mi.com"),
    "mimo": ("xiaomimimo.com", "platform.mi.com"),
}


def _validate_public_http_url(url: str) -> str:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("only http/https URLs are allowed")
    if not parsed.hostname:
        raise ValueError("URL hostname is required")
    host = parsed.hostname.strip("[]")
    try:
        addresses = socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ValueError("URL hostname could not be resolved") from exc
    for family, _, _, _, sockaddr in addresses:
        ip = ipaddress.ip_address(sockaddr[0])
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
            raise ValueError("URL resolves to a non-public address")
    return urllib.parse.urlunparse(parsed)


class _SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        _validate_public_http_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _default_fetch(url: str, timeout: float) -> str:
    url = _validate_public_http_url(url)
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "RumiDefaultspack/1.0 (+local-first research)",
            "Accept": "application/json,text/html;q=0.9,*/*;q=0.8",
        },
    )
    opener = urllib.request.build_opener(_SafeRedirectHandler)
    with opener.open(request, timeout=timeout) as response:
        _validate_public_http_url(response.geturl())
        content_type = (response.headers.get_content_type() or "").lower()
        if content_type and not content_type.startswith(ALLOWED_CONTENT_PREFIXES):
            raise ValueError("unsupported response content-type: " + content_type)
        charset = response.headers.get_content_charset() or "utf-8"
        body = response.read(MAX_RESPONSE_BYTES + 1)
        if len(body) > MAX_RESPONSE_BYTES:
            raise ValueError("response exceeds 1 MiB limit")
        return body.decode(charset, errors="replace")


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


def _hostname(url: str) -> str:
    parsed = urllib.parse.urlparse(str(url or ""))
    return str(parsed.hostname or "").strip("[]").lower()


def _normalize_domains(domains: Any) -> list[str]:
    if domains is None:
        return []
    if isinstance(domains, str):
        items = domains.replace(",", "\n").splitlines()
    elif isinstance(domains, (list, tuple, set)):
        items = list(domains)
    else:
        items = [domains]
    cleaned: list[str] = []
    for item in items:
        domain = str(item or "").strip().lower()
        if not domain:
            continue
        domain = domain.removeprefix("https://").removeprefix("http://")
        domain = domain.split("/", 1)[0].strip("[]")
        if domain and domain not in cleaned:
            cleaned.append(domain)
    return cleaned


def _domain_matches(host: str, domains: list[str]) -> bool:
    host = str(host or "").lower()
    for domain in domains:
        if host == domain or host.endswith("." + domain):
            return True
    return False


def _official_domains_for_query(query: str, extra_domains: list[str] | None = None) -> list[str]:
    text = str(query or "").lower()
    matched: list[str] = []
    for keyword, domains in OFFICIAL_DOMAIN_HINTS.items():
        if keyword not in text:
            continue
        for domain in domains:
            if domain not in matched:
                matched.append(domain)
    for domain in extra_domains or []:
        if domain not in matched:
            matched.append(domain)
    return matched


def _page_excerpt(value: str, title: str = "") -> str:
    clean = _strip_html(value, limit=ENRICHED_SUMMARY_LIMIT * 3)
    if title and clean.lower().startswith(title.lower()):
        clean = clean[len(title) :].strip(" -:\n\t")
    return clean[:ENRICHED_SUMMARY_LIMIT]


def _query_terms(query: str) -> list[str]:
    return [term for term in re.split(r"\W+", str(query or "").lower()) if len(term) >= 2]


def _html_attr(attrs: str, name: str) -> str:
    match = re.search(rf"""\b{name}\s*=\s*(['"])(.*?)\1""", attrs, flags=re.I | re.S)
    return html.unescape(match.group(2)).strip() if match else ""


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


def _output_budget(max_chars: Any = None, max_tokens: Any = None, *, default: int | None = None) -> int | None:
    candidates: list[int] = []
    for value, ratio in ((max_chars, 1), (max_tokens, DEFAULT_TOKEN_CHAR_RATIO)):
        if value is None or value == "":
            continue
        try:
            parsed = int(value)
        except Exception:
            continue
        if parsed > 0:
            candidates.append(parsed * ratio)
    if not candidates:
        return default
    return max(200, min(min(candidates), 40_000))


def _clip_text(value: Any, max_chars: int) -> tuple[str, bool]:
    text = str(value or "")
    if len(text) <= max_chars:
        return text, False
    return text[: max(0, max_chars - 28)].rstrip() + "\n[truncated]", True


def compact_provider_result(
    result: ProviderResult,
    *,
    max_chars: Any = None,
    max_tokens: Any = None,
) -> ProviderResult:
    budget = _output_budget(max_chars, max_tokens)
    if budget is None:
        return result
    sources = list(result.sources or [])
    if not sources:
        return result
    per_source = max(80, min(800, budget // max(1, len(sources))))
    truncated = False
    compact_sources: list[dict[str, Any]] = []
    for source in sources:
        item = dict(source)
        item_truncated = False
        for key in ("summary", "snippet", "excerpt", "content"):
            if key not in item:
                continue
            clipped, did_truncate = _clip_text(item.get(key), per_source)
            item[key] = clipped
            item_truncated = item_truncated or did_truncate
            truncated = truncated or did_truncate
        if item_truncated:
            metadata = dict(item.get("metadata") if isinstance(item.get("metadata"), dict) else {})
            metadata["output_compacted"] = True
            item["metadata"] = metadata
        compact_sources.append(item)
    summary = result.summary
    if truncated:
        summary = f"{summary} Source text was compacted to fit the requested output budget."
    return ProviderResult(
        result.query,
        result.provider,
        compact_sources,
        summary,
        result.network_enabled,
    )


class ExternalWebProvider:
    """Small network-search provider with a fetchable URL fallback.

    The provider is intentionally interface-driven: search adapters can be
    swapped by replacing the fetcher or by adding another provider class.
    """

    provider_id = "external_web"

    def __init__(self, fetcher: FetchFn | None = None) -> None:
        self._fetcher = fetcher or _default_fetch

    def search(
        self,
        query: str,
        *,
        limit: int = 5,
        allow_network: bool = True,
        timeout: float = 8.0,
        domains: list[str] | str | None = None,
        official_only: bool = False,
        fetch_pages: bool = False,
    ) -> ProviderResult:
        query = str(query or "").strip()
        if not query:
            raise ValueError("'query' is required")
        if not allow_network:
            return ProviderResult(query, self.provider_id, [], "External web access is disabled.", False)
        requested_domains = _normalize_domains(domains)
        preferred_domains = _official_domains_for_query(query, requested_domains if official_only else None)
        direct_url = query.startswith(("http://", "https://"))
        url = query if direct_url else "https://duckduckgo.com/lite/?" + urllib.parse.urlencode({"q": query})
        try:
            body = self._fetcher(url, timeout)
        except Exception as exc:
            return ProviderResult(query, self.provider_id, [], f"External web request failed: {exc}", True)

        sources: list[dict[str, Any]]
        if direct_url:
            title = _html_title(body) or url
            sources = [self._source(query, title, url, _page_excerpt(body, title))]
        else:
            sources = self._parse_duckduckgo(body, query, min(MAX_SEARCH_SCAN_RESULTS, max(limit * 4, limit)))
        if requested_domains:
            sources = self._filter_sources_by_domains(sources, requested_domains)
        if official_only:
            if preferred_domains:
                sources = self._filter_sources_by_domains(sources, preferred_domains)
            else:
                return ProviderResult(query, self.provider_id, [], "No official-domain hints matched the query.", True)
        if fetch_pages:
            sources = self._enrich_sources(sources, timeout=timeout)
        sources = self._rank_sources(sources, query, preferred_domains if official_only else requested_domains or preferred_domains)
        limited = sources[: max(1, min(int(limit), MAX_SEARCH_SCAN_RESULTS))]
        filters: list[str] = []
        if requested_domains:
            filters.append("domains=" + ",".join(requested_domains))
        if official_only:
            filters.append("official_only")
        if fetch_pages:
            filters.append("page_fetch")
        filter_text = f" ({'; '.join(filters)})" if filters else ""
        return ProviderResult(query, self.provider_id, limited, f"Found {len(limited)} external web sources{filter_text}.", True)

    def _parse_duckduckgo(self, body: str, query: str, limit: int) -> list[dict[str, Any]]:
        matches: list[tuple[str, str]] = []
        for anchor in re.finditer(r"<a(?P<attrs>[^>]*)>(?P<title>.*?)</a>", body, flags=re.I | re.S):
            attrs = anchor.group("attrs")
            classes = {
                token.strip().lower()
                for token in _html_attr(attrs, "class").split()
                if token.strip()
            }
            if not classes.intersection({"result__a", "result-link"}):
                continue
            href = _html_attr(attrs, "href")
            if not href:
                continue
            matches.append((href, anchor.group("title")))

        snippets: list[str] = []
        for node in re.finditer(
            r"<(?P<tag>a|div|td)(?P<attrs>[^>]*)>(?P<content>.*?)</(?P=tag)>",
            body,
            flags=re.I | re.S,
        ):
            attrs = node.group("attrs")
            classes = {
                token.strip().lower()
                for token in _html_attr(attrs, "class").split()
                if token.strip()
            }
            if not classes.intersection({"result__snippet", "result-snippet"}):
                continue
            snippets.append(_strip_html(node.group("content"), limit=500))

        sources: list[dict[str, Any]] = []
        for index, (href, title_html) in enumerate(matches[:limit]):
            title = _strip_html(title_html, limit=180) or f"Result {index + 1}"
            parsed_href = urllib.parse.unquote(href)
            if parsed_href.startswith("//"):
                parsed_href = "https:" + parsed_href
            url = parsed_href
            if "uddg=" in parsed_href:
                params = urllib.parse.parse_qs(urllib.parse.urlparse(parsed_href).query)
                url = params.get("uddg", [parsed_href])[0]
            snippet = snippets[index] if index < len(snippets) else ""
            sources.append(self._source(query, title, url, snippet))
        return sources

    def _filter_sources_by_domains(self, sources: list[dict[str, Any]], domains: list[str]) -> list[dict[str, Any]]:
        filtered: list[dict[str, Any]] = []
        for source in sources:
            host = _hostname(source.get("url", ""))
            if _domain_matches(host, domains):
                filtered.append(source)
        return filtered

    def _enrich_sources(self, sources: list[dict[str, Any]], *, timeout: float) -> list[dict[str, Any]]:
        enriched: list[dict[str, Any]] = []
        for source in sources:
            item = dict(source)
            metadata = dict(item.get("metadata") if isinstance(item.get("metadata"), dict) else {})
            try:
                body = self._fetcher(str(item.get("url") or ""), timeout)
                title = _html_title(body) or str(item.get("title") or "")
                excerpt = _page_excerpt(body, title)
                if title:
                    item["title"] = title
                if excerpt:
                    item["summary"] = excerpt
                metadata["enriched_from_page"] = True
            except Exception as exc:
                metadata["enrichment_error"] = str(exc)
            item["metadata"] = metadata
            enriched.append(item)
        return enriched

    def _rank_sources(self, sources: list[dict[str, Any]], query: str, preferred_domains: list[str]) -> list[dict[str, Any]]:
        preferred_domains = _normalize_domains(preferred_domains)
        terms = _query_terms(query)
        ranked: list[dict[str, Any]] = []
        for index, source in enumerate(sources):
            item = dict(source)
            metadata = dict(item.get("metadata") if isinstance(item.get("metadata"), dict) else {})
            title = str(item.get("title") or "").lower()
            summary = str(item.get("summary") or "").lower()
            url = str(item.get("url") or "").lower()
            domain = _hostname(url)
            score = max(0, 200 - (index * 5))
            for term in terms:
                score += title.count(term) * 8
                score += summary.count(term) * 4
                score += url.count(term) * 2
            if preferred_domains and _domain_matches(domain, preferred_domains):
                score += 60
                metadata["official"] = True
                item["trust_level"] = "high"
            metadata["domain"] = domain
            metadata["rank_score"] = score
            item["metadata"] = metadata
            ranked.append(item)
        ranked.sort(key=lambda entry: int(((entry.get("metadata") if isinstance(entry.get("metadata"), dict) else {}) or {}).get("rank_score", 0)), reverse=True)
        return ranked

    def _source(self, query: str, title: str, url: str, summary: str) -> dict[str, Any]:
        host = _hostname(url)
        return {
            "source_id": "web:" + url,
            "type": "external_web",
            "title": title,
            "url": url,
            "trust_level": "medium",
            "summary": summary,
            "provider": self.provider_id,
            "retrieved_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "metadata": {"query": query, "domain": host},
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
