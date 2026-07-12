import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from blocks._common import ok, error, gen_id, timestamp

from domain.chat.store import ChatStore


def _active_profile_prompt_id() -> str | None:
    try:
        from core_runtime.profile_paths import active_profile_id
        from core_runtime.profile_runtime_selection import apply_profile_graph_selection
        from core_runtime.profile_workspace import ProfileWorkspaceManager
    except Exception:
        return None

    try:
        profile_id = str(active_profile_id() or "").strip()
    except Exception:
        return None
    if not profile_id:
        return None

    try:
        profile = ProfileWorkspaceManager().load_profile_yaml(profile_id)
    except Exception:
        return None
    if not isinstance(profile, dict):
        return None
    try:
        profile = apply_profile_graph_selection(profile)
    except Exception:
        pass
    prompt_id = str(profile.get("system_prompt_id") or profile.get("default_prompt_id") or "").strip()
    return prompt_id or None


def run(input_data, context):
    store = ChatStore()
    model = input_data.get("model")
    system_prompt_id = input_data.get("system_prompt_id") or _active_profile_prompt_id()
    agent_id = input_data.get("agent_id")
    tags = input_data.get("tags")
    parent_conversation_id = input_data.get("parent_conversation_id")
    conversation_kind = input_data.get("conversation_kind")
    metadata = input_data.get("metadata")
    group_id = input_data.get("group_id")
    conv = store.create_conversation(
        model=model,
        system_prompt_id=system_prompt_id,
        agent_id=agent_id,
        tags=tags,
        parent_conversation_id=parent_conversation_id,
        conversation_kind=conversation_kind,
        metadata=metadata,
        group_id=group_id,
    )
    return ok(conv)
