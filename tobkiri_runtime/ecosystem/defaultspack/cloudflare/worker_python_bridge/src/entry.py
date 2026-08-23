"""Cloudflare Workers Python entrypoint for Tobkiri fixed tools."""

from __future__ import annotations

import ast
import hmac
import json
import math
import re
from typing import Any
from urllib.parse import urlencode, urlparse

from js import Object, fetch
from pyodide.ffi import to_js as _to_js
from workers import Response, WorkerEntrypoint

SERVICE_NAME = "tobkiri-cloudflare-worker-python-bridge"
SUPPORTED_TOOLS = {
    "calculator",
    "reddit_search",
    "tool_reddit_search",
    "tool_web_search",
    "web_search",
}
TOOL_ALIASES = {
    "tool_reddit_search": "reddit_search",
    "tool_web_search": "web_search",
}
MAX_QUERY_LENGTH = 512
MAX_EXPRESSION_LENGTH = 256
MAX_AST_NODES = 64
MAX_UPSTREAM_BYTES = 1024 * 1024
MAX_ABSOLUTE_RESULT = 1e100
_SUBREDDIT = re.compile(r"^[A-Za-z0-9_]{1,21}$")


class Default(WorkerEntrypoint):
    """Serve the finite health and tool-invocation API."""

    async def fetch(self, request):
        url = urlparse(request.url)
        path = url.path.rstrip("/") or "/"
        if request.method == "GET" and path == "/health":
            return json_response(health(self.env))
        if request.method != "POST" or path != "/v1/tools/invoke":
            return json_response({"ok": False, "error": "not_found"}, status=404)
        authorization = authorized(request, self.env)
        if not authorization["ok"]:
            return json_response(
                {"ok": False, "error": authorization["error"]},
                status=authorization["status"],
            )
        try:
            payload = await request.json()
        except Exception:
            return json_response({"ok": False, "error": "invalid_json"}, status=400)
        if not isinstance(payload, dict) or not isinstance(
            payload.get("arguments"), dict
        ):
            return json_response(
                {"ok": False, "error": "invalid_payload"}, status=400
            )
        tool_name = normalize_tool_name(payload.get("tool_name"))
        if tool_name not in {"calculator", "reddit_search", "web_search"}:
            return json_response(
                {
                    "ok": False,
                    "code": "TOOL_UNSUPPORTED",
                    "error": "Unsupported Workers Python fixed tool.",
                },
                status=400,
            )
        try:
            if tool_name == "web_search":
                result = await web_search(payload["arguments"])
            elif tool_name == "reddit_search":
                result = await reddit_search(payload["arguments"])
            else:
                result = calculator(payload["arguments"])
        except ToolError as exc:
            return json_response(
                {"ok": False, "code": exc.code, "error": exc.message},
                status=exc.status,
            )
        except Exception:
            return json_response(
                {
                    "ok": False,
                    "code": "TOOL_FAILED",
                    "error": "Fixed tool execution failed.",
                },
                status=500,
            )
        return json_response(
            {
                "ok": True,
                "tool_name": tool_name,
                "result": result["result"],
                "is_error": False,
                "widget": result.get("widget"),
                "provider_runtime": "cloudflare_worker_python",
            }
        )


async def web_search(arguments: dict[str, Any]) -> dict[str, Any]:
    """Run bounded DuckDuckGo instant-answer search."""

    query = bounded_query(arguments.get("query"))
    limit = bounded_int(arguments.get("limit"), default=5, minimum=1, maximum=10)
    params = urlencode(
        {"q": query, "format": "json", "no_html": "1", "skip_disambig": "1"}
    )
    payload = await fetch_json(f"https://api.duckduckgo.com/?{params}")
    topics = flatten_duckduckgo_topics(payload.get("RelatedTopics"))
    sources: list[dict[str, Any]] = []
    abstract_url = str(payload.get("AbstractURL") or "")
    abstract = str(payload.get("AbstractText") or "")[:1000]
    if abstract_url or abstract:
        sources.append(
            {
                "title": str(payload.get("Heading") or query)[:300],
                "url": abstract_url[:2000],
                "snippet": abstract,
                "source": "duckduckgo",
            }
        )
    sources.extend(topics)
    sources = sources[:limit]
    summary = "\n".join(
        f"- {item.get('title') or item.get('url')}: "
        f"{item.get('snippet') or item.get('url')}"
        for item in sources
    )
    return {
        "result": summary or f"No web search results returned for {query}.",
        "widget": {
            "type": "research_sources",
            "query": query,
            "sources": sources,
            "summary": summary,
        },
    }


async def reddit_search(arguments: dict[str, Any]) -> dict[str, Any]:
    """Run bounded Reddit public search without OAuth promotion."""

    query = bounded_query(arguments.get("query"))
    limit = bounded_int(arguments.get("limit"), default=5, minimum=1, maximum=10)
    sort = str(arguments.get("sort") or "relevance").strip().lower()
    if sort not in {"comments", "hot", "new", "relevance", "top"}:
        raise ToolError("INVALID_INPUT", "Unsupported Reddit sort order.", 400)
    subreddit = str(arguments.get("subreddit") or "").strip().strip("/")
    if subreddit and not _SUBREDDIT.fullmatch(subreddit):
        raise ToolError("INVALID_INPUT", "Invalid subreddit name.", 400)
    base_path = f"/r/{subreddit}/search.json" if subreddit else "/search.json"
    params = {"q": query, "sort": sort, "limit": str(limit), "raw_json": "1"}
    if subreddit:
        params["restrict_sr"] = "1"
    payload = await fetch_json(
        f"https://www.reddit.com{base_path}?{urlencode(params)}"
    )
    data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
    children = data.get("children") if isinstance(data.get("children"), list) else []
    sources: list[dict[str, Any]] = []
    for item in children[:limit]:
        record = item.get("data") if isinstance(item, dict) else None
        if not isinstance(record, dict):
            continue
        permalink = str(record.get("permalink") or "")
        sources.append(
            {
                "title": str(record.get("title") or "")[:300],
                "url": (
                    f"https://www.reddit.com{permalink}"
                    if permalink
                    else str(record.get("url") or "")[:2000]
                ),
                "snippet": str(
                    record.get("selftext")
                    or record.get("subreddit_name_prefixed")
                    or ""
                )[:500],
                "source": "reddit",
                "score": record.get("score"),
                "comments": record.get("num_comments"),
            }
        )
    summary = "\n".join(
        f"- {item.get('title')}: {item.get('url')}" for item in sources
    )
    return {
        "result": summary or f"No Reddit search results returned for {query}.",
        "widget": {
            "type": "research_sources",
            "query": query,
            "sources": sources,
            "summary": summary,
        },
    }


def calculator(arguments: dict[str, Any]) -> dict[str, Any]:
    """Evaluate bounded numeric arithmetic without dynamic execution."""

    expression = str(
        arguments.get("expression") or arguments.get("query") or ""
    ).strip()
    if not expression or len(expression) > MAX_EXPRESSION_LENGTH:
        raise ToolError("INVALID_INPUT", "A bounded expression is required.", 400)
    value = evaluate_math_expression(expression)
    return {
        "result": str(value),
        "widget": {
            "type": "calculator_result",
            "expression": expression,
            "value": value,
        },
    }


def evaluate_math_expression(expression: str) -> int | float:
    """Parse and evaluate a finite arithmetic AST."""

    try:
        tree = ast.parse(expression, mode="eval")
    except (SyntaxError, ValueError) as exc:
        raise ToolError("INVALID_EXPRESSION", "Invalid arithmetic expression.", 400) from exc
    if sum(1 for _ in ast.walk(tree)) > MAX_AST_NODES:
        raise ToolError("EXPRESSION_TOO_COMPLEX", "Expression is too complex.", 400)
    return evaluate_ast(tree.body)


def evaluate_ast(node: ast.AST) -> int | float:
    """Evaluate an already bounded arithmetic AST node."""

    if (
        isinstance(node, ast.Constant)
        and isinstance(node.value, (int, float))
        and not isinstance(node.value, bool)
    ):
        return bounded_number(node.value)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        value = evaluate_ast(node.operand)
        return bounded_number(value if isinstance(node.op, ast.UAdd) else -value)
    if isinstance(node, ast.BinOp):
        left = evaluate_ast(node.left)
        right = evaluate_ast(node.right)
        if isinstance(node.op, ast.Add):
            return bounded_number(left + right)
        if isinstance(node.op, ast.Sub):
            return bounded_number(left - right)
        if isinstance(node.op, ast.Mult):
            return bounded_number(left * right)
        if isinstance(node.op, ast.Div):
            return bounded_number(left / right)
        if isinstance(node.op, ast.FloorDiv):
            return bounded_number(left // right)
        if isinstance(node.op, ast.Mod):
            return bounded_number(left % right)
        if isinstance(node.op, ast.Pow):
            if abs(right) > 12 or abs(left) > 1_000_000:
                raise ToolError("EXPONENT_LIMIT", "Exponent is outside limits.", 400)
            return bounded_number(left**right)
    raise ToolError(
        "INVALID_EXPRESSION", "Only numeric arithmetic is supported.", 400
    )


def bounded_number(value: int | float) -> int | float:
    """Reject non-finite or unreasonably large numeric results."""

    if isinstance(value, float) and not math.isfinite(value):
        raise ToolError("RESULT_LIMIT", "Result is not finite.", 400)
    if abs(value) > MAX_ABSOLUTE_RESULT:
        raise ToolError("RESULT_LIMIT", "Result exceeds the numeric limit.", 400)
    return value


async def fetch_json(url: str) -> dict[str, Any]:
    """Fetch a bounded object payload from a fixed upstream host."""

    response = await fetch(
        url,
        to_js(
            {
                "headers": {
                    "accept": "application/json",
                    "user-agent": "Tobkiri Workers Python fixed tools",
                }
            }
        ),
    )
    status = int(response.status)
    text = await response.text()
    if len(text.encode("utf-8")) > MAX_UPSTREAM_BYTES:
        raise ToolError("UPSTREAM_TOO_LARGE", "Upstream response is too large.", 502)
    if not 200 <= status < 300:
        raise ToolError("UPSTREAM_HTTP_ERROR", "Upstream request failed.", 502)
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ToolError("UPSTREAM_INVALID_JSON", "Upstream JSON is invalid.", 502) from exc
    if not isinstance(payload, dict):
        raise ToolError("UPSTREAM_INVALID_JSON", "Upstream JSON is invalid.", 502)
    return payload


def flatten_duckduckgo_topics(values: Any) -> list[dict[str, Any]]:
    """Flatten bounded DuckDuckGo topic groups."""

    sources: list[dict[str, Any]] = []
    if not isinstance(values, list):
        return sources
    for item in values[:50]:
        if not isinstance(item, dict):
            continue
        nested = item.get("Topics")
        if isinstance(nested, list):
            sources.extend(flatten_duckduckgo_topics(nested))
            continue
        url = str(item.get("FirstURL") or "")[:2000]
        text = str(item.get("Text") or "")[:1000]
        if url or text:
            sources.append(
                {
                    "title": (text.split(" - ", 1)[0] if text else url)[:300],
                    "url": url,
                    "snippet": text,
                    "source": "duckduckgo",
                }
            )
    return sources[:50]


def bounded_query(value: Any) -> str:
    """Return a non-empty query within the fixed input bound."""

    query = str(value or "").strip()
    if not query or len(query) > MAX_QUERY_LENGTH:
        raise ToolError("INVALID_INPUT", "A bounded query is required.", 400)
    return query


def bounded_int(value: Any, *, default: int, minimum: int, maximum: int) -> int:
    """Coerce only a bounded pagination integer."""

    try:
        number = int(value)
    except (TypeError, ValueError):
        number = default
    return min(max(number, minimum), maximum)


def health(env: Any) -> dict[str, Any]:
    """Return secret-free readiness metadata."""

    configured = bool(
        str(getattr(env, "RUMI_CLOUDFLARE_WORKER_PYTHON_API_KEY", "") or "").strip()
    )
    return {
        "ok": configured,
        "service": SERVICE_NAME,
        "runtime": "cloudflare_worker_python",
        "api_key_configured": configured,
        "routes": ["GET /health", "POST /v1/tools/invoke"],
        "tools": sorted(SUPPORTED_TOOLS),
        "fixed_tool_api_only": True,
    }


def authorized(request: Any, env: Any) -> dict[str, Any]:
    """Verify the configured bearer secret in constant time."""

    expected = str(
        getattr(env, "RUMI_CLOUDFLARE_WORKER_PYTHON_API_KEY", "") or ""
    ).strip()
    if not expected:
        return {"ok": False, "status": 503, "error": "api_key_not_configured"}
    provided = bearer_token(request.headers.get("Authorization") or "")
    if not provided:
        return {"ok": False, "status": 401, "error": "api_key_required"}
    if not hmac.compare_digest(provided.encode(), expected.encode()):
        return {"ok": False, "status": 403, "error": "api_key_invalid"}
    return {"ok": True}


def bearer_token(value: str) -> str:
    """Extract a strict bearer token."""

    prefix = "Bearer "
    return value[len(prefix) :].strip() if value.startswith(prefix) else ""


def normalize_tool_name(value: Any) -> str:
    """Resolve only the two finite compatibility aliases."""

    tool_name = str(value or "").strip()
    return TOOL_ALIASES.get(tool_name, tool_name)


def to_js(value: Any) -> Any:
    """Convert request options for the Workers JavaScript fetch API."""

    return _to_js(value, dict_converter=Object.fromEntries)


def json_response(payload: dict[str, Any], *, status: int = 200) -> Response:
    """Return non-cacheable JSON."""

    return Response(
        json.dumps(payload),
        status=status,
        headers={
            "cache-control": "no-store",
            "content-type": "application/json; charset=utf-8",
        },
    )


class ToolError(Exception):
    """Safe fixed-tool diagnostic exposed to the caller."""

    def __init__(self, code: str, message: str, status: int) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
