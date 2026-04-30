import type { FormEvent, MutableRefObject } from "react";

import type { ChatActivityEvent, ChatContentBlock, ModelProfile, SettingsSection, SidebarAction, SidebarItem, ToolLogEntry, UICatalog } from "../lib/api";
import type { ChatItem } from "../components/HistoryBoard";
import type { ToolPreviewItem, ToolPreviewMode } from "../components/ToolPreview";

export type ChatUiMessage = {
  id: string;
  role: "user" | "agent";
  content: ChatContentBlock[];
  rawText: string;
  widget?: Record<string, unknown> | null;
  metadata?: {
    executionTime?: string;
    toolUsed?: string;
    modelName?: string;
    thinkingLabel?: string;
    attachedToolCount?: number;
  };
  events?: ChatActivityEvent[];
  toolLogs?: ToolLogEntry[];
};

export type ComposerExtensionItem = {
  id: string;
  label: string;
  category?: string;
  description?: string;
  disabled?: boolean;
};

export type ContextUsageInfo = {
  usedTokens: number;
  maxContext: number;
  ratio: number;
  label: string;
};

export type SettingChangeHandler = (sectionId: string, fieldId: string, value: unknown) => void;

export type TitleBarRendererProps = {
  appName?: string;
  appIcon?: string;
};

export type HistoryBoardRendererProps = {
  activeChatId: string | null;
  chatItems: ChatItem[];
  account?: NonNullable<UICatalog["app"]>["account"];
  onChatSelect: (conversationId: string) => void;
  onNewTask: () => void;
  onSettingsClick: () => void;
};

export type ChatHeaderRendererProps = {
  title: string;
  showPreview: boolean;
  canShowPreview: boolean;
  canOpenSettings: boolean;
  onTogglePreview: () => void;
  onOpenSettings: () => void;
};

export type ChatMessagesRendererProps = {
  error: string | null;
  isMessagesRegionVisible: boolean;
  isLoading: boolean;
  isNewConversation: boolean;
  isGenerating: boolean;
  messages: ChatUiMessage[];
  messagesEndRef: MutableRefObject<HTMLDivElement | null>;
  unknownBlockStrategy: string;
  showActivityInMessages: boolean;
  showWidgets: boolean;
  onSuggestionClick: (text: string) => void;
};

export type ComposerRendererProps = {
  input: string;
  placeholder: string;
  isGenerating: boolean;
  selectedProfile: ModelProfile | null;
  favoriteProfiles: ModelProfile[];
  thinkingLevel: string | null;
  contextUsage: ContextUsageInfo;
  inlineExtensions: ComposerExtensionItem[];
  belowExtensions: ComposerExtensionItem[];
  onModelProfileSelect: (profileId: string) => void;
  onThinkingLevelChange: (level: string | null) => void;
  onInputChange: (value: string) => void;
  onSubmit: (event: FormEvent) => void;
};

export type ToolPreviewPanelRendererProps = {
  previews: ToolPreviewItem[];
  showPreview: boolean;
  previewMode: ToolPreviewMode;
  activePreviewId: string | null;
  onClose: () => void;
  onModeChange: (mode: ToolPreviewMode) => void;
};

export type RightSidebarRendererProps = {
  items: SidebarItem[];
  settingsValues: Record<string, Record<string, unknown>>;
  settingsSections: SettingsSection[];
  onSettingChange: SettingChangeHandler;
  onOpenSettings: () => void;
  onPanelAction?: (item: SidebarItem, action: SidebarAction) => void;
};

export type SettingsModalRendererProps = {
  isOpen: boolean;
  catalog: UICatalog | null;
  health: { status: string; pack: string; ts: string } | null;
  previewsCount: number;
  settingsSections: SettingsSection[];
  settingsValues: Record<string, Record<string, unknown>>;
  onClose: () => void;
  onSettingChange: SettingChangeHandler;
};
