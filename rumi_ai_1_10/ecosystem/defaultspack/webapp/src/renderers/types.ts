import type { FormEvent, MutableRefObject, ReactNode } from "react";

import type { ChatActivityEvent, ChatContentBlock, CodingContextEntry, CodingGitStatus, CodingWorkspaceRecord, ComposerWidgetAction, ConversationSteerItem, ModelCommandCandidate, ModelProfile, SettingsSection, SidebarAction, SidebarItem, ToolLogEntry, UICatalog } from "../lib/api";
import type { ComposerCommandItem } from "../lib/api";
import type { ChatItem } from "../components/HistoryBoard";
import type { ToolPreviewItem, ToolPreviewMode } from "../components/ToolPreview";
import type { LocaleSetting } from "../lib/i18n";

export type { ComposerCommandItem } from "../lib/api";

export type ChatUiMessage = {
  id: string;
  conversationId?: string;
  role: "user" | "agent";
  content: ChatContentBlock[];
  rawText: string;
  widget?: Record<string, unknown> | null;
  metadata?: {
    executionTime?: string;
    toolUsed?: string;
    modelName?: string;
    thinkingLabel?: string;
    thinkingDuration?: string;
    thinkingTranscript?: string;
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
  ui?: SidebarItem["ui"];
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
  onChatMetadataChange?: (chatId: string, updates: { is_pinned?: boolean; is_starred?: boolean; tags?: string[] }) => void;
  onMinimize?: () => void;
  onRestore?: () => void;
  isCompact?: boolean;
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
  pendingStartedAt?: number | null;
  pendingToolStartedAt?: Record<string, number>;
  messages: ChatUiMessage[];
  messagesEndRef: MutableRefObject<HTMLDivElement | null>;
  unknownBlockStrategy: string;
  showActivityInMessages: boolean;
  showWidgets: boolean;
  onSuggestionClick: (text: string) => void;
  onOpenToolPreview?: (previewId: string) => void;
};

export type ComposerRendererProps = {
  input: string;
  placeholder: string;
  isNewConversation?: boolean;
  isGenerating: boolean;
  selectedProfile: ModelProfile | null;
  favoriteProfiles: ModelProfile[];
  modelProfiles?: ModelProfile[];
  thinkingLevel: string | null;
  contextUsage: ContextUsageInfo;
  inlineExtensions: ComposerExtensionItem[];
  belowExtensions: ComposerExtensionItem[];
  commands?: ComposerCommandItem[];
  modelCommandCandidates?: ModelCommandCandidate[];
  modelPickerRequestId?: number;
  yoloMode?: boolean;
  mode?: AppMode;
  codingContext?: CodingContext | null;
  codingWorkspaces?: CodingWorkspaceRecord[];
  selectedCodingWorkspaceId?: string | null;
  attachedFiles?: AttachedFile[];
  droppedWidgets?: DroppedWidget[];
  selectedToolIds?: string[];
  keyboardButtonNavigation?: boolean;
  steerStatus?: string | null;
  steerBusy?: boolean;
  steerQueuedCount?: number;
  steerPreviewItems?: ConversationSteerItem[];
  onExtensionSelect?: (item: ComposerExtensionItem) => void;
  onCommandSelect?: (commandId: string, rawInput?: string) => void;
  onModelCommandCandidateSelect?: (candidate: ModelCommandCandidate) => void;
  onModelCommandCandidatesClose?: () => void;
  onModelProfileSelect: (profileId: string) => void;
  onProviderApiKeySave?: (providerId: string, value: string) => Promise<void> | void;
  onThinkingLevelChange: (level: string | null) => void;
  onInputChange: (value: string) => void;
  onSubmit: (event: FormEvent) => void;
  onStopGenerating?: () => void;
  onSteerSubmit?: (prompt: string) => void;
  onModeChange?: (mode: AppMode) => void;
  onFileAttach?: (files: AttachedFile[]) => void;
  onAtFileAttach?: (path: string) => void;
  onFileRemove?: (fileId: string) => void;
  onDropWidget?: (widget: DroppedWidget) => void;
  onWidgetAction?: (widget: DroppedWidget) => void;
  onWidgetToggle?: (widgetId: string) => void;
  onCodingBranchSwitch?: (branch: string, create?: boolean) => void;
  onCodingDirectoryChange?: (directory: string) => void;
  onCodingWorkspaceSelect?: (workspaceId: string) => void;
  onCodingWorkspaceTrust?: (workspaceId: string) => void;
  onCodingWorkspaceCreate?: () => void;
  onCodingWorkspacesRefresh?: () => void;
  onCodingContextRefresh?: () => void;
};

export type ToolPreviewPanelRendererProps = {
  previews: ToolPreviewItem[];
  showPreview: boolean;
  previewMode: ToolPreviewMode;
  activePreviewId: string | null;
  memo?: string;
  onClose: () => void;
  onModeChange: (mode: ToolPreviewMode) => void;
  onMemoChange?: (value: string) => void;
};

export type RightSidebarRendererProps = {
  items: SidebarItem[];
  activeItemId?: string | null;
  settingsValues: Record<string, Record<string, unknown>>;
  settingsSections: SettingsSection[];
  selectedToolIds?: string[];
  companyPanel?: ReactNode;
  keyboardButtonNavigation?: boolean;
  onSettingChange: SettingChangeHandler;
  onOpenSettings: () => void;
  onToolToggle?: (item: SidebarItem) => void;
  onToolBatchSet?: (toolIds: string[], enabled: boolean) => void;
  onPanelAction?: (item: SidebarItem, action: SidebarAction) => void;
};

export type SettingsModalRendererProps = {
  isOpen: boolean;
  activeSectionId?: string | null;
  catalog: UICatalog | null;
  health: { status: string; pack: string; ts: string } | null;
  previewsCount: number;
  settingsSections: SettingsSection[];
  settingsValues: Record<string, Record<string, unknown>>;
  locale?: LocaleSetting;
  onClose: () => void;
  onSettingChange: SettingChangeHandler;
};

export type ToolGroup = {
  id: string;
  label: string;
  description: string;
  icon?: string;
  path?: string[];
  items: ComposerExtensionItem[];
};

export type AppMode = "chat" | "coding" | "agent";

export type CodingContext = {
  branch: string | null;
  rootFolder: string | null;
  workspaceId?: string | null;
  directory?: string;
  branches?: string[];
  files: string[];
  entries?: CodingContextEntry[];
  git?: CodingGitStatus | null;
};

export type AttachedFile = {
  id: string;
  name: string;
  size: number;
  content?: string;
  dataUrl?: string;
  type?: string;
  truncated?: boolean;
  source?: "local_file" | "workspace";
  sourcePath?: string;
};

export type DroppedWidget = {
  id: string;
  type: "tool" | "model" | "setting" | "button" | "panel" | "selector" | "model_card" | string;
  label: string;
  enabled?: boolean;
  widgetKind?: string;
  action?: ComposerWidgetAction;
  sourceItemId?: string;
  description?: string;
  icon?: string;
};
