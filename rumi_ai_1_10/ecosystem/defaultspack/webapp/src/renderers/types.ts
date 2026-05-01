import type { FormEvent, MutableRefObject } from "react";

import type { ChatActivityEvent, ChatAttachment, ChatContentBlock, ModelProfile, SettingsSection, SidebarAction, SidebarItem, ToolLogEntry, UICatalog } from "../lib/api";
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
  tags?: string[];
  disabled?: boolean;
};

export type ComposerCommandItem = {
  id: string;
  label: string;
  description?: string;
  enabled?: boolean;
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
  onMinimize?: () => void;
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
  pendingStatus?: string | null;
  pendingToolNames?: string[];
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
  isNewConversation?: boolean;
  isGenerating: boolean;
  selectedProfile: ModelProfile | null;
  favoriteProfiles: ModelProfile[];
  thinkingLevel: string | null;
  contextUsage: ContextUsageInfo;
  inlineExtensions: ComposerExtensionItem[];
  belowExtensions: ComposerExtensionItem[];
  commands?: ComposerCommandItem[];
  yoloMode?: boolean;
  mode?: AppMode;
  codingContext?: CodingContext | null;
  attachedFiles?: AttachedFile[];
  droppedWidgets?: DroppedWidget[];
  onExtensionSelect?: (item: ComposerExtensionItem) => void;
  onFilesAttach?: (files: ChatAttachment[]) => void;
  onCommandSelect?: (commandId: string) => void;
  onModelProfileSelect: (profileId: string) => void;
  onThinkingLevelChange: (level: string | null) => void;
  onInputChange: (value: string) => void;
  onSubmit: (event: FormEvent) => void;
  onModeChange?: (mode: AppMode) => void;
  onFileAttach?: (files: AttachedFile[]) => void;
  onFileRemove?: (fileId: string) => void;
  onDropWidget?: (widget: DroppedWidget) => void;
  onWidgetToggle?: (widgetId: string) => void;
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
  activeItemId?: string | null;
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

export type ToolGroup = {
  id: string;
  label: string;
  description: string;
  icon?: string;
  items: ComposerExtensionItem[];
};

export type AppMode = "chat" | "coding" | "agent";

export type CodingContext = {
  branch: string | null;
  rootFolder: string | null;
  files: string[];
};

export type AttachedFile = {
  id: string;
  name: string;
  size: number;
  content: string;
  type?: string;
  truncated?: boolean;
};

export type DroppedWidget = {
  id: string;
  type: "tool" | "model" | "setting";
  label: string;
  enabled?: boolean;
};
