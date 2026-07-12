import {
  useEffect,
  useMemo,
  useState,
  type ComponentType,
} from "react";
import { MessageSquareText, X } from "lucide-react";

import { SideChatWidget } from "../components/SideChatWidget";
import { api, type Conversation, type ModelProfile } from "../lib/api";
import type { ActionApprovalMode } from "../features/tools/ActionApprovalControl";
import type {
  AppMode,
  ComposerExtensionItem,
  ContextUsageInfo,
  RightSidebarRendererProps,
} from "./types";
import { ChatMessagesRenderer } from "./ChatMessagesRenderer";
import { ComposerRenderer } from "./ComposerRenderer";

type Props = RightSidebarRendererProps & {
  baseRenderer: ComponentType<RightSidebarRendererProps>;
};

const EMPTY_CONTEXT_USAGE: ContextUsageInfo = {
  usedTokens: 0,
  maxContext: 0,
  ratio: 0,
  label: "",
};

function record(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {};
}

function text(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function booleanSetting(value: unknown, fallback: boolean): boolean {
  return typeof value === "boolean" ? value : fallback;
}

function stringList(value: unknown): string[] {
  return Array.isArray(value)
    ? value.map((item) => String(item ?? "").trim()).filter(Boolean)
    : [];
}

function modelProfilesFromSettings(
  settingsValues: Record<string, Record<string, unknown>>,
  selectedProfile: ModelProfile | null,
): ModelProfile[] {
  const models = record(settingsValues.models);
  const source = [
    models.model_profiles,
    models.profiles,
    models.available_profiles,
  ].find(Array.isArray);
  const profiles = Array.isArray(source)
    ? source.filter((item): item is ModelProfile => (
        Boolean(item)
        && typeof item === "object"
        && typeof (item as Record<string, unknown>).profile_id === "string"
      ))
    : [];
  if (
    selectedProfile
    && !profiles.some((profile) => profile.profile_id === selectedProfile.profile_id)
  ) {
    profiles.unshift(selectedProfile);
  }
  return profiles;
}

function modeFromConversation(conversation: Conversation | null): AppMode {
  const metadata = record(conversation?.metadata);
  const value = text(metadata.mode);
  return value === "coding" || value === "agent" ? value : "chat";
}

function extensionItems(props: RightSidebarRendererProps): ComposerExtensionItem[] {
  return props.items.map((item) => ({
    id: item.id,
    label: item.label,
    category: item.category,
    description: item.description,
    tags: item.tags,
    disabled: item.disabled,
    ui: item.ui,
  }));
}

export function SideChatRightSidebarRenderer({
  baseRenderer: BaseRenderer,
  ...props
}: Props) {
  const [isOpen, setIsOpen] = useState(false);
  const [parentConversation, setParentConversation] = useState<Conversation | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const activeConversationId = props.activeConversationId ?? props.conversationId ?? null;

  useEffect(() => {
    let cancelled = false;
    setParentConversation(null);
    setLoadError(null);
    if (!activeConversationId) return () => { cancelled = true; };
    void api.getConversation(activeConversationId)
      .then((conversation) => {
        if (!cancelled) setParentConversation(conversation);
      })
      .catch((error) => {
        if (!cancelled) {
          setLoadError(error instanceof Error ? error.message : "現在のチャットを読み込めませんでした。");
        }
      });
    return () => { cancelled = true; };
  }, [activeConversationId]);

  const selectedProfile = props.selectedProfile ?? null;
  const modelProfiles = useMemo(
    () => modelProfilesFromSettings(props.settingsValues, selectedProfile),
    [props.settingsValues, selectedProfile],
  );
  const extensions = useMemo(() => extensionItems(props), [props.items]);
  const generalSettings = record(props.settingsValues.general);
  const modelSettings = record(props.settingsValues.models);
  const chatSettings = record(props.settingsValues.chat);
  const toolSettings = record(props.settingsValues.tools);
  const parentMetadata = record(parentConversation?.metadata);
  const selectedModel = parentConversation?.model
    || selectedProfile?.profile_id
    || text(modelSettings.preferred_model)
    || "stub/default";
  const thinkingLevel = text(modelSettings.thinking_level)
    || text(modelSettings.default_thinking_level);
  const actionApprovalMode = String(
    toolSettings.action_approval_mode
    ?? toolSettings.approval_mode
    ?? "ask",
  ) as ActionApprovalMode;

  const handleModelSelect = (profileId: string) => {
    props.onSettingChange("models", "preferred_model", profileId);
    if (activeConversationId) {
      void api.updateConversation(activeConversationId, { model: profileId })
        .then(setParentConversation)
        .catch(() => undefined);
    }
  };

  return (
    <div className="relative h-full min-h-0">
      <BaseRenderer {...props} />

      <button
        type="button"
        aria-label={isOpen ? "サイドチャットを閉じる" : "サイドチャットを開く"}
        title={isOpen ? "サイドチャットを閉じる" : "サイドチャットを開く"}
        onClick={() => setIsOpen((current) => !current)}
        className="absolute bottom-3 right-3 z-30 inline-flex h-9 w-9 items-center justify-center rounded-xl border border-zinc-700/80 bg-zinc-900/95 text-zinc-300 shadow-lg shadow-black/30 transition hover:border-zinc-600 hover:bg-zinc-800 hover:text-white"
      >
        {isOpen ? <X size={17} /> : <MessageSquareText size={17} />}
      </button>

      {isOpen && (
        <section
          aria-label="サイドチャット"
          className="absolute inset-0 z-20 flex min-h-0 flex-col overflow-hidden border-l border-zinc-800 bg-[#09090b] shadow-2xl shadow-black/40"
        >
          {loadError ? (
            <div className="flex h-full items-center justify-center p-5 text-center text-xs leading-5 text-red-300">
              {loadError}
            </div>
          ) : (
            <SideChatWidget
              parentConversation={parentConversation}
              selectedModel={selectedModel}
              selectedProfile={selectedProfile}
              modelProfiles={modelProfiles}
              thinkingLevel={thinkingLevel}
              deepthinkEnabled={booleanSetting(modelSettings.deepthink_enabled, false)}
              contextUsage={props.contextUsage ?? EMPTY_CONTEXT_USAGE}
              inlineExtensions={extensions}
              selectedToolIds={props.selectedToolIds ?? []}
              disabledToolIds={stringList(toolSettings.disabled_tools)}
              actionApprovalMode={actionApprovalMode}
              yoloMode={Boolean(props.yoloMode)}
              ultraYoloMode={booleanSetting(toolSettings.ultra_yolo_mode, false)}
              mode={modeFromConversation(parentConversation)}
              workspaceId={text(parentMetadata.workspace_id)}
              workspaceLabel={text(parentMetadata.workspace_label)}
              workspaceRoot={text(parentMetadata.workspace_root)}
              templateParams={{}}
              templateToolPolicy={toolSettings}
              voiceInputEnabled={booleanSetting(generalSettings.voice_input_enabled, true)}
              voiceInputUseAi={booleanSetting(generalSettings.voice_input_use_ai, false)}
              unknownBlockStrategy={text(chatSettings.unknown_block_strategy) ?? "fallback"}
              showActivityInMessages={booleanSetting(chatSettings.show_activity_in_messages, true)}
              showWidgets={booleanSetting(chatSettings.show_widgets, true)}
              showPromptUsageInMessages={Boolean(props.showChatPromptUsage)}
              composerRenderer={ComposerRenderer}
              messagesRenderer={ChatMessagesRenderer}
              onOpenModelManager={() => props.onOpenSettingsSection?.("models")}
              onOpenToolSettings={() => props.onOpenSettingsSection?.("tools")}
              onActionApprovalModeChange={(mode) => (
                props.onSettingChange("tools", "action_approval_mode", mode)
              )}
              onExtensionSelect={(item) => {
                const sidebarItem = props.items.find((candidate) => candidate.id === item.id);
                if (sidebarItem) props.onToolToggle?.(sidebarItem);
              }}
              onModelProfileSelect={handleModelSelect}
              onThinkingLevelChange={(level) => (
                props.onSettingChange("models", "thinking_level", level)
              )}
            />
          )}
        </section>
      )}
    </div>
  );
}
