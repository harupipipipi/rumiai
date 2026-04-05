"""Integration tests for all backend modules."""
import sys, os, tempfile, json, csv
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from ecosystem.defaultspack.backend.ai_client import AIClientManager
from ecosystem.defaultspack.backend.ai_client.providers.stub_provider import StubProvider
from ecosystem.defaultspack.backend.ai_client.base_provider import CompletionRequest
from ecosystem.defaultspack.backend.ai_client.model_router import ModelRouter, RoutingRule
from ecosystem.defaultspack.backend.prompt import PromptManager, PromptEntry
from ecosystem.defaultspack.backend.tool import ToolManager, ToolEntry
from ecosystem.defaultspack.backend.plugin import PluginManager, PluginManifest
from ecosystem.defaultspack.backend.supporter import SupporterManager
from ecosystem.defaultspack.backend.memory import MemoryManager, MemoryEntry, MemoryType
from ecosystem.defaultspack.backend.knowledge import KnowledgeManager, KnowledgeEntry
from ecosystem.defaultspack.backend.chat import ChatManager, Message
from ecosystem.defaultspack.backend.agent import AgentManager, AgentRole, AgentTask
from ecosystem.defaultspack.backend.coding import CodingManager
from ecosystem.defaultspack.backend.sandbox import SandboxManager
from ecosystem.defaultspack.migration import MigrationManager


class TestAIClient:
    def test_register_provider(self):
        mgr = AIClientManager()
        mgr.register_provider(StubProvider())
        assert "stub" in mgr.list_providers()

    def test_complete(self):
        mgr = AIClientManager()
        mgr.register_provider(StubProvider())
        req = CompletionRequest(messages=[{"role": "user", "content": "hi"}])
        resp = mgr.complete(req)
        assert resp.content == "[stub response]"
        assert resp.finish_reason == "stop"

    def test_count_tokens(self):
        mgr = AIClientManager()
        mgr.register_provider(StubProvider())
        count = mgr.count_tokens("hello world test", provider_id="stub")
        assert count > 0

    def test_list_models(self):
        mgr = AIClientManager()
        mgr.register_provider(StubProvider())
        models = mgr.list_models()
        assert len(models) >= 1

    def test_model_router(self):
        router = ModelRouter()
        router.add_rule(RoutingRule(name="code", conditions={"task": "code"}, target_provider="fast", target_model="gpt-fast"))
        result = router.route({"task": "code"})
        assert result["provider_id"] == "fast"


class TestPrompt:
    def test_register_and_get(self):
        mgr = PromptManager()
        mgr.register(PromptEntry(prompt_id="p1", display_name="Test", system_prompt="Hello {name}"))
        assert mgr.get("p1") is not None

    def test_render(self):
        mgr = PromptManager()
        mgr.register(PromptEntry(prompt_id="p1", system_prompt="Hello {name}", variables={"name": "world"}))
        assert mgr.render("p1") == "Hello world"

    def test_mix(self):
        mgr = PromptManager()
        mgr.register(PromptEntry(prompt_id="p1", system_prompt="System A"))
        mgr.register(PromptEntry(prompt_id="p2", system_prompt="System B"))
        result = mgr.mix(["p1", "p2"])
        assert "System A" in result and "System B" in result

    def test_update_and_delete(self):
        mgr = PromptManager()
        mgr.register(PromptEntry(prompt_id="p1"))
        assert mgr.update("p1", display_name="Updated")
        assert mgr.get("p1").display_name == "Updated"
        assert mgr.delete("p1")
        assert mgr.get("p1") is None

    def test_metadata_index(self):
        mgr = PromptManager()
        mgr.register(PromptEntry(prompt_id="p1"))
        idx = mgr.get_metadata_index()
        assert len(idx) == 1


class TestTool:
    def test_register_and_invoke(self):
        mgr = ToolManager()
        mgr.register(ToolEntry(tool_id="t1", handler=lambda d: "ok"))
        result = mgr.invoke("t1")
        assert result["result"] == "ok"

    def test_enable_disable(self):
        mgr = ToolManager()
        mgr.register(ToolEntry(tool_id="t1", handler=lambda d: "ok"))
        mgr.disable("t1")
        result = mgr.invoke("t1")
        assert "error" in result
        mgr.enable("t1")
        result = mgr.invoke("t1")
        assert result["result"] == "ok"

    def test_consent_check(self):
        mgr = ToolManager()
        mgr.register(ToolEntry(tool_id="t1", requires_consent=True, consent_message="Sure?"))
        check = mgr.check_consent("t1")
        assert check["required"]

    def test_mcp(self):
        mgr = ToolManager()
        result = mgr.connect_mcp("http://localhost:3000", "test-mcp")
        assert result["status"] == "connected"
        assert len(mgr.list_mcp()) == 1
        assert mgr.disconnect_mcp("test-mcp")
        assert len(mgr.list_mcp()) == 0


class TestPlugin:
    def test_install_uninstall(self):
        mgr = PluginManager()
        result = mgr.install(PluginManifest(plugin_id="p1"))
        assert result["success"]
        assert mgr.get("p1") is not None
        result = mgr.uninstall("p1")
        assert result["success"]

    def test_dependency_check(self):
        mgr = PluginManager()
        result = mgr.install(PluginManifest(plugin_id="p2", dependencies=["p1"]))
        assert not result["success"]


class TestMemory:
    def test_store_and_recall(self):
        mgr = MemoryManager()
        mgr.store(MemoryEntry(memory_id="m1", memory_type=MemoryType.CONVERSATION, content="hello"))
        entry = mgr.recall(MemoryType.CONVERSATION, "m1")
        assert entry is not None
        assert entry.content == "hello"

    def test_hypothesis(self):
        mgr = MemoryManager()
        mgr.store_hypothesis(MemoryType.TYPO_TENDENCY, "t1", {"pattern": "teh -> the"}, 0.7)
        entry = mgr.recall(MemoryType.TYPO_TENDENCY, "t1")
        assert entry.is_hypothesis
        assert entry.confidence == 0.7

    def test_disable_entry(self):
        mgr = MemoryManager()
        mgr.store(MemoryEntry(memory_id="m1", memory_type=MemoryType.USER, content="data"))
        mgr.disable_entry(MemoryType.USER, "m1")
        assert mgr.recall(MemoryType.USER, "m1") is None

    def test_user_model(self):
        mgr = MemoryManager()
        mgr.store_hypothesis(MemoryType.WORK_TYPE, "w1", "developer")
        model = mgr.get_user_model()
        assert MemoryType.WORK_TYPE in model


class TestKnowledge:
    def test_crud(self):
        mgr = KnowledgeManager()
        mgr.create(KnowledgeEntry(knowledge_id="k1", title="Test", content="Hello"))
        assert mgr.get("k1") is not None
        mgr.update("k1", title="Updated")
        assert mgr.get("k1").title == "Updated"
        mgr.delete("k1")
        assert mgr.get("k1") is None

    def test_search(self):
        mgr = KnowledgeManager()
        mgr.create(KnowledgeEntry(knowledge_id="k1", title="Python Error", content="IndentationError fix", tags=["python"]))
        results = mgr.search("Python IndentationError")
        assert len(results) >= 1

    def test_error_solution(self):
        mgr = KnowledgeManager()
        kid = mgr.store_error_solution("ImportError: no module", "pip install missing")
        assert mgr.get(kid) is not None


class TestChat:
    def test_conversation_lifecycle(self):
        mgr = ChatManager()
        conv = mgr.create_conversation("Test Chat")
        assert conv.title == "Test Chat"
        mgr.add_message(conv.conversation_id, Message(role="user", content="hello"))
        history = mgr.get_history(conv.conversation_id)
        assert len(history) == 1

    def test_queue_message(self):
        mgr = ChatManager()
        conv = mgr.create_conversation()
        mgr.queue_message(conv.conversation_id, Message(role="user", content="queued"))
        msg = mgr.pop_queued(conv.conversation_id)
        assert msg is not None
        assert msg.content == "queued"

    def test_stream_control(self):
        mgr = ChatManager()
        conv = mgr.create_conversation()
        assert not mgr.is_streaming(conv.conversation_id)
        mgr.start_stream(conv.conversation_id)
        assert mgr.is_streaming(conv.conversation_id)
        mgr.stop_stream(conv.conversation_id)
        assert not mgr.is_streaming(conv.conversation_id)

    def test_compact_history(self):
        mgr = ChatManager()
        conv = mgr.create_conversation()
        for i in range(30):
            mgr.add_message(conv.conversation_id, Message(role="user", content=f"msg{i}"))
        removed = mgr.compact_history(conv.conversation_id, keep_last=10)
        assert removed == 20
        assert len(mgr.get_history(conv.conversation_id)) == 10


class TestAgent:
    def test_task_lifecycle(self):
        mgr = AgentManager()
        task = mgr.create_task("Do something", assigned_to="coder")
        assert task.status == "pending"
        mgr.update_task_status(task.task_id, "running")
        assert mgr.get_task(task.task_id).status == "running"

    def test_checkpoint_resume(self):
        mgr = AgentManager()
        task = mgr.create_task("Long task")
        mgr.checkpoint_task(task.task_id, {"step": 5, "data": "partial"})
        cp = mgr.resume_task(task.task_id)
        assert cp["step"] == 5

    def test_channel_messaging(self):
        mgr = AgentManager()
        ch = mgr.create_channel("dev-team", members=["alice", "bob"])
        mgr.send_to_channel(ch.channel_id, "alice", "Hello team!")
        msgs = mgr.get_channel_messages(ch.channel_id)
        assert len(msgs) == 1
        assert msgs[0]["sender"] == "alice"

    def test_escalation(self):
        mgr = AgentManager()
        task = mgr.create_task("Complex task")
        result = mgr.escalate_to_pm(task.task_id, "Too complex")
        assert result["escalated_to"] == "pm"

    def test_roles(self):
        mgr = AgentManager()
        mgr.register_role(AgentRole(role_id="coder", display_name="Coding Agent"))
        roles = mgr.list_roles()
        assert len(roles) == 1


class TestMigration:
    def test_csv_to_json(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False) as f:
            writer = csv.writer(f)
            writer.writerow(["name", "email"])
            writer.writerow(["Alice", "alice@test.com"])
            csv_path = f.name
        json_path = csv_path.replace('.csv', '.json')
        try:
            mgr = MigrationManager()
            result = mgr.migrate_user_csv_to_json(csv_path, json_path)
            assert result["success"]
            assert result["count"] == 1
            with open(json_path) as f:
                data = json.load(f)
            assert len(data["users"]) == 1
        finally:
            os.unlink(csv_path)
            if os.path.exists(json_path):
                os.unlink(json_path)

    def test_config_migration(self):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({"key": "value"}, f)
            old_path = f.name
        new_path = old_path.replace('.json', '_new.json')
        try:
            mgr = MigrationManager()
            result = mgr.migrate_old_config(old_path, new_path)
            assert result["success"]
            with open(new_path) as f:
                data = json.load(f)
            assert data["version"] == "2.0"
        finally:
            os.unlink(old_path)
            if os.path.exists(new_path):
                os.unlink(new_path)

    def test_deprecation_log(self):
        mgr = MigrationManager()
        mgr.log_deprecation("old_func", "new_func")
        log = mgr.get_deprecation_log()
        assert len(log) == 1
        assert log[0]["feature"] == "old_func"

    def test_rollback(self):
        mgr = MigrationManager()
        result = mgr.rollback()
        assert result["status"] == "rollback_available"
