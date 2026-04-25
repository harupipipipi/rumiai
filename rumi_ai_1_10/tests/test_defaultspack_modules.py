from __future__ import annotations

from ecosystem.defaultspack.backend.ai_client.ai_profile import AIProfile, AIProfileManager
from ecosystem.defaultspack.backend.prompt.prompt_manager import PromptEntry, PromptManager
from ecosystem.defaultspack.backend.tool.tool_manager import ToolEntry, ToolManager
from ecosystem.defaultspack.backend.plugin.plugin_manager import PluginManager
from ecosystem.defaultspack.backend.chat.chat_manager import ChatManager, Message
from ecosystem.defaultspack.backend.memory.memory_manager import MemoryEntry, MemoryManager
from ecosystem.defaultspack.backend.knowledge.knowledge_manager import KnowledgeEntry, KnowledgeManager
from ecosystem.defaultspack.backend.agent.orchestrator import AgentOrchestrator
from ecosystem.defaultspack.backend.migration.migrator import DefaultsMigrator
from ecosystem.defaultspack.backend.frontend_support.layout_engine import LayoutConfig, LayoutEngine, PaneConfig
from ecosystem.defaultspack.backend.pack_extension.extension_manager import ExtensionManager, PatchMode
from ecosystem.defaultspack.backend.sandbox.gui_sandbox import GUISandbox
from ecosystem.defaultspack.frontend.dependency_manager import build_frontend_dependency_graph
from ecosystem.defaultspack.frontend.frontend_loader import (
    discover_frontend_modules,
    load_frontend_module,
)
from ecosystem.setup_pack.pack_selector import PackSelector


def test_ai_prompt_tool_plugin_and_more(tmp_path):
    prof_dir = tmp_path / "profiles"
    prompt_dir = tmp_path / "prompts"
    tool_dir = tmp_path / "tools"
    plugin_dir = tmp_path / "plugins"
    prof_dir.mkdir()
    prompt_dir.mkdir()
    tool_dir.mkdir()
    plugin_dir.mkdir()

    pm = AIProfileManager(prof_dir)
    pm.save(AIProfile(profile_id="p1", display_name="Profile 1", provider_id="x", model="m"))
    assert pm.get("p1") is not None

    prompts = PromptManager(prompt_dir)
    prompts.create(PromptEntry(prompt_id="pr1", display_name="Prompt 1", content="Hello {{name}}", variables={"name": "World"}))
    assert prompts.get("pr1").render() == "Hello World"

    tools = ToolManager(tool_dir)
    tools.create(ToolEntry(tool_id="t1", display_name="Tool 1"))
    assert tools.get("t1") is not None

    plugins = PluginManager(plugin_dir)
    src = tmp_path / "src_plugin"
    src.mkdir()
    (src / "manifest.json").write_text('{"plugin_id":"plug1"}', encoding="utf-8")
    assert plugins.install(src)

    chat = ChatManager()
    convo = chat.create_conversation("chat")
    chat.add_message(convo.chat_id, Message(role="user", content="hi"))
    assert chat.list_messages(convo.chat_id)

    memory = MemoryManager()
    memory.store(MemoryEntry(surface="conversation", key="topic", value="ai"))
    assert memory.recall("conversation", "topic")

    knowledge = KnowledgeManager()
    knowledge.create(KnowledgeEntry(title="t", content="c"))
    assert knowledge.retrieve_relevant("t")

    orch = AgentOrchestrator()
    task = orch.create_task("do work", "coding")
    orch.start_task(task.task_id)
    assert orch.get_task(task.task_id).status.value == "running"

    migrator = DefaultsMigrator(tmp_path / "old", tmp_path / "new")
    assert migrator.migrate_all()["success"]

    layout_dir = tmp_path / "layouts"
    layout = LayoutEngine(layout_dir)
    saved = layout.save(LayoutConfig(name="main", mode="coding", panes=[PaneConfig(component="sidebar")]))
    assert layout.load(saved.layout_id) is not None

    ex = ExtensionManager()
    req = ex.create_request(PatchMode.REQUEST_EXTENSION, "pack_a", "defaultspack", "extend")
    assert ex.approve(req.request_id)

    sand = GUISandbox()
    sess = sand.create_session("test")
    assert sand.click(sess.session_id, 1, 2)["ok"]


def test_setup_pack_selector(tmp_path):
    eco = tmp_path / "eco"
    eco.mkdir()
    setup_pack = eco / "setup_pack" / "defaultspack"
    setup_pack.mkdir(parents=True)
    (setup_pack / "pack.json").write_text(
        '{"pack_id":"defaultspack","target_pack_id":"defaultspack","supports_all_ok":true}',
        encoding="utf-8",
    )
    target = eco / "defaultspack"
    target.mkdir()
    (target / "ecosystem.json").write_text(
        '{"pack_identity":"rumi.defaults"}',
        encoding="utf-8",
    )
    selector = PackSelector(eco / "setup_pack")
    assert selector.scan_candidates()[0].all_ok_eligible


def test_frontend_loader_includes_ui_shell_root_module():
    assert "ui_shell" in discover_frontend_modules()
    assert "rumi_bundle" in discover_frontend_modules()
    loaded = load_frontend_module("ui_shell")
    assert loaded["loaded"]
    assert loaded["spec"]["module_id"] == "ui_shell"
    bundle = load_frontend_module("rumi_bundle")
    assert bundle["loaded"]
    assert bundle["spec"]["module_id"] == "rumi_bundle"
    assert bundle["spec"]["bundle"]["launch_mode"] == "desktop_app"
    assert bundle["spec"]["bundle"]["port_source"]["default"] == 8766
    assert "ui_shell" in build_frontend_dependency_graph()
    assert "rumi_bundle" in build_frontend_dependency_graph()
