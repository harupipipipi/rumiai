from __future__ import annotations

import subprocess
import sys
import importlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(DEFAULTSPACK_ROOT))


class _RouteRegistry:
    def __init__(self):
        self.routes = []

    def register(self, key, value, meta=None):
        if key == "io.http.route":
            self.routes.append(value)

    def get(self, *args, **kwargs):
        return None

    def get_interface(self, key, strategy=None):
        if key == "io.http.route":
            return self.routes
        return None


def _collect_defaultspack_routes():
    registry = _RouteRegistry()
    ecosystem = json.loads((DEFAULTSPACK_ROOT / "ecosystem.json").read_text(encoding="utf-8"))
    for entry in ecosystem["load_order"]:
        _, component_id = entry.split(":", 1)
        component = ecosystem["components"][component_id]
        module_name = component["path"].replace("/", ".") + ".setup"
        try:
            setup = importlib.import_module(module_name)
        except ModuleNotFoundError:
            continue
        setup.run({"interface_registry": registry, "_source_component": entry})
    return registry


def test_capability_catalog_loads_plan_manifest():
    from domain.capability.catalog import CapabilityCatalog

    catalog = CapabilityCatalog(DEFAULTSPACK_ROOT)
    manifest = catalog.manifest()

    assert manifest["local_first"] is True
    assert manifest["core_requires_api_key"] is False
    assert manifest["default_profile"] == "defaultspack.local_agent"
    assert manifest["counts"]["capabilities"] >= 11
    assert manifest["counts"]["profiles"] >= 5
    capability_ids = {item["id"] for item in manifest["capabilities"]}
    assert {"local_file", "terminal", "git", "safety", "artifact", "compact", "research"} <= capability_ids


def test_chat_store_persists_conversations_to_user_data(tmp_path, monkeypatch):
    from domain.chat.store import ChatStore

    storage_path = tmp_path / "user_data" / "shared" / "chat" / "conversations.json"
    monkeypatch.setenv("RUMI_DEFAULTSPACK_CHAT_STORE_PATH", str(storage_path))
    ChatStore._instance = None


def test_model_profiles_expose_required_context_and_thinking_metadata():
    from ecosystem.defaultspack.backend.ai_client.provider_catalog import list_profile_catalog

    profiles = list_profile_catalog()
    by_id = {profile["profile_id"]: profile for profile in profiles}

    assert by_id["stub/default"]["max_context"] == -1
    assert isinstance(by_id["openrouter/tencent/hy3-preview:free"]["max_context"], int)
    assert "supports_thinking" in by_id["openrouter/tencent/hy3-preview:free"]
    assert isinstance(by_id["openai/gpt-5.4"]["thinking_levels"], list)


def test_chat_send_attaches_tools_and_persists_activity_events(tmp_path, monkeypatch):
    from domain.chat.store import ChatStore
    from blocks.chat.send import run

    storage_path = tmp_path / "user_data" / "shared" / "chat" / "conversations.json"
    monkeypatch.setenv("RUMI_DEFAULTSPACK_CHAT_STORE_PATH", str(storage_path))
    ChatStore._instance = None

    store = ChatStore()
    conversation = store.create_conversation(model="stub/default")
    result = run(
        {
            "conversation_id": conversation["id"],
            "message": {"role": "user", "content": "hello with tools"},
            "params": {"thinking_level": "medium"},
        },
        {},
    )

    assert result["status"] == "ok"
    assistant = result["data"]
    assert assistant["metadata"]["model"] == "stub/default"
    assert assistant["metadata"]["attached_tool_count"] >= 1
    assert assistant["metadata"]["thinking_level"] == "medium"
    assert any(event["phase"] == "tools_attached" for event in assistant["events"])

    persisted = json.loads(storage_path.read_text(encoding="utf-8"))
    stored_assistant = persisted["conversations"][conversation["id"]]["messages"][-1]
    assert stored_assistant["metadata"]["attached_tool_count"] == assistant["metadata"]["attached_tool_count"]
    ChatStore._instance = None

    store = ChatStore()
    conversation = store.create_conversation(tags=["persisted"])
    message = store.add_message(
        conversation["id"],
        {"role": "user", "content": [{"type": "text", "text": "hello persistence"}]},
    )

    assert storage_path.is_file()
    payload = json.loads(storage_path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == 1
    assert conversation["id"] in payload["conversations"]
    assert payload["conversations"][conversation["id"]]["messages"][0]["id"] == message["id"]

    ChatStore._instance = None
    reloaded = ChatStore()
    assert reloaded.get_conversation(conversation["id"])["messages"][0]["raw_text"] == "hello persistence"
    ChatStore._instance = None


def test_chat_send_persists_user_attachment_metadata(tmp_path, monkeypatch):
    from domain.chat.store import ChatStore
    from blocks.chat.send import run

    storage_path = tmp_path / "user_data" / "shared" / "chat" / "conversations.json"
    monkeypatch.setenv("RUMI_DEFAULTSPACK_CHAT_STORE_PATH", str(storage_path))
    ChatStore._instance = None

    store = ChatStore()
    conversation = store.create_conversation(model="stub/default")
    result = run(
        {
            "conversation_id": conversation["id"],
            "message": {
                "role": "user",
                "content": "hello\n\n添付ファイル: notes.txt",
                "attachments": [{"name": "notes.txt", "content": "body", "size": 4}],
                "metadata": {"selected_tools": ["local_file"]},
            },
            "tools": ["local_file"],
            "params": {"tool_policy": {"selected_tools": ["local_file"]}},
        },
        {},
    )

    assert result["status"] == "ok"
    persisted = json.loads(storage_path.read_text(encoding="utf-8"))
    stored_user = persisted["conversations"][conversation["id"]]["messages"][0]
    assert stored_user["metadata"]["attachments"][0]["name"] == "notes.txt"
    assert stored_user["metadata"]["selected_tools"] == ["local_file"]
    ChatStore._instance = None


def test_coding_context_and_branch_blocks(tmp_path):
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True, text=True)
    (tmp_path / "README.md").write_text("# test\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=tmp_path, check=True, capture_output=True, text=True)
    subprocess.run(
        ["git", "-c", "user.email=test@example.com", "-c", "user.name=Test", "commit", "-m", "init"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    )

    from blocks.coding.context import run as context_run
    from blocks.coding.git_branch import run as branch_run

    context_result = context_run({"workspace_root": str(tmp_path)}, {})
    assert context_result["status"] == "ok"
    data = context_result["data"]
    assert data["branch"] in {"main", "master"}
    assert data["root_folder"] == str(tmp_path)
    assert data["files"] == ["README.md"]
    assert all(isinstance(item, str) for item in data["files"])
    assert any(item["name"] == "README.md" for item in data["entries"])
    assert data["git"]["branch"] == data["branch"]

    branch_result = branch_run({"workspace_root": str(tmp_path)}, {})
    assert branch_result["status"] == "ok"
    assert branch_result["data"]["branch"] in {"main", "master"}


def test_direct_chat_completion_forwards_tools_and_tool_context(monkeypatch):
    import blocks.chat.send as send

    captured = {}

    class DummyClient:
        def resolve_provider(self, model):
            return object(), model

        def complete(self, model, messages, tools=None, params=None):
            captured["model"] = model
            captured["messages"] = messages
            captured["tools"] = tools
            captured["params"] = params
            return {
                "content": [{"type": "text", "text": "ok"}],
                "finish_reason": "stop",
                "usage": {},
            }

    monkeypatch.setattr(send, "AIClient", DummyClient)

    tools = [
        {
            "type": "function",
            "function": {
                "name": "calculator",
                "description": "Evaluate arithmetic.",
                "parameters": {"type": "object", "properties": {}},
            },
        }
    ]
    response = send._complete_with_tools(
        "openrouter/test-model",
        [{"role": "user", "content": "2+2"}],
        tools,
        {},
        None,
        {"temperature": 0},
    )

    assert captured["tools"] == tools
    assert captured["params"]["temperature"] == 0
    assert "calculator" in captured["messages"][0]["content"]
    assert response["metadata"]["attached_tools"] == ["calculator"]


def test_chat_tool_loop_replays_openai_tool_call_messages():
    import blocks.chat.send as send

    seen_messages = []

    def call_handler(name, payload):
        if name == "defaults.ai.complete":
            seen_messages.append(payload["messages"])
            if len(seen_messages) == 1:
                return {
                    "status": "ok",
                    "data": {
                        "content": [
                            {
                                "type": "tool_use",
                                "id": "call_1",
                                "name": "calculator",
                                "input": "{\"expression\":\"2+2\"}",
                            }
                        ],
                        "finish_reason": "tool_calls",
                    },
                }
            return {
                "status": "ok",
                "data": {
                    "content": [{"type": "text", "text": "tool result used"}],
                    "finish_reason": "stop",
                },
            }
        if name == "defaults.tool.invoke":
            return {"status": "ok", "data": {"result": "4"}}
        raise AssertionError(name)

    response = send._complete_with_tools(
        "openrouter/test-model",
        [{"role": "user", "content": "2+2"}],
        [{"type": "function", "function": {"name": "calculator", "parameters": {"type": "object"}}}],
        {},
        call_handler,
        {"max_tool_calls": 3},
    )

    assert response["content"][0]["text"] == "tool result used"
    assert seen_messages[1][-2]["role"] == "assistant"
    assert seen_messages[1][-2]["tool_calls"][0]["function"]["name"] == "calculator"
    assert seen_messages[1][-1]["role"] == "tool"
    assert seen_messages[1][-1]["tool_call_id"] == "call_1"


def test_builtin_calculator_returns_real_arithmetic_result():
    from domain.tool.executor import ToolExecutor

    result = ToolExecutor().execute("calculator", {"expression": "2 + 2 * 3"}, {})

    assert result["is_error"] is False
    assert result["result"] == "Calculated: 2 + 2 * 3 = 8"


def test_coding_tools_are_exposed_through_tool_registry():
    from domain.tool.registry import ToolRegistry

    ToolRegistry._instance = None
    registry = ToolRegistry()
    names = {tool["tool_id"] for tool in registry.list_tools()}

    assert {
        "coding_file_read",
        "coding_file_write",
        "coding_file_patch",
        "coding_terminal_exec",
        "coding_git_status",
    } <= names


def test_tool_executor_dispatches_coding_handler_with_yolo_policy(tmp_path, monkeypatch):
    from domain.tool.executor import ToolExecutor
    from domain.tool.registry import ToolRegistry

    ToolRegistry._instance = None
    monkeypatch.chdir(tmp_path)
    result = ToolExecutor().execute(
        "coding_file_create",
        {"path": "created.txt", "content": "hello"},
        {"profile_policy": {"yolo_mode": True}},
    )

    assert result["is_error"] is False
    assert json.loads(result["result"])["created"] is True
    assert (tmp_path / "created.txt").read_text(encoding="utf-8") == "hello"

    ToolRegistry._instance = None
    approval = ToolExecutor().execute(
        "coding_file_write",
        {"path": "needs-approval.txt", "content": "blocked"},
        {},
    )

    assert approval["is_error"] is False
    assert approval["widget"]["approval_required"] is True
    assert not (tmp_path / "needs-approval.txt").exists()


def test_coding_handlers_do_not_trust_body_approved_flag(tmp_path, monkeypatch):
    from blocks.coding.file_write import run as file_write_run
    from blocks.coding.terminal_exec import run as terminal_exec_run

    monkeypatch.chdir(tmp_path)

    write = file_write_run({"path": "pwned.txt", "content": "blocked", "approved": True}, {})
    assert write["status"] == "ok"
    assert write["data"]["approval_required"] is True
    assert not (tmp_path / "pwned.txt").exists()

    command = "python3 -c 'open(\"terminal-pwned.txt\", \"w\").write(\"blocked\")'"
    terminal = terminal_exec_run({"command": command, "approved": True}, {})
    assert terminal["status"] == "ok"
    assert terminal["data"]["approval_required"] is True
    assert terminal["data"]["exit_code"] is None
    assert not (tmp_path / "terminal-pwned.txt").exists()


def test_coding_handlers_accept_only_server_approval_context(tmp_path, monkeypatch):
    from blocks.coding.file_write import run as file_write_run

    monkeypatch.chdir(tmp_path)

    result = file_write_run(
        {"path": "approved.txt", "content": "ok"},
        {"_tool_server_approved": True},
    )

    assert result["status"] == "ok"
    assert result["data"]["written"] is True
    assert (tmp_path / "approved.txt").read_text(encoding="utf-8") == "ok"


def test_direct_coding_route_cannot_execute_with_forged_approved(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    registry = _collect_defaultspack_routes()
    route = next(
        item
        for item in registry.routes
        if item["method"] == "POST" and item["pattern"] == "/api/coding/files/write"
    )

    result = route["handler"](
        {"path": "direct-pwned.txt", "content": "blocked", "approved": True},
        {"flow_id": "transport_direct"},
    )

    assert result["status"] == "ok"
    assert result["data"]["approval_required"] is True
    assert not (tmp_path / "direct-pwned.txt").exists()


def test_sensitive_coding_routes_do_not_use_wildcard_cors():
    from ecosystem.defaultspack.transport.http import _is_sensitive_coding_path

    assert _is_sensitive_coding_path("/api/coding/terminal/exec") is True
    assert _is_sensitive_coding_path("/api/coding/files/write") is True
    assert _is_sensitive_coding_path("/api/coding/files/read") is False


def test_fallback_routes_expose_agent_service_and_coding_surfaces():
    from ecosystem.defaultspack.transport.registry import _FALLBACK_HTTP_ROUTE_SPECS

    routes = {(spec.method, spec.pattern, spec.block_module) for spec in _FALLBACK_HTTP_ROUTE_SPECS}

    assert ("GET", "/api/capabilities", "blocks.capability.list") in routes
    assert ("GET", "/api/agent-service/manifest", "blocks.capability.manifest") in routes
    assert ("GET", "/api/coding/context", "blocks.coding.context") in routes
    assert ("GET", "/api/coding/files", "blocks.coding.file_list") in routes
    assert ("GET", "/api/coding/git/branch", "blocks.coding.git_branch") in routes
    assert ("POST", "/api/coding/git/branch", "blocks.coding.git_branch") in routes
    assert ("POST", "/api/coding/files/diff", "blocks.coding.file_diff") in routes
    assert ("POST", "/api/coding/terminal/exec", "blocks.coding.terminal_exec") in routes
    assert ("POST", "/api/context/compact", "blocks.context.compact") in routes
    assert ("POST", "/api/artifacts", "blocks.artifact.create") in routes
    assert ("POST", "/api/research/local-search", "blocks.research.local_search") in routes
    assert ("POST", "/api/research/web-search", "blocks.research.web_search") in routes
    assert ("POST", "/api/research/reddit-search", "blocks.research.reddit_search") in routes
    assert ("POST", "/api/tools/browser-computer", "blocks.tool.browser_computer") in routes
    assert ("GET", "/api/ai/profiles", "blocks.ai.profiles") in routes
    assert ("GET", "/api/agent/schedules", "blocks.agent.scheduler.list") in routes
    assert ("GET", "/api/chat/channels", "blocks.chat.channel.list") in routes
    assert ("POST", "/api/share", "blocks.share.create") in routes


def test_transport_direct_routes_json_has_interface_registry_parity():
    ecosystem_routes = json.loads((DEFAULTSPACK_ROOT / "routes.json").read_text(encoding="utf-8"))["routes"]
    contract_routes = {
        (route["method"], route["path"])
        for route in ecosystem_routes
        if route.get("flow_id") == "transport_direct"
    }
    registry = _collect_defaultspack_routes()
    registered_routes = {(route["method"], route["pattern"]) for route in registry.routes}

    assert contract_routes <= registered_routes


def test_frontend_sidebar_api_routes_match_in_registry_mode():
    from ecosystem.defaultspack.transport.http import DefaultsHttpServer

    registry = _collect_defaultspack_routes()

    class Facade:
        def get_interface(self, key, strategy=None):
            return registry.get_interface(key, strategy=strategy)

    server = DefaultsHttpServer(Facade())
    expected = [
        ("GET", "/api/artifacts"),
        ("POST", "/api/share"),
        ("POST", "/api/tools/browser-computer"),
        ("POST", "/api/research/web-search"),
        ("POST", "/api/research/reddit-search"),
        ("GET", "/api/coding/context"),
        ("GET", "/api/coding/files"),
        ("GET", "/api/coding/git/branch"),
        ("GET", "/api/ai/profiles"),
        ("GET", "/api/agent/schedules"),
        ("GET", "/api/chat/channels"),
        ("GET", "/api/capabilities/local_file"),
    ]

    for method, path in expected:
        handler, _, source, _ = server._match_route(method, path)
        assert handler is not None, (method, path)
        assert source == "registry"


def test_research_providers_use_shared_source_schema():
    from domain.research.providers import ExternalWebProvider, RedditProvider

    html = '<html><title>Example</title><a class="result__a" href="https://example.test">Example</a><div class="result__snippet">Snippet</div></html>'
    web = ExternalWebProvider(fetcher=lambda url, timeout: html)
    web_result = web.search("example", allow_network=True)

    assert web_result.sources[0]["type"] == "external_web"
    assert web_result.sources[0]["provider"] == "external_web"
    assert web.search("example", allow_network=False).network_enabled is False

    reddit_payload = '{"data":{"children":[{"data":{"id":"abc","title":"Hello","permalink":"/r/test/comments/abc/hello","subreddit":"test","score":3,"num_comments":2,"selftext":"Body"}}]}}'
    reddit = RedditProvider(fetcher=lambda url, timeout: reddit_payload)
    reddit_result = reddit.search("hello", subreddit="test")

    assert reddit_result.sources[0]["type"] == "reddit_post"
    assert reddit_result.sources[0]["provider"] == "reddit"
    assert reddit.search("hello", allow_network=False).network_enabled is False


def test_external_web_provider_rejects_private_network_urls():
    from domain.research.providers import ExternalWebProvider

    result = ExternalWebProvider().search("http://127.0.0.1:8766/private", allow_network=True)

    assert result.sources == []
    assert "non-public" in result.summary


def test_browser_computer_controller_gates_desktop_actions():
    from domain.tool.browser_computer import BrowserComputerController

    controller = BrowserComputerController()

    assert controller.run("browser.session")["action"] == "browser.session"
    assert controller.run("browser.open_url", {"url": "https://example.test", "dry_run": True})["dry_run"] is True
    assert controller.run("computer.screenshot", {"dry_run": True})["requires_approval"] is False
    approval = controller.run("computer.click", {"x": 1, "y": 2})
    assert approval["requires_approval"] is True
    assert approval["approval_token"]
    assert controller.run("computer.click", {"x": 1, "y": 2, "approved": True})["requires_approval"] is True


def test_capability_detail_endpoint_returns_one_manifest_and_404_for_unknown():
    from blocks.capability.manifest import run

    result = run({"capability_id": "local_file"})
    assert result["status"] == "ok"
    assert result["data"]["id"] == "local_file"

    missing = run({"capability_id": "missing-capability"})
    assert missing["status"] == "error"
    assert missing["error"]["code"] == "NOT_FOUND"
    assert missing["_http_status"] == 404


def test_share_store_creates_lists_and_revokes_local_links(tmp_path):
    from domain.share.store import ShareStore

    store = ShareStore(tmp_path)
    record = store.create({"target_type": "conversation", "target_id": "c1", "content": "hello"})

    assert record["share_url"].startswith("/api/share/")
    assert store.get(record["token"])["content"] == "hello"
    assert len(store.list()) == 1
    assert store.revoke(record["token"]) is True
    assert store.get(record["token"]) is None


def test_file_ops_diff_patch_snapshot_restore(tmp_path):
    from domain.coding.file_ops import FileOps

    ops = FileOps(tmp_path)
    ops.create_file("notes/example.txt", "hello world\n")

    diff = ops.diff_text("notes/example.txt", "hello rumi\n")
    assert "hello world" in diff
    assert "hello rumi" in diff

    patch = ops.apply_patch_text("notes/example.txt", "world", "rumi")
    assert patch["patched"] is True
    assert ops.read_file("notes/example.txt") == "hello rumi\n"

    snapshot = ops.snapshot(["notes/example.txt"])
    ops.write_file("notes/example.txt", "changed\n")
    restored = ops.restore_snapshot(snapshot["snapshot_id"], ["notes/example.txt"])
    assert restored["restored"] == ["notes/example.txt"]
    assert ops.read_file("notes/example.txt") == "hello rumi\n"


def test_terminal_exec_requires_approval_for_medium_risk_and_runs_read_only(tmp_path):
    from domain.coding.terminal import Terminal

    terminal = Terminal(tmp_path)

    read_only = terminal.execute("pwd", approved=False)
    assert read_only["exit_code"] == 0
    assert read_only["risk"]["risk_level"] == "low"

    medium = terminal.execute("python3 -c 'print(42)'", approved=False)
    assert medium["approval_required"] is True
    assert medium["exit_code"] is None

    approved = terminal.execute("python3 -c 'print(42)'", approved=True)
    assert approved["exit_code"] == 0
    assert approved["stdout"].strip() == "42"


def test_git_ops_returns_real_status_and_diff(tmp_path):
    from domain.coding.git_ops import GitOps

    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.test"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=tmp_path, check=True)
    (tmp_path / "file.txt").write_text("one\n", encoding="utf-8")
    subprocess.run(["git", "add", "file.txt"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-m", "initial"], cwd=tmp_path, check=True, capture_output=True)
    (tmp_path / "file.txt").write_text("two\n", encoding="utf-8")

    git = GitOps(tmp_path)
    status = git.status()
    diff = git.diff()

    assert status["clean"] is False
    assert "file.txt" in status["modified"]
    assert "-one" in diff["diff"]
    assert "+two" in diff["diff"]


def test_artifact_store_is_local_and_versioned(tmp_path):
    from domain.artifact.store import ArtifactStore

    pack_root = tmp_path / "defaultspack"
    store = ArtifactStore(pack_root)
    artifact = store.create("markdown", "Plan", "# Plan\n", path="plans/plan.md", source_task="test")

    assert artifact["version"] == 1
    assert artifact["content_ref"] == "user_data/artifacts/plans/plan.md"
    assert store.list()[0]["artifact_id"] == artifact["artifact_id"]
    assert store.get(artifact["artifact_id"])["content"] == "# Plan\n"

    try:
        store.create("markdown", "Escape", "nope", path="../escape.md")
    except ValueError as exc:
        assert "escapes artifact root" in str(exc)
    else:
        raise AssertionError("artifact store allowed path traversal")
