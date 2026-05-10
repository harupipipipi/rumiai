import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from blocks._common import ok, error, timestamp

import base64
import hmac
import json
import re
import signal
import threading
import http.server
import urllib.parse

from bridge.block_adapter import invoke_block
from domain.safety.local_guard import (
    METHOD_SENSITIVE_CODING_PATHS,
    SENSITIVE_CODING_PATHS,
    is_sensitive_coding_path as _local_is_sensitive_coding_path,
    origin_allowed as _local_origin_allowed,
    require_local_guard,
)
from transport.registry import build_always_available_http_routes, build_fallback_http_routes


_PACK_NOT_APPROVED_SAFE_GET_FALLBACK_BLOCKS = {
    "blocks.ui.catalog",
    "blocks.ui.settings",
    "blocks.ui.commands",
}


class DefaultsHttpServer:
    def __init__(self, facade):
        self.facade = facade
        self.host = os.environ.get("DEFAULTS_HTTP_HOST", "127.0.0.1")
        self.port = int(os.environ.get("DEFAULTS_HTTP_PORT", "8766"))
        self._server = None
        self._thread = None
        self._routes = []
        self._load_runtime_secrets()
        self._setup_routes()

    def _load_runtime_secrets(self):
        try:
            from domain.integrations.secrets import load_integration_secrets_into_env

            load_integration_secrets_into_env()
        except Exception:
            pass

    def _setup_routes(self):
        """Build the route table.

        If the kernel facade is available and components have registered
        ``io.http.route`` entries via InterfaceRegistry, those are used.
        Otherwise the hard-coded fallback list is used for backward
        compatibility.

        Each entry in ``self._routes`` is a 5-tuple:
            (method, compiled_regex, handler, source, path_inject)

        *source* is ``"registry"`` or ``"fallback"``.
        *path_inject* is a dict mapping URL param names to request_data keys
        (only meaningful for registry routes).
        """
        registry_routes = []

        # ---- Attempt to collect routes from InterfaceRegistry ----
        if self.facade is not None:
            try:
                raw = self.facade.get_interface("io.http.route", strategy="all")
                if raw and isinstance(raw, list):
                    for entry in raw:
                        if not isinstance(entry, dict):
                            continue
                        method = entry.get("method")
                        pattern = entry.get("pattern")
                        handler = entry.get("handler")
                        path_inject = entry.get("path_inject", {})
                        if method and pattern and callable(handler):
                            regex_pattern = re.sub(
                                r"\{(\w+)\}",
                                lambda match: r"(?P<{}>.+)".format(match.group(1))
                                if match.group(1) == "path"
                                else r"(?P<{}>[^/]+)".format(match.group(1)),
                                pattern,
                            )
                            regex_pattern = "^" + regex_pattern + "$"
                            compiled = re.compile(regex_pattern)
                            registry_routes.append(
                                (method, compiled, handler, "registry", path_inject)
                            )
            except Exception as exc:
                print(
                    "[defaults] WARNING: failed to collect io.http.route from "
                    "InterfaceRegistry – " + str(exc)
                )

        if registry_routes:
            self._routes = registry_routes + build_always_available_http_routes(self)
            print(
                "[defaults] Route registry: loaded "
                + str(len(registry_routes))
                + " routes from InterfaceRegistry"
            )
            return

        # ---- Fallback: registry-defined compatibility routes ----
        print("[defaults] Route registry: no routes found, using fallback")
        self._routes.extend(build_fallback_http_routes(self))

    def start(self):
        _RequestHandler.server_ref = self
        self._server = http.server.ThreadingHTTPServer(
            (self.host, self.port), _RequestHandler
        )
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=False)
        self._thread.start()
        print("[defaults] HTTP server started on " + self.host + ":" + str(self.port))

    def stop(self):
        if self._server is not None:
            self._server.shutdown()
            self._server = None
            self._thread = None

    def _match_route(self, method, path):
        """Match *method* + *path* against the route table.

        Returns ``(handler, path_params, source, path_inject)`` or
        ``(None, None, None, None)`` when nothing matches.
        """
        for route_method, compiled, handler, source, path_inject in self._routes:
            if route_method != method:
                continue
            m = compiled.match(path)
            if m is not None:
                return handler, m.groupdict(), source, path_inject
        return None, None, None, None

    def _build_context(self):
        return {
            "flow_id": "transport_direct",
            "step_id": "http_request",
            "phase": "execute",
            "ts": timestamp(),
            "owner_pack": "defaultspack",
            "inputs": {},
        }

    def _invoke_fallback_block(self, module_name, request_data, path_params, inject=None):
        payload = dict(request_data or {})
        for source_key, dest_key in (inject or {}).items():
            payload[dest_key] = path_params.get(source_key, "")
        context = self._build_context()
        if module_name == "blocks.chat.stream":
            return invoke_block(module_name, payload, context)
        try:
            from domain.function_runtime.bridge import invoke_function
            from domain.function_runtime.registry import function_id_for_block_module

            function_id = function_id_for_block_module(module_name)
            if function_id:
                context["_defaultspack_http_route_adapter"] = True
                result = invoke_function(
                    f"defaultspack:{function_id}",
                    payload,
                    context,
                    principal_id="defaultspack",
                )
                error_info = result.get("error", {}) if isinstance(result, dict) else {}
                error_code = str(error_info.get("code") or "")
                if error_code == "PACK_NOT_APPROVED":
                    if self._pack_not_approved_fallback_allowed(module_name, payload):
                        pass
                    else:
                        return result
                elif error_code not in {
                    "FUNCTION_REGISTRY_UNAVAILABLE",
                    "FUNCTION_NOT_FOUND",
                    "CAPABILITY_RUNTIME_UNAVAILABLE",
                    "CAPABILITY_EXECUTION_FAILED",
                }:
                    return result
        except Exception:
            pass
        return invoke_block(module_name, payload, context)

    def _pack_not_approved_fallback_allowed(self, module_name, payload):
        actual_method = str(payload.get("_actual_method") or "").upper()
        return actual_method == "GET" and module_name in _PACK_NOT_APPROVED_SAFE_GET_FALLBACK_BLOCKS

    # ---- Chat Handlers (fallback) ----

    def _handle_chat_send(self, request_data, path_params):
        return self._invoke_fallback_block("blocks.chat.send", request_data, path_params)

    def _handle_chat_create(self, request_data, path_params):
        return self._invoke_fallback_block("blocks.chat.create_conversation", request_data, path_params)

    def _handle_chat_list(self, request_data, path_params):
        return self._invoke_fallback_block("blocks.chat.list_conversations", request_data, path_params)

    def _handle_chat_get(self, request_data, path_params):
        return self._invoke_fallback_block(
            "blocks.chat.get_conversation",
            request_data,
            path_params,
            {"id": "conversation_id"},
        )

    def _handle_chat_update(self, request_data, path_params):
        return self._invoke_fallback_block(
            "blocks.chat.update_conversation",
            request_data,
            path_params,
            {"id": "conversation_id"},
        )

    def _handle_chat_delete(self, request_data, path_params):
        return self._invoke_fallback_block(
            "blocks.chat.delete_conversation",
            request_data,
            path_params,
            {"id": "conversation_id"},
        )

    def _handle_chat_send_message(self, request_data, path_params):
        return self._invoke_fallback_block(
            "blocks.chat.send",
            request_data,
            path_params,
            {"id": "conversation_id"},
        )

    def _handle_chat_stream(self, request_data, path_params):
        return self._invoke_fallback_block(
            "blocks.chat.stream",
            request_data,
            path_params,
            {"id": "conversation_id"},
        )

    def _handle_chat_export(self, request_data, path_params):
        return self._invoke_fallback_block(
            "blocks.chat.export_conversation",
            request_data,
            path_params,
            {"id": "conversation_id"},
        )

    def _handle_chat_summarize(self, request_data, path_params):
        return self._invoke_fallback_block(
            "blocks.chat.summarize_and_trim",
            request_data,
            path_params,
            {"id": "conversation_id"},
        )

    def _handle_chat_auto_trim(self, request_data, path_params):
        return self._invoke_fallback_block(
            "blocks.chat.auto_trim",
            request_data,
            path_params,
            {"id": "conversation_id"},
        )

    # ---- Agent Handlers (fallback) ----

    def _handle_agent_execute(self, request_data, path_params):
        return self._invoke_fallback_block("blocks.agent.execute", request_data, path_params)

    def _handle_agent_approve(self, request_data, path_params):
        return self._invoke_fallback_block(
            "blocks.agent.approve",
            request_data,
            path_params,
            {"id": "execution_id"},
        )

    def _handle_agent_reject(self, request_data, path_params):
        return self._invoke_fallback_block(
            "blocks.agent.reject",
            request_data,
            path_params,
            {"id": "execution_id"},
        )

    def _handle_agent_cancel(self, request_data, path_params):
        return self._invoke_fallback_block(
            "blocks.agent.cancel",
            request_data,
            path_params,
            {"id": "execution_id"},
        )

    def _handle_agent_status(self, request_data, path_params):
        return self._invoke_fallback_block(
            "blocks.agent.status",
            request_data,
            path_params,
            {"id": "execution_id"},
        )

    # ---- Multi-Agent Handlers (fallback, Group 8) ----

    def _handle_multi_execute(self, request_data, path_params):
        return self._invoke_fallback_block("blocks.agent.multi_execute", request_data, path_params)

    def _handle_multi_status(self, request_data, path_params):
        return self._invoke_fallback_block(
            "blocks.agent.multi_status",
            request_data,
            path_params,
            {"id": "session_id"},
        )

    def _handle_multi_message(self, request_data, path_params):
        return self._invoke_fallback_block(
            "blocks.agent.multi_message",
            request_data,
            path_params,
            {"id": "session_id"},
        )

    # ---- Instruction Handler (fallback, Group 8) ----

    def _handle_agent_instruct(self, request_data, path_params):
        return self._invoke_fallback_block(
            "blocks.agent.add_instruction",
            request_data,
            path_params,
            {"id": "execution_id"},
        )

    # ---- Consent Handlers (fallback, Group 8) ----

    def _handle_consent_check(self, request_data, path_params):
        return self._invoke_fallback_block("blocks.tool.consent_check", request_data, path_params)

    def _handle_consent_confirm(self, request_data, path_params):
        return self._invoke_fallback_block(
            "blocks.tool.consent_confirm",
            request_data,
            path_params,
            {"id": "consent_id"},
        )

    # ---- Knowledge Handlers (fallback, Group 9a) ----

    def _handle_knowledge_create(self, request_data, path_params):
        return self._invoke_fallback_block("blocks.knowledge.create", request_data, path_params)

    def _handle_knowledge_list(self, request_data, path_params):
        return self._invoke_fallback_block("blocks.knowledge.list", request_data, path_params)

    def _handle_knowledge_search(self, request_data, path_params):
        return self._invoke_fallback_block("blocks.knowledge.search", request_data, path_params)

    def _handle_knowledge_get(self, request_data, path_params):
        return self._invoke_fallback_block(
            "blocks.knowledge.get",
            request_data,
            path_params,
            {"id": "id"},
        )

    def _handle_knowledge_update(self, request_data, path_params):
        return self._invoke_fallback_block(
            "blocks.knowledge.update",
            request_data,
            path_params,
            {"id": "id"},
        )

    def _handle_knowledge_delete(self, request_data, path_params):
        return self._invoke_fallback_block(
            "blocks.knowledge.delete",
            request_data,
            path_params,
            {"id": "id"},
        )

    # ---- Prompt Handlers (fallback) ----

    def _handle_prompt_update(self, request_data, path_params):
        return self._invoke_fallback_block(
            "blocks.prompt.update",
            request_data,
            path_params,
            {"name": "name"},
        )

    def _handle_prompt_delete(self, request_data, path_params):
        return self._invoke_fallback_block(
            "blocks.prompt.delete",
            request_data,
            path_params,
            {"name": "name"},
        )

    def _handle_prompt_convert(self, request_data, path_params):
        return self._invoke_fallback_block("blocks.prompt.convert", request_data, path_params)

    # ---- Dynamic Tool Handlers (fallback) ----

    def _handle_tool_create(self, request_data, path_params):
        return self._invoke_fallback_block("blocks.tool.create", request_data, path_params)

    def _handle_tool_update(self, request_data, path_params):
        return self._invoke_fallback_block(
            "blocks.tool.update",
            request_data,
            path_params,
            {"name": "name"},
        )

    def _handle_tool_delete(self, request_data, path_params):
        return self._invoke_fallback_block(
            "blocks.tool.delete",
            request_data,
            path_params,
            {"name": "name"},
        )

    def _handle_tool_export(self, request_data, path_params):
        return self._invoke_fallback_block(
            "blocks.tool.export",
            request_data,
            path_params,
            {"name": "name"},
        )

    # ---- Dev Tool Handlers (fallback, P1-1) ----

    def _handle_dev_inspect(self, request_data, path_params):
        return self._invoke_fallback_block("blocks.dev.inspect", request_data, path_params)

    def _handle_dev_prompt_history(self, request_data, path_params):
        return self._invoke_fallback_block("blocks.dev.prompt_history", request_data, path_params)

    def _handle_dev_edit_prompt(self, request_data, path_params):
        return self._invoke_fallback_block("blocks.dev.edit_prompt_live", request_data, path_params)

    def _handle_dev_replay(self, request_data, path_params):
        return self._invoke_fallback_block("blocks.dev.replay", request_data, path_params)

    # ---- System Handlers (fallback) ----

    def _handle_health(self, request_data, path_params):
        return ok({
            "status": "healthy",
            "pack": "defaultspack",
            "ts": timestamp(),
        })

    def _handle_context_info(self, request_data, path_params):
        interfaces = {}
        if self.facade is not None:
            try:
                interfaces = self.facade.list_interfaces()
            except Exception:
                interfaces = {}
        return ok({
            "pack": "defaultspack",
            "interfaces": interfaces,
            "ts": timestamp(),
        })

    # ---- Static Handlers (fallback) ----

    def _handle_chat_redirect(self, request_data, path_params):
        query = urllib.parse.urlencode({
            key: value
            for key, value in (request_data or {}).items()
            if not str(key).startswith("_")
        })
        location = "/chat" + (("?" + query) if query else "")
        return {"_redirect": True, "location": location, "status_code": 302}

    def _handle_static(self, request_data, path_params):
        shell_path = os.path.join(
            os.path.dirname(__file__), "..", "ui", "shell.html"
        )
        if os.path.isfile(shell_path):
            with open(shell_path, "r", encoding="utf-8") as f:
                body = f.read()
            return {"_static": True, "content_type": "text/html; charset=utf-8", "body": body}
        return {"_static": True, "content_type": "text/html; charset=utf-8",
                "body": "<!DOCTYPE html><html><body><h1>defaults pack</h1><p>shell.html not found</p></body></html>"}

    def _handle_static_file(self, request_data, path_params):
        rel_path = path_params.get("path", "")
        safe_path = os.path.normpath(rel_path)
        if safe_path.startswith("..") or os.path.isabs(safe_path):
            return error("invalid path")
        pack_root = os.path.normpath(os.path.join(os.path.dirname(__file__), ".."))
        file_path = os.path.join(pack_root, "ui", safe_path)
        if not os.path.isfile(file_path) and (
            safe_path == "assets" or safe_path.startswith("assets" + os.sep)
        ):
            file_path = os.path.join(pack_root, safe_path)
        if not os.path.isfile(file_path):
            return error("file not found: " + rel_path)
        ext = os.path.splitext(file_path)[1].lower()
        content_types = {
            ".html": "text/html; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".js": "application/javascript; charset=utf-8",
            ".json": "application/json; charset=utf-8",
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".gif": "image/gif",
            ".svg": "image/svg+xml",
            ".ico": "image/x-icon",
        }
        ct = content_types.get(ext, "application/octet-stream")
        if ct.startswith("text/") or ct.startswith("application/j"):
            with open(file_path, "r", encoding="utf-8") as f:
                body = f.read()
        else:
            with open(file_path, "rb") as f:
                body = f.read()
        return {"_static": True, "content_type": ct, "body": body}


_SENSITIVE_CODING_PATHS = set(SENSITIVE_CODING_PATHS) | set(METHOD_SENSITIVE_CODING_PATHS)

_SENSITIVE_INTEGRATION_PATHS = {
    "/api/integrations/secrets",
}
_SENSITIVE_CHAT_PATH_RE = re.compile(
    r"^/v1/conversations/[^/]+/run-results/[^/]+/browser-screenshots$"
)

_LOCAL_ORIGIN_HOSTS = {"127.0.0.1", "localhost", "::1"}


def _is_sensitive_coding_path(path):
    return _local_is_sensitive_coding_path(path)


def _is_sensitive_http_path(path):
    return (
        path in _SENSITIVE_CODING_PATHS
        or path in _SENSITIVE_INTEGRATION_PATHS
        or _SENSITIVE_CHAT_PATH_RE.match(path) is not None
    )


def _is_allowed_sensitive_origin(origin):
    return _local_origin_allowed(origin)


def _configured_local_auth_token():
    for key in ("RUMI_DEFAULTSPACK_LOCAL_TOKEN", "RUMI_API_TOKEN", "RUMI_TOKEN"):
        value = os.environ.get(key, "").strip()
        if value:
            return value
    return ""


def _bearer_token(headers):
    auth_header = headers.get("Authorization", "")
    if not auth_header.lower().startswith("bearer "):
        return ""
    return auth_header[7:].strip()


class _RequestHandler(http.server.BaseHTTPRequestHandler):
    server_ref = None
    protocol_version = "HTTP/1.1"

    def do_GET(self):
        self._handle_request("GET")

    def do_POST(self):
        self._handle_request("POST")

    def do_PUT(self):
        self._handle_request("PUT")

    def do_DELETE(self):
        self._handle_request("DELETE")

    def do_OPTIONS(self):
        self.send_response(204)
        self._send_cors_headers()
        self.end_headers()

    def _handle_request(self, method):
        try:
            parsed_url = urllib.parse.urlsplit(self.path)
            path = parsed_url.path
            handler, path_params, source, path_inject = self.server_ref._match_route(method, path)
            if handler is None:
                self._send_json(404, error("not found: " + method + " " + path))
                return
            sensitive_error = self._sensitive_request_error(method, path)
            if sensitive_error:
                self._send_json(sensitive_error[0], error(sensitive_error[1], sensitive_error[2]))
                return
            request_data = {
                key: values[-1]
                for key, values in urllib.parse.parse_qs(parsed_url.query, keep_blank_values=True).items()
                if values
            }
            request_data["_headers"] = {str(key): str(value) for key, value in self.headers.items()}
            if method in ("POST", "PUT"):
                content_length = int(self.headers.get("Content-Length", 0))
                if content_length > 0:
                    raw_body = self.rfile.read(content_length)
                    raw_text = raw_body.decode("utf-8", errors="replace")
                    request_data["_raw_body"] = raw_text
                    request_data["_raw_body_base64"] = base64.b64encode(raw_body).decode("ascii")
                    content_type = str(self.headers.get("Content-Type", "")).lower()
                    if "application/x-www-form-urlencoded" in content_type:
                        body_data = {
                            key: values[-1]
                            for key, values in urllib.parse.parse_qs(raw_text, keep_blank_values=True).items()
                            if values
                        }
                    else:
                        try:
                            body_data = json.loads(raw_text)
                        except (json.JSONDecodeError, UnicodeDecodeError):
                            self._send_json(400, error("invalid JSON body"))
                            return
                        if not isinstance(body_data, dict):
                            self._send_json(400, error("JSON body must be an object"))
                            return
                    request_data.update(body_data)

            if source == "registry":
                # Inject path parameters into request_data per route config
                if path_inject and path_params:
                    for url_param, data_key in path_inject.items():
                        request_data[data_key] = path_params.get(url_param, "")
                request_data["_method"] = method
                request_data["_actual_method"] = method
                context = self.server_ref._build_context()
                context["_facade"] = self.server_ref.facade
                result = handler(request_data, context)
            else:
                request_data["_method"] = method
                request_data["_actual_method"] = method
                # Fallback: original handler signature (request_data, path_params)
                result = handler(request_data, path_params)

            if isinstance(result, dict) and result.get("_static"):
                self._send_static(200, result.get("content_type", "text/html"), result.get("body", ""))
            elif isinstance(result, dict) and result.get("_redirect"):
                self._send_redirect(
                    int(result.get("status_code", 302)),
                    str(result.get("location") or "/chat"),
                )
            elif self._sse_events_from_result(result) is not None:
                self._send_sse(self._sse_events_from_result(result))
            else:
                status_code = 200
                if isinstance(result, dict) and result.get("status") == "error":
                    status_code = int(result.pop("_http_status", 400))
                self._send_json(status_code, result)
        except Exception as exc:
            self._send_json(500, error("internal server error: " + str(exc)))

    @staticmethod
    def _sse_events_from_result(result):
        if isinstance(result, dict) and result.get("_sse"):
            return result.get("events", [])
        if (
            isinstance(result, dict)
            and result.get("status") == "ok"
            and isinstance(result.get("data"), dict)
            and result["data"].get("_sse")
        ):
            return result["data"].get("events", [])
        return None

    def _send_json(self, status_code, data):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status_code)
        self._send_cors_headers()
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except BrokenPipeError:
            pass

    def _send_sse(self, events):
        self.send_response(200)
        self._send_cors_headers()
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache, no-transform")
        self.send_header("Connection", "close")
        self.end_headers()
        try:
            for event in events:
                if isinstance(event, bytes):
                    payload = event
                else:
                    payload = ("data: " + json.dumps(event, ensure_ascii=False) + "\n\n").encode("utf-8")
                self.wfile.write(payload)
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            self.close_connection = True

    def _send_redirect(self, status_code, location):
        self.send_response(status_code)
        self._send_cors_headers()
        self.send_header("Location", location)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _send_static(self, status_code, content_type, body):
        if isinstance(body, str):
            body_bytes = body.encode("utf-8")
        else:
            body_bytes = body
        self.send_response(status_code)
        self._send_cors_headers()
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body_bytes)))
        self.end_headers()
        try:
            self.wfile.write(body_bytes)
        except BrokenPipeError:
            pass

    def _sensitive_request_error(self, method, path):
        coding_error = require_local_guard(
            path,
            method,
            {str(key): str(value) for key, value in self.headers.items()},
            self.client_address,
        )
        if coding_error:
            return coding_error
        if _is_sensitive_coding_path(path):
            return None
        if path not in _SENSITIVE_INTEGRATION_PATHS and _SENSITIVE_CHAT_PATH_RE.match(path) is None:
            return None
        origin = self.headers.get("Origin", "")
        if not _is_allowed_sensitive_origin(origin):
            return (403, "origin not allowed for sensitive integration route", "ORIGIN_DENIED")
        expected = _configured_local_auth_token()
        provided = _bearer_token(self.headers)
        if not expected:
            return (403, "local auth token is not configured", "AUTH_REQUIRED")
        if not provided or not hmac.compare_digest(provided, expected):
            return (401, "local auth token required", "AUTH_REQUIRED")
        if method.upper() in {"POST", "PUT", "DELETE"} and origin and not self.headers.get("X-Rumi-CSRF", "").strip():
            return (403, "CSRF header required for sensitive integration mutation", "CSRF_REQUIRED")
        return None

    def _send_cors_headers(self):
        path = self.path.split("?")[0]
        if _is_sensitive_http_path(path):
            origin = self.headers.get("Origin", "")
            if _is_allowed_sensitive_origin(origin):
                if origin:
                    self.send_header("Access-Control-Allow-Origin", origin)
                    self.send_header("Vary", "Origin")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Rumi-CSRF, X-Rumi-Approval")
            return
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")

    def log_message(self, format, *args):
        pass


def _wait_for_signal():
    """Block the main thread until interrupted (cross-platform)."""
    try:
        while True:
            signal.pause()
    except AttributeError:
        # Windows does not have signal.pause(); poll instead.
        import time
        while True:
            time.sleep(86400)


def start_http_server(facade):
    """Start the HTTP transport and block until interrupted.

    The kernel's app.py calls ``http_server(facade)`` and then returns from
    ``main()``.  If we don't block here the process exits immediately because
    there would be no non-daemon threads keeping it alive.

    Strategy:
      * The server thread is started as **non-daemon** so the process stays
        alive even if main() returns without blocking.
      * We additionally call ``_wait_for_signal()`` so that Ctrl-C is caught
        cleanly and the server is shut down in an orderly fashion.
    """
    server = DefaultsHttpServer(facade)
    server.start()
    try:
        _wait_for_signal()
    except KeyboardInterrupt:
        print("\n[defaults] Shutting down HTTP server...")
    finally:
        server.stop()
    return server
