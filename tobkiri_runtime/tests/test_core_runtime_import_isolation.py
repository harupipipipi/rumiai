from __future__ import annotations

import ast
import importlib
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
CORE_RUNTIME_ROOT = ROOT / "core_runtime"
FOCUSED_CORE_MODULES = (
    "core_runtime.prompt_builder",
    "core_runtime.chat_session_manager",
)


def _clear_modules(monkeypatch, *prefixes: str) -> None:
    for name in list(sys.modules):
        if any(name == prefix or name.startswith(f"{prefix}.") for prefix in prefixes):
            monkeypatch.delitem(sys.modules, name, raising=False)


def test_focused_core_modules_import_without_domain_package(monkeypatch, tmp_path):
    poison_domain = tmp_path / "domain"
    poison_domain.mkdir()
    (poison_domain / "__init__.py").write_text(
        "raise RuntimeError('core_runtime must not import pack-local domain')\n",
        encoding="utf-8",
    )

    monkeypatch.syspath_prepend(str(tmp_path))
    _clear_modules(monkeypatch, "domain", *FOCUSED_CORE_MODULES)

    for module_name in FOCUSED_CORE_MODULES:
        importlib.import_module(module_name)


def test_core_runtime_python_files_do_not_directly_import_domain():
    for module_path in sorted(CORE_RUNTIME_ROOT.rglob("*.py")):
        tree = ast.parse(module_path.read_text(encoding="utf-8"))

        domain_imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                domain_imports.extend(
                    alias.name
                    for alias in node.names
                    if alias.name == "domain" or alias.name.startswith("domain.")
                )
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if module == "domain" or module.startswith("domain."):
                    domain_imports.append(module)

        assert domain_imports == [], str(module_path.relative_to(ROOT))


def test_chat_session_manager_uses_injected_chat_store():
    from core_runtime.chat_session_manager import SessionManager

    class ChatStore:
        def get_conversation(self, conversation_id):
            if conversation_id == "conversation-1":
                return {"id": conversation_id}
            return None

    BoundSessionManager = SessionManager.with_dependencies(chat_store_factory=ChatStore)
    manager = BoundSessionManager()

    session = manager.create_session("test")
    updated = manager.add_conversation(session["id"], "conversation-1")

    assert updated["conversation_ids"] == ["conversation-1"]
    assert manager.list_conversations(session["id"]) == [{"id": "conversation-1"}]
