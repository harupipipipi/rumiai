from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

_PACK_ROOT = Path(__file__).resolve().parents[2]
_DEFAULTSPACK_ROOT = _PACK_ROOT.parent / "defaultspack"
for _path in (str(_PACK_ROOT), str(_DEFAULTSPACK_ROOT)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from domain.chat.store import ChatStore
from domain.input import RumiInputEnvelope, dispatch_input


class SubagentController:
    """Create a child conversation and run a bounded subagent turn."""

    def run(self, arguments: dict[str, Any] | None = None, context: dict[str, Any] | None = None) -> dict[str, Any]:
        arguments = arguments or {}
        context = context or {}
        parent_id = str(context.get("conversation_id") or arguments.get("parent_conversation_id") or "").strip()
        if not parent_id:
            raise ValueError("parent conversation is required for subagent")

        task = str(arguments.get("task") or arguments.get("prompt") or "").strip()
        if not task:
            raise ValueError("'task' is required for subagent")

        store = ChatStore()
        parent = store.get_conversation(parent_id)
        if parent is None:
            raise ValueError("parent conversation not found")

        model = str(arguments.get("model") or context.get("model") or parent.get("model") or "stub/default")
        title = str(arguments.get("title") or task[:48] or "Subagent").strip()
        agent_id = str(arguments.get("agent_id") or "subagent")
        child = store.create_conversation(
            model=model,
            parent_conversation_id=parent_id,
            conversation_kind="subagent",
            agent_id=agent_id,
            tags=[*list(parent.get("tags", [])), "subagent"],
            metadata={
                "parent_conversation_id": parent_id,
                "subagent": {
                    "task": task,
                    "source": "subagent_tool",
                },
            },
        )
        parent_workspace = store.conversation_workspace_dir(parent_id).resolve()
        child_workspace = store.conversation_workspace_dir(child["id"]).resolve()
        child_workspace.mkdir(parents=True, exist_ok=True)
        workspace_contract = {
            "contract_version": "rumi.agent_workspace.v1",
            "mode": "child_conversation_workspace",
            "isolation": "per_child_conversation",
            "write_scope": "child_workspace_root",
            "agent_id": agent_id,
            "parent_conversation_id": parent_id,
            "child_conversation_id": child["id"],
            "parent_workspace_root": str(parent_workspace),
            "workspace_root": str(child_workspace),
            "worktree": {
                "mode": str(arguments.get("worktree_mode") or context.get("worktree_mode") or "metadata_only"),
                "path": str(child_workspace),
            },
        }
        child_metadata = dict(child.get("metadata") or {})
        subagent_metadata = dict(child_metadata.get("subagent") or {})
        subagent_metadata["workspace"] = workspace_contract
        child_metadata["subagent"] = subagent_metadata
        child_metadata["workspace"] = workspace_contract
        child = store.update_conversation(child["id"], {"metadata": child_metadata}) or child
        child = store.update_conversation(child["id"], {"title": title}) or child
        params = dict(arguments.get("params") if isinstance(arguments.get("params"), dict) else {})
        if "tool_policy" not in params and isinstance(context.get("profile_policy"), dict):
            params["tool_policy"] = dict(context.get("profile_policy") or {})
        inherited_tools = list(arguments.get("tools") if isinstance(arguments.get("tools"), list) else self._connected_tools(context))
        message_metadata = {"source": "subagent_tool"}
        if isinstance(context.get("profile_id"), str) and context.get("profile_id").strip():
            message_metadata["profile_id"] = context.get("profile_id").strip()
        if agent_id:
            message_metadata["agent_id"] = agent_id
        result = dispatch_input(
            RumiInputEnvelope(
                role="user",
                input=task,
                chat={"conversation_id": child["id"], "title": title, "model": model},
                source={"kind": "internal", "provider": "subagent", "event_id": "subagent:" + child["id"]},
                target={
                    "conversation_id": child["id"],
                    "direct": True,
                    "model_route": {"preferred_model": model},
                },
                delivery={"action_id": "chat.message"},
                metadata=message_metadata,
                params=params,
                tools=inherited_tools,
            ),
            {**context, "chat_history_mode": "current_turn"},
        )
        if result.get("status") != "ok":
            raise RuntimeError(str(result.get("error") or "failed to dispatch subagent conversation"))
        summary = str(result.get("assistant_text") or "Subagent completed.").strip()
        return {
            "action": "subagent.run",
            "parent_conversation_id": parent_id,
            "child_conversation_id": child["id"],
            "title": title,
            "task": task,
            "summary": summary,
            "workspace": workspace_contract,
        }

    @staticmethod
    def _connected_tools(context: dict[str, Any]) -> list[str]:
        graph = context.get("capability_graph") if isinstance(context.get("capability_graph"), dict) else {}
        connected = graph.get("connected_tools") if isinstance(graph.get("connected_tools"), list) else []
        return [str(item).strip() for item in connected if isinstance(item, str) and str(item).strip()]
