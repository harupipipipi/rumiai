"""Fail-closed client for a fixed Cloudflare Workers Python tool service."""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from typing import Any, Callable, Mapping
from urllib import error as urllib_error
from urllib import parse, request

PROVIDER_INSTANCE_ID = "cloudflare-worker-python.fixed-tools"
EXPECTED_CONSUMER = "rumi_tool_remote_executor_pack"
REMOTE_OPERATION = "rumi.service.tool.remote.operation.v1"
URL_ENV = "RUMI_CLOUDFLARE_WORKER_PYTHON_URL"
API_KEY_ENV = "RUMI_CLOUDFLARE_WORKER_PYTHON_API_KEY"
MAX_REQUEST_BYTES = 64 * 1024
MAX_RESPONSE_BYTES = 1024 * 1024
MAX_TIMEOUT_SECONDS = 30.0
SUPPORTED_TOOLS = frozenset({"calculator", "reddit_search", "web_search"})
TOOL_ALIASES = {
    "tool_reddit_search": "reddit_search",
    "tool_web_search": "web_search",
}
FORBIDDEN_ARGUMENT_KEYS = frozenset(
    {
        "cloud_execution",
        "execution_location",
        "execution_provider",
        "execution_route",
        "execution_target",
        "provider_id",
    }
)


@dataclass(frozen=True)
class WorkerResponse:
    """Bounded HTTP response returned by the injected transport."""

    status: int
    body: bytes


WorkerTransport = Callable[
    [str, str, bytes, Mapping[str, str], float], WorkerResponse
]


def create_definition_contribution(
    client: Any,
) -> Callable[[str, Mapping[str, Any]], dict[str, Any]]:
    """Expose signed fixed-tool definitions for explicit Worker profiles."""

    del client

    def operation(name: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        if name not in {"list", "catalog"}:
            raise ValueError(f"unknown Workers Python catalog operation: {name}")
        del payload
        return {
            "definitions": _definitions(),
            "aliases": {
                "tool_reddit_search": "reddit_search",
                "tool_web_search": "web_search",
            },
        }

    return operation


def create_invoke_operation(
    client: Any,
    *,
    transport: WorkerTransport | None = None,
    environ: Mapping[str, str] | None = None,
) -> Callable[[str, Mapping[str, Any]], dict[str, Any]]:
    """Create the exact-provider remote operation used by the tool executor."""

    del client
    bound_transport = transport or _urllib_transport
    bound_environ = environ if environ is not None else os.environ

    def operation(name: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        if name != "invoke":
            raise ValueError(f"unknown Workers Python operation: {name}")
        if payload.get("_contract_consumer_pack_id") != EXPECTED_CONSUMER:
            raise PermissionError("Workers Python consumer is not authorized")
        return _invoke(bound_transport, bound_environ, payload)

    return operation


def _invoke(
    transport: WorkerTransport,
    environ: Mapping[str, str],
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    tool_id = _normalize_tool_id(payload.get("tool_id"))
    if tool_id not in SUPPORTED_TOOLS:
        return _error(
            "worker_python_tool_unsupported",
            "Cloudflare Workers Python accepts only its fixed tool allowlist.",
        )
    arguments = payload.get("arguments")
    if not isinstance(arguments, Mapping):
        return _error(
            "worker_python_arguments_invalid", "tool arguments must be an object"
        )
    if FORBIDDEN_ARGUMENT_KEYS.intersection(str(key) for key in arguments):
        return _error(
            "worker_python_routing_argument_rejected",
            "routing metadata is not accepted inside tool arguments",
        )
    endpoint = _endpoint(environ.get(URL_ENV, ""))
    api_key = str(environ.get(API_KEY_ENV, "") or "").strip()
    if endpoint is None or not api_key:
        return _error(
            "worker_python_not_configured",
            "Cloudflare Workers Python endpoint and API key are required.",
        )
    try:
        body = json.dumps(
            {"tool_name": tool_id, "arguments": dict(arguments)},
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
    except (TypeError, ValueError):
        return _error(
            "worker_python_arguments_invalid", "tool arguments must be JSON values"
        )
    if len(body) > MAX_REQUEST_BYTES:
        return _error(
            "worker_python_request_too_large", "tool request exceeds the size limit"
        )
    try:
        response = transport(
            "POST",
            f"{endpoint}/v1/tools/invoke",
            body,
            {
                "accept": "application/json",
                "authorization": f"Bearer {api_key}",
                "content-type": "application/json",
            },
            _timeout(payload.get("deadline")),
        )
    except TimeoutError:
        return _error("worker_python_timeout", "Workers Python request timed out")
    except (OSError, urllib_error.URLError):
        return _error(
            "worker_python_unavailable", "Workers Python endpoint is unavailable"
        )
    if not 200 <= response.status < 300:
        return _error(
            "worker_python_http_error",
            "Workers Python endpoint rejected the request.",
            status=response.status,
        )
    if len(response.body) > MAX_RESPONSE_BYTES:
        return _error(
            "worker_python_response_too_large", "Workers Python response is too large"
        )
    try:
        value = json.loads(response.body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return _error(
            "worker_python_response_invalid", "Workers Python returned invalid JSON"
        )
    if not isinstance(value, Mapping):
        return _error(
            "worker_python_response_invalid", "Workers Python returned invalid JSON"
        )
    if value.get("ok") is not True:
        return _error(
            str(value.get("code") or "worker_python_tool_failed")[:100],
            str(value.get("error") or "Workers Python tool failed")[:500],
        )
    return {
        "result": value.get("result"),
        "is_error": False,
        "error": None,
        "widget": value.get("widget") if isinstance(value.get("widget"), Mapping) else None,
        "provider_runtime": "cloudflare_worker_python",
    }


def _normalize_tool_id(value: Any) -> str:
    tool_id = str(value or "").strip()
    return TOOL_ALIASES.get(tool_id, tool_id)


def _definitions() -> list[dict[str, Any]]:
    query_schema = {
        "type": "object",
        "additionalProperties": False,
        "required": ["query"],
        "properties": {
            "query": {"type": "string", "minLength": 1, "maxLength": 512},
            "limit": {"type": "integer", "minimum": 1, "maximum": 10},
        },
    }
    reddit_schema = {
        **query_schema,
        "properties": {
            **query_schema["properties"],
            "sort": {
                "type": "string",
                "enum": ["comments", "hot", "new", "relevance", "top"],
            },
            "subreddit": {
                "type": "string",
                "pattern": "^[A-Za-z0-9_]{1,21}$",
            },
        },
    }
    calculator_schema = {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "expression": {"type": "string", "minLength": 1, "maxLength": 256},
            "query": {"type": "string", "minLength": 1, "maxLength": 256},
        },
        "anyOf": [{"required": ["expression"]}, {"required": ["query"]}],
    }
    return [
        _definition("calculator", "Calculate bounded arithmetic", calculator_schema),
        _definition("reddit_search", "Search public Reddit posts", reddit_schema),
        _definition("web_search", "Search the public web", query_schema),
    ]


def _definition(
    tool_id: str, description: str, schema: Mapping[str, Any]
) -> dict[str, Any]:
    return {
        "tool_id": tool_id,
        "display_name": description,
        "description": description,
        "input_schema": dict(schema),
        "result_schema": {"type": "object"},
        "execution": {
            "kind": "remote",
            "contract_id": REMOTE_OPERATION,
            "provider_instance_id": (
                "rumi_cloudflare_worker_python_pack."
                "cloudflare-worker-python.fixed-tools"
            ),
        },
        "authority": "service.invoke",
        "risk": "low",
        "policy_tags": ["cloudflare", "fixed-api", "network-read"],
        "aliases": [],
        "widget": {},
        "source_adapter_id": "rumi_cloudflare_worker_python_pack",
    }


def _endpoint(value: Any) -> str | None:
    clean = str(value or "").strip().rstrip("/")
    if not clean:
        return None
    parsed = parse.urlsplit(clean)
    hostname = (parsed.hostname or "").lower()
    local = hostname in {"127.0.0.1", "::1", "localhost"} or hostname.endswith(
        ".localhost"
    )
    if (
        not hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
        or (not local and not hostname.endswith(".workers.dev"))
        or (parsed.scheme != "https" and not (local and parsed.scheme == "http"))
        or (not local and parsed.port not in {None, 443})
        or (local and parsed.port not in {None, 443, 8787})
    ):
        return None
    return clean


def _timeout(deadline: Any) -> float:
    try:
        remaining = float(deadline) - time.time()
    except (TypeError, ValueError):
        remaining = 15.0
    return max(0.1, min(MAX_TIMEOUT_SECONDS, remaining))


def _urllib_transport(
    method: str,
    url: str,
    body: bytes,
    headers: Mapping[str, str],
    timeout: float,
) -> WorkerResponse:
    req = request.Request(
        url, data=body, headers=dict(headers), method=method
    )
    opener = request.build_opener(_NoRedirectHandler())
    try:
        with opener.open(req, timeout=timeout) as opened:
            response_body = opened.read(MAX_RESPONSE_BYTES + 1)
            return WorkerResponse(int(getattr(opened, "status", 200)), response_body)
    except urllib_error.HTTPError as exc:
        return WorkerResponse(int(exc.code), exc.read(MAX_RESPONSE_BYTES + 1))


class _NoRedirectHandler(request.HTTPRedirectHandler):
    """Prevent bearer credentials from following redirects."""

    def redirect_request(
        self,
        req: Any,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> None:
        del req, fp, code, msg, headers, newurl
        return None


def _error(code: str, message: str, **details: Any) -> dict[str, Any]:
    return {
        "result": None,
        "is_error": True,
        "error": {"code": code, "message": message, **details},
        "widget": None,
        "provider_runtime": "cloudflare_worker_python",
    }
