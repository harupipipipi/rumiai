from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(relative_path: str, old: str, new: str) -> None:
    path = ROOT / relative_path
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{relative_path}: expected one replacement, found {count}: {old[:80]!r}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


replace_once(
    "rumi_ai_1_10/ecosystem/defaultspack/domain/chat/run_request.py",
    "from domain.chat.store import ChatStore\n",
    "from domain.chat.store import ChatStore\n"
    "from domain.chat.conversation_channel import (\n"
    "    conversation_channel,\n"
    "    conversation_channel_system_instruction,\n"
    "    runtime_conversation,\n"
    ")\n",
)

replace_once(
    "rumi_ai_1_10/ecosystem/defaultspack/domain/chat/run_request.py",
    '''    conversation = store.get_conversation(conversation_id)
    if conversation is None:
        raise ValueError("Conversation not found")
    conversation_metadata = conversation.get("metadata") if isinstance(conversation.get("metadata"), dict) else {}
''',
    '''    conversation = store.get_conversation(conversation_id)
    if conversation is None:
        raise ValueError("Conversation not found")
    conversation = runtime_conversation(store, conversation)
    conversation_metadata = conversation.get("metadata") if isinstance(conversation.get("metadata"), dict) else {}
''',
)

replace_once(
    "rumi_ai_1_10/ecosystem/defaultspack/domain/chat/run_request.py",
    '''    if effective_system_prompt:
        system_prompt = effective_system_prompt
        _replace_system_prompt_message(standard_messages, effective_system_prompt)
    temporal_context = current_datetime_context(request_context)
''',
    '''    if effective_system_prompt:
        system_prompt = effective_system_prompt
        _replace_system_prompt_message(standard_messages, effective_system_prompt)
    request_context["conversation_channel"] = conversation_channel(conversation)
    channel_instruction = conversation_channel_system_instruction(conversation)
    if channel_instruction:
        _append_system_context_message(standard_messages, channel_instruction)
    temporal_context = current_datetime_context(request_context)
''',
)

replace_once(
    "rumi_ai_1_10/ecosystem/defaultspack/domain/chat/store.py",
    '''            cid = _gen_id()
            now = _now_ms()
            parent_id = str(parent_conversation_id) if parent_conversation_id else None
            metadata_dict = dict(metadata) if isinstance(metadata, dict) else {}
            self._set_metadata_icon(metadata_dict, "New Conversation", cid)
''',
    '''            now = _now_ms()
            parent_id = str(parent_conversation_id) if parent_conversation_id else None
            requested_kind = conversation_kind or ("subagent" if parent_id else "chat")
            metadata_dict = dict(metadata) if isinstance(metadata, dict) else {}
            if parent_id and requested_kind == "side":
                for existing in self._conversations.values():
                    if (
                        isinstance(existing, dict)
                        and existing.get("parent_conversation_id") == parent_id
                        and existing.get("conversation_kind") == "side"
                    ):
                        return copy.deepcopy(existing)
            cid = _gen_id()
            self._set_metadata_icon(metadata_dict, "New Conversation", cid)
''',
)

replace_once(
    "rumi_ai_1_10/ecosystem/defaultspack/domain/chat/store.py",
    '''                "conversation_kind": conversation_kind or ("subagent" if parent_id else "chat"),
''',
    '''                "conversation_kind": requested_kind,
''',
)

replace_once(
    "rumi_ai_1_10/ecosystem/defaultspack/domain/chat/store.py",
    '''                for candidate in self._conversations.values():
                    if isinstance(candidate, dict) and candidate.get("parent_conversation_id") == conversation_id:
                        candidate["parent_conversation_id"] = None
                del self._conversations[conversation_id]
''',
    '''                side_child_ids = [
                    candidate_id
                    for candidate_id, candidate in self._conversations.items()
                    if (
                        isinstance(candidate, dict)
                        and candidate.get("parent_conversation_id") == conversation_id
                        and candidate.get("conversation_kind") == "side"
                    )
                ]
                for child_id in side_child_ids:
                    del self._conversations[child_id]
                for candidate in self._conversations.values():
                    if isinstance(candidate, dict) and candidate.get("parent_conversation_id") == conversation_id:
                        candidate["parent_conversation_id"] = None
                del self._conversations[conversation_id]
''',
)

replace_once(
    "rumi_ai_1_10/ecosystem/defaultspack/webapp/src/renderers/types.ts",
    '''  companyPanel?: ReactNode;
  codingPanel?: ReactNode;
''',
    '''  companyPanel?: ReactNode;
  codingPanel?: ReactNode;
  sideChatPanel?: ReactNode;
''',
)

replace_once(
    "rumi_ai_1_10/ecosystem/defaultspack/webapp/src/components/RightSidebar.tsx",
    '''  inspector: <Cpu size={18} />,
''',
    '''  inspector: <Cpu size={18} />,
  side_chat: <MessageSquareText size={18} />,
''',
)

replace_once(
    "rumi_ai_1_10/ecosystem/defaultspack/webapp/src/components/RightSidebar.tsx",
    '''  companyPanel,
  codingPanel,
  keyboardButtonNavigation = true,
''',
    '''  companyPanel,
  codingPanel,
  sideChatPanel,
  keyboardButtonNavigation = true,
''',
)

replace_once(
    "rumi_ai_1_10/ecosystem/defaultspack/webapp/src/components/RightSidebar.tsx",
    '''  companyPanel?: ReactNode;
  codingPanel?: ReactNode;
  keyboardButtonNavigation?: boolean;
''',
    '''  companyPanel?: ReactNode;
  codingPanel?: ReactNode;
  sideChatPanel?: ReactNode;
  keyboardButtonNavigation?: boolean;
''',
)

replace_once(
    "rumi_ai_1_10/ecosystem/defaultspack/webapp/src/components/RightSidebar.tsx",
    '''  const isCompanyPanelActive = activePanel === "__company_workspace__" && Boolean(companyPanel);
  const isCodingPanelActive = activePanel === "__coding_widget__" && Boolean(codingPanel);
''',
    '''  const isCompanyPanelActive = activePanel === "__company_workspace__" && Boolean(companyPanel);
  const isSideChatActive = activePanel === "side_chat" && Boolean(sideChatPanel);
  const isCodingPanelActive = activePanel === "__coding_widget__" && Boolean(codingPanel);
''',
)

replace_once(
    "rumi_ai_1_10/ecosystem/defaultspack/webapp/src/components/RightSidebar.tsx",
    '''          <div className={cn("flex-1 overflow-y-auto", isCompanyPanelActive ? "p-0" : "p-2.5")}>
            {isCompanyPanelActive ? (
              companyPanel
            ) : isCodingPanelActive ? (
''',
    '''          <div className={cn(
            "flex-1",
            isCompanyPanelActive || isSideChatActive ? "overflow-hidden p-0" : "overflow-y-auto p-2.5",
          )}>
            {isSideChatActive ? (
              sideChatPanel
            ) : isCompanyPanelActive ? (
              companyPanel
            ) : isCodingPanelActive ? (
''',
)

replace_once(
    "rumi_ai_1_10/ecosystem/defaultspack/webapp/src/App.tsx",
    '''import { ConversationSpotlight } from "./components/ConversationSpotlight";
''',
    '''import { ConversationSpotlight } from "./components/ConversationSpotlight";
import { SideChatWidget } from "./components/SideChatWidget";
''',
)

replace_once(
    "rumi_ai_1_10/ecosystem/defaultspack/webapp/src/App.tsx",
    '''type BackendConnectionState = "online" | "degraded" | "offline";
''',
    '''type BackendConnectionState = "online" | "degraded" | "offline";

const SIDE_CHAT_SIDEBAR_ITEM: SidebarItem = {
  id: "side_chat",
  label: "サイドチャット",
  category: "widget",
  description: "現在のチャットに紐づく補助会話",
  tags: ["chat", "side-chat"],
  ui: { item_icon: "side_chat" },
};
''',
)

replace_once(
    "rumi_ai_1_10/ecosystem/defaultspack/webapp/src/App.tsx",
    '''             items={sidebarItems}
''',
    '''             items={[
               SIDE_CHAT_SIDEBAR_ITEM,
               ...sidebarItems.filter((item) => item.id !== SIDE_CHAT_SIDEBAR_ITEM.id),
             ]}
''',
)

replace_once(
    "rumi_ai_1_10/ecosystem/defaultspack/webapp/src/App.tsx",
    '''             codingPanel={codingSidebarPanel}
             keyboardButtonNavigation={keyboardButtonNavigation}
''',
    '''             codingPanel={codingSidebarPanel}
             sideChatPanel={(
               <SideChatWidget
                 parentConversation={activeConversation}
                 selectedModel={preferredModel || activeConversation?.model || "stub/default"}
                 selectedProfile={activeProfile}
                 modelProfiles={selectableModelProfiles}
                 thinkingLevel={selectedThinkingLevel}
                 deepthinkEnabled={deepthinkEnabled}
                 contextUsage={contextUsage}
                 inlineExtensions={composerExtensions}
                 skillExtensions={composerSkills}
                 commands={composerCommands}
                 composerInput={composerInputMetadata}
                 selectedToolIds={selectedToolIds}
                 disabledToolIds={effectiveDisabledToolIds}
                 actionApprovalMode={actionApprovalMode}
                 yoloMode={yoloMode}
                 ultraYoloMode={ultraYoloMode}
                 mode={mode}
                 workspaceId={activeConversationWorkspaceContext.workspaceId ?? effectiveWorkspaceId}
                 workspaceLabel={activeConversationWorkspaceContext.workspaceLabel}
                 workspaceRoot={activeConversationWorkspaceContext.workspaceRoot}
                 templateParams={templateAiInputParams}
                 templateToolPolicy={templatePolicyReferencePayload}
                 voiceInputEnabled={settingsValues.general?.voice_input_enabled !== false}
                 voiceInputUseAi={settingsValues.general?.voice_input_use_ai === true}
                 unknownBlockStrategy={unknownBlockStrategy}
                 showActivityInMessages={showActivityInMessages}
                 showWidgets={showWidgets}
                 showPromptUsageInMessages={showPromptUsageInMessages}
                 composerRenderer={Renderers.composer}
                 messagesRenderer={Renderers.chatMessages}
                 onOpenModelManager={() => openSettingsSection("models")}
                 onOpenToolSettings={() => openSettingsSection("tools")}
                 onActionApprovalModeChange={handleActionApprovalModeChange}
                 onExtensionSelect={handleComposerExtensionSelect}
                 onCommandSelect={handleComposerCommand}
                 onModelProfileSelect={handleModelProfileSelect}
                 onThinkingLevelChange={handleThinkingLevelChange}
               />
             )}
             keyboardButtonNavigation={keyboardButtonNavigation}
''',
)

print("Applied side chat implementation.")
