import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from blocks._common import ok, error, not_implemented, timestamp, gen_id

import json
import importlib


_ROUTE_MAP = [
    ("POST", "/v1/chat/completions", "blocks.chat.send"),
    ("POST", "/api/chat/conversations", "blocks.chat.create_conversation"),
    ("GET", "/api/chat/conversations", "blocks.chat.list_conversations"),
    ("GET", "/api/chat/conversations/{id}", "blocks.chat.get_conversation"),
    ("PUT", "/api/chat/conversations/{id}", "blocks.chat.update_conversation"),
    ("DELETE", "/api/chat/conversations/{id}", "blocks.chat.delete_conversation"),
    ("POST", "/api/chat/conversations/{id}/messages", "blocks.chat.send"),
    ("POST", "/api/chat/conversations/{id}/stream", "blocks.chat.stream"),
    ("POST", "/api/chat/conversations/{id}/export", "blocks.chat.export_conversation"),
    ("POST", "/api/agent/execute", "blocks.agent.execute"),
    ("POST", "/api/agent/{id}/approve", "blocks.agent.approve"),
    ("POST", "/api/agent/{id}/reject", "blocks.agent.reject"),
    ("POST", "/api/agent/{id}/cancel", "blocks.agent.cancel"),
    ("GET", "/api/agent/{id}/status", "blocks.agent.status"),
    ("GET", "/api/health", None),
    ("GET", "/api/context", None),
]

_ID_INJECT_MAP = {
    "/api/chat/conversations/{id}": ("conversation_id", "id"),
    "/api/chat/conversations/{id}/messages": ("conversation_id", "id"),
    "/api/chat/conversations/{id}/stream": ("conversation_id", "id"),
    "/api/chat/conversations/{id}/export": ("conversation_id", "id"),
    "/api/agent/{id}/approve": ("execution_id", "id"),
    "/api/agent/{id}/reject": ("execution_id", "id"),
    "/api/agent/{id}/cancel": ("execution_id", "id"),
    "/api/agent/{id}/status": ("execution_id", "id"),
}


def _match_route(method, path):
    import re
    for route_method, pattern, module_name in _ROUTE_MAP:
        if route_method != method:
            continue
        regex = re.sub(r"\{(\w+)\}", r"(?P<\1>[^/]+)", pattern)
        regex = "^" + regex + "$"
        m = re.match(regex, path)
        if m is not None:
            return pattern, module_name, m.groupdict()
    return None, None, {}


class DefaultsStdioTransport:
    def __init__(self):
        self._running = False

    def start(self):
        self._running = True
        while self._running:
            line = sys.stdin.readline()
            if not line:
                break
            line = line.strip()
            if not line:
                continue
            try:
                request = json.loads(line)
            except json.JSONDecodeError:
                self._send_error("Invalid JSON")
                continue
            result = self._handle_request(request)
            self._send_response(result)

    def stop(self):
        self._running = False

    def _handle_request(self, request):
        method = request.get("method", "GET").upper()
        path = request.get("path", "")
        data = request.get("data", {})

        pattern, module_name, path_params = _match_route(method, path)

        if pattern is None:
            return error("not found: " + method + " " + path)

        if pattern == "/api/health" and module_name is None:
            return ok({"status": "healthy", "pack": "defaultspack", "ts": timestamp()})

        if pattern == "/api/context" and module_name is None:
            return ok({"pack": "defaultspack", "ts": timestamp()})

        if pattern in _ID_INJECT_MAP:
            field_name, param_name = _ID_INJECT_MAP[pattern]
            data[field_name] = path_params.get(param_name, "")

        try:
            mod = importlib.import_module(module_name)
            handler_run = getattr(mod, "run")
        except (ImportError, AttributeError) as exc:
            return error("handler not available: " + str(exc))

        context = self._build_context()
        try:
            return handler_run(data, context)
        except Exception as exc:
            return error("handler error: " + str(exc))

    def _send_response(self, data):
        line = json.dumps(data, ensure_ascii=False) + "\n"
        sys.stdout.write(line)
        sys.stdout.flush()

    def _send_error(self, message):
        self._send_response(error(message))

    def _build_context(self):
        return {
            "flow_id": "stdio_direct",
            "step_id": "stdio_request",
            "phase": "execute",
            "ts": timestamp(),
            "owner_pack": "defaultspack",
            "inputs": {},
        }
