import React, { useState, useEffect } from 'react';
import {
  DndContext,
  DragOverlay,
  closestCenter,
  KeyboardSensor,
  PointerSensor,
  defaultDropAnimationSideEffects,
  useDroppable,
  useSensor,
  useSensors,
  DragStartEvent,
  DragOverEvent,
  DragEndEvent,
  rectIntersection,
  pointerWithin,
  CollisionDetection,
} from '@dnd-kit/core';
import {
  SortableContext,
  arrayMove,
  sortableKeyboardCoordinates,
  verticalListSortingStrategy,
  useSortable,
} from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import {
  Globe, Terminal, MessageSquare, Plus, ChevronRight, Settings,
  GripVertical, FolderOpen, Folder, FolderPlus, MessageSquarePlus, PanelLeftClose, PanelLeftOpen, X,
} from 'lucide-react';
import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

// ============================================================
// Types
// ============================================================

export type ChatItem = {
  id: string;
  title: string;
  date: string;
  type: 'research' | 'code' | 'chat';
  parentId?: string | null;
  conversationKind?: string;
  sectionId?: string | null;
  sectionTitle?: string | null;
  children?: ChatItem[];
};

export type ChatGroup = {
  id: string;
  title: string;
  chats: ChatItem[];
  subGroups: ChatGroup[];
  isCollapsed?: boolean;
  custom?: boolean;
};

type CustomGroupInfo = {
  id: string;
  title: string;
};

export type AccountInfo = {
  display_name?: string;
  email?: string;
  plan_label?: string;
  avatar_url?: string;
  initial?: string;
  source?: string;
};

// ============================================================
// External data adapters
// ============================================================

function classifyChatType(chat: ChatItem): ChatItem['type'] {
  const title = chat.title.toLowerCase();
  if (
    title.includes('code') ||
    title.includes('build') ||
    title.includes('debug') ||
    title.includes('fix') ||
    title.includes('react') ||
    title.includes('rust') ||
    title.includes('api')
  ) {
    return 'code';
  }
  if (
    title.includes('research') ||
    title.includes('調査') ||
    title.includes('分析') ||
    title.includes('market') ||
    title.includes('trend')
  ) {
    return 'research';
  }
  return 'chat';
}

function groupDateLabel(dateText: string): 'today' | 'recent' | 'older' {
  if (dateText === 'Today') {
    return 'today';
  }
  if (dateText === 'Yesterday' || dateText === 'Previous 7 Days') {
    return 'recent';
  }
  return 'older';
}

const CUSTOM_GROUPS_STORAGE_KEY = 'rumi-history-custom-groups';

function loadCustomGroups(): CustomGroupInfo[] {
  try {
    const raw = localStorage.getItem(CUSTOM_GROUPS_STORAGE_KEY);
    const parsed = raw ? JSON.parse(raw) : [];
    return Array.isArray(parsed)
      ? parsed.filter((item): item is CustomGroupInfo => Boolean(item?.id && item?.title))
      : [];
  } catch {
    return [];
  }
}

function saveCustomGroups(groups: CustomGroupInfo[]) {
  try {
    localStorage.setItem(CUSTOM_GROUPS_STORAGE_KEY, JSON.stringify(groups));
  } catch {
    // localStorage can be unavailable in restricted contexts.
  }
}

export function buildGroupsFromChats(chatItems: ChatItem[], customGroups: CustomGroupInfo[] = []): ChatGroup[] {
  const buckets: Record<'today' | 'recent' | 'older', ChatItem[]> = {
    today: [],
    recent: [],
    older: [],
  };
  const integrationGroups = new Map<string, ChatGroup>();

  chatItems.forEach((chat) => {
    const normalized = {
      ...chat,
      type: classifyChatType(chat),
    };
    const sectionId = typeof normalized.sectionId === "string" ? normalized.sectionId.trim() : "";
    const sectionTitle = typeof normalized.sectionTitle === "string" ? normalized.sectionTitle.trim() : "";
    if (sectionId && sectionTitle) {
      const existing = integrationGroups.get(sectionId);
      if (existing) {
        existing.chats.push(normalized);
      } else {
        integrationGroups.set(sectionId, {
          id: sectionId,
          title: sectionTitle,
          isCollapsed: false,
          chats: [normalized],
          subGroups: [],
        });
      }
      return;
    }
    buckets[groupDateLabel(chat.date)].push(normalized);
  });

  const groups: ChatGroup[] = [
    {
      id: 'group-today',
      title: 'Today',
      isCollapsed: false,
      chats: buckets.today,
      subGroups: [],
    },
    {
      id: 'group-recent',
      title: 'Recent',
      isCollapsed: false,
      chats: buckets.recent,
      subGroups: [],
    },
    {
      id: 'group-older',
      title: 'Older',
      isCollapsed: false,
      chats: buckets.older,
      subGroups: [],
    },
  ];

  const visibleGroups = groups.filter((group) => group.chats.length > 0);
  const custom = customGroups.map((group) => ({
    id: group.id,
    title: group.title,
    isCollapsed: false,
    chats: [],
    subGroups: [],
    custom: true,
  }));
  return [...custom, ...integrationGroups.values(), ...visibleGroups];
}

// ============================================================
// Utility functions
// ============================================================

function countChats(group: ChatGroup): number {
  let count = group.chats.reduce((total, chat) => total + countChatWithChildren(chat), 0);
  for (const sub of group.subGroups) count += countChats(sub);
  return count;
}

function countChatWithChildren(chat: ChatItem): number {
  return 1 + (chat.children ?? []).reduce((total, child) => total + countChatWithChildren(child), 0);
}

function findGroupContainingChat(groups: ChatGroup[], chatId: string): string | null {
  for (const g of groups) {
    if (g.chats.some(c => c.id === chatId)) return g.id;
    const found = findGroupContainingChat(g.subGroups, chatId);
    if (found) return found;
  }
  return null;
}

function removeChatFromTree(groups: ChatGroup[], chatId: string): { groups: ChatGroup[]; chat: ChatItem | null } {
  let removedChat: ChatItem | null = null;
  const newGroups = groups.map(g => {
    if (removedChat) return g;
    const idx = g.chats.findIndex(c => c.id === chatId);
    if (idx !== -1) {
      removedChat = g.chats[idx];
      return { ...g, chats: g.chats.filter(c => c.id !== chatId) };
    }
    const result = removeChatFromTree(g.subGroups, chatId);
    if (result.chat) {
      removedChat = result.chat;
      return { ...g, subGroups: result.groups };
    }
    return g;
  });
  return { groups: newGroups, chat: removedChat };
}

function removeGroupFromTree(groups: ChatGroup[], groupId: string): { groups: ChatGroup[]; removed: ChatGroup | null } {
  const idx = groups.findIndex(g => g.id === groupId);
  if (idx !== -1) {
    return { groups: groups.filter(g => g.id !== groupId), removed: groups[idx] };
  }
  let removed: ChatGroup | null = null;
  const newGroups = groups.map(g => {
    if (removed) return g;
    const result = removeGroupFromTree(g.subGroups, groupId);
    if (result.removed) {
      removed = result.removed;
      return { ...g, subGroups: result.groups };
    }
    return g;
  });
  return { groups: newGroups, removed };
}

function addChatToGroup(groups: ChatGroup[], groupId: string, chat: ChatItem, position?: number): ChatGroup[] {
  return groups.map(g => {
    if (g.id === groupId) {
      const newChats = [...g.chats];
      if (position !== undefined) newChats.splice(position, 0, chat);
      else newChats.push(chat);
      return { ...g, chats: newChats };
    }
    return { ...g, subGroups: addChatToGroup(g.subGroups, groupId, chat, position) };
  });
}

function findGroupById(groups: ChatGroup[], id: string): ChatGroup | null {
  for (const g of groups) {
    if (g.id === id) return g;
    const found = findGroupById(g.subGroups, id);
    if (found) return found;
  }
  return null;
}

function mapGroups(groups: ChatGroup[], fn: (g: ChatGroup) => ChatGroup): ChatGroup[] {
  return groups.map(g => {
    const mapped = fn(g);
    return { ...mapped, subGroups: mapGroups(mapped.subGroups, fn) };
  });
}

function getAllChatIds(groups: ChatGroup[]): string[] {
  const ids: string[] = [];
  for (const g of groups) {
    ids.push(...g.chats.flatMap(getChatIds));
    ids.push(...getAllChatIds(g.subGroups));
  }
  return ids;
}

function getChatIds(chat: ChatItem): string[] {
  return [chat.id, ...(chat.children ?? []).flatMap(getChatIds)];
}

function getAllGroupDragIds(groups: ChatGroup[]): string[] {
  const ids: string[] = [];
  for (const g of groups) {
    ids.push(`drag-col-${g.id}`);
    ids.push(...getAllGroupDragIds(g.subGroups));
  }
  return ids;
}

function flattenChats(groups: ChatGroup[]): ChatItem[] {
  const chats: ChatItem[] = [];
  const visitChat = (chat: ChatItem) => {
    chats.push(chat);
    for (const child of chat.children ?? []) visitChat(child);
  };
  const visitGroup = (group: ChatGroup) => {
    for (const chat of group.chats) visitChat(chat);
    for (const subGroup of group.subGroups) visitGroup(subGroup);
  };
  for (const group of groups) visitGroup(group);
  return chats;
}

// ============================================================
// Custom collision detection
// ============================================================

function createCustomCollision(activeType: string | null): CollisionDetection {
  return (args) => {
    if (activeType === 'ColumnDrag') {
      const columnContainers = args.droppableContainers.filter(container => {
        const type = container.data?.current?.type;
        return type === 'Column' || type === 'SubGroup' || container.id === 'extract-to-top-level';
      });
      return rectIntersection({ ...args, droppableContainers: columnContainers });
    }
    return pointerWithin(args);
  };
}

// ============================================================
// SortableChatItem
// ============================================================

interface SortableChatItemProps {
  chat: ChatItem;
  activeChatId: string | null;
  onChatSelect: (chatId: string) => void;
  onRename: (id: string, newTitle: string) => void;
  onToggleChildren: (chatId: string) => void;
  isChildrenExpanded: (chatId: string) => boolean;
  depth?: number;
}

function SortableChatItem({ chat, activeChatId, onChatSelect, onRename, onToggleChildren, isChildrenExpanded, depth = 0 }: SortableChatItemProps) {
  const [isEditing, setIsEditing] = useState(false);
  const [title, setTitle] = useState(chat.title);
  const children = chat.children ?? [];
  const hasChildren = children.length > 0;
  const expanded = hasChildren && isChildrenExpanded(chat.id);
  const isActive = activeChatId === chat.id;

  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: chat.id,
    data: { type: 'Chat', chat },
    disabled: isEditing,
  });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.3 : 1,
    paddingLeft: `${depth * 16 + 8}px`,
  };

  const handleBlur = () => {
    setIsEditing(false);
    if (title.trim() && title !== chat.title) onRename(chat.id, title);
    else setTitle(chat.title);
  };

  const icon = chat.type === 'research' ? <Globe size={14} className="text-zinc-500 flex-shrink-0" /> :
               chat.type === 'code' ? <Terminal size={14} className="text-zinc-500 flex-shrink-0" /> :
               <MessageSquare size={14} className="text-zinc-500 flex-shrink-0" />;

  return (
    <>
      <div
        ref={setNodeRef}
        style={style}
        {...attributes}
        {...listeners}
        className={cn(
          "w-full flex items-center gap-2 pr-2 py-1.5 rounded-md text-left group/chat transition-colors cursor-grab active:cursor-grabbing outline-none",
          isActive ? "bg-zinc-800/80" : "hover:bg-zinc-800/50",
          chat.conversationKind === "subagent" && "text-zinc-400",
          isDragging && "ring-1 ring-emerald-500/50 z-50"
        )}
        onClick={() => { if (!isEditing) onChatSelect(chat.id); }}
        onDoubleClick={(e) => { e.stopPropagation(); setIsEditing(true); }}
        tabIndex={0}
      >
        <GripVertical size={12} className="text-zinc-700 group-hover/chat:text-zinc-500 flex-shrink-0" />
        {icon}
        {hasChildren && (
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              onToggleChildren(chat.id);
            }}
            className="flex h-4 w-4 flex-shrink-0 items-center justify-center rounded text-zinc-500 transition-colors hover:bg-zinc-800 hover:text-zinc-100"
            title={expanded ? "Subagents を閉じる" : "Subagents を開く"}
          >
            <ChevronRight size={13} className={cn("transition-transform", expanded && "rotate-90")} />
          </button>
        )}
        {isEditing ? (
          <input
            autoFocus
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            onBlur={handleBlur}
            onKeyDown={(e) => {
              if (e.key === 'Enter') { e.preventDefault(); handleBlur(); }
              if (e.key === 'Escape') { setIsEditing(false); setTitle(chat.title); }
            }}
            onClick={(e) => e.stopPropagation()}
            className="bg-zinc-900 text-zinc-100 text-sm px-1 py-0.5 rounded outline-none w-full border border-emerald-500/50"
          />
        ) : (
          <span className={cn(
            "text-sm truncate flex-1 select-none",
            isActive ? "text-zinc-100" : "text-zinc-300 group-hover/chat:text-zinc-100"
          )}>{chat.title}</span>
        )}
      </div>
      {expanded && (
        <div className="space-y-0.5">
          {children.map((child) => (
            <SortableChatItem
              key={child.id}
              chat={child}
              activeChatId={activeChatId}
              onChatSelect={onChatSelect}
              onRename={onRename}
              onToggleChildren={onToggleChildren}
              isChildrenExpanded={isChildrenExpanded}
              depth={depth + 1}
            />
          ))}
        </div>
      )}
    </>
  );
}

// ============================================================
// SubGroup (VSCode folder style, recursive)
// ============================================================

interface SubGroupProps {
  group: ChatGroup;
  activeChatId: string | null;
  onChatSelect: (chatId: string) => void;
  onChatRename: (chatId: string, newTitle: string) => void;
  onToggleCollapse: (id: string) => void;
  onRenameGroup: (id: string, newTitle: string) => void;
  onUngroup: (groupId: string) => void;
  onToggleChatChildren: (chatId: string) => void;
  isChatChildrenExpanded: (chatId: string) => boolean;
  depth: number;
}

function SubGroup({ group, activeChatId, onChatSelect, onChatRename, onToggleCollapse, onRenameGroup, onUngroup, onToggleChatChildren, isChatChildrenExpanded, depth }: SubGroupProps) {
  const [isEditing, setIsEditing] = useState(false);
  const [title, setTitle] = useState(group.title);

  const {
    attributes,
    listeners,
    setNodeRef: setSortRef,
    transform,
    transition,
    isDragging,
  } = useSortable({
    id: `drag-col-${group.id}`,
    data: { type: 'ColumnDrag', group },
    disabled: isEditing,
  });

  const { setNodeRef: setDropRef, isOver } = useDroppable({
    id: `subgroup-drop-${group.id}`,
    data: { type: 'SubGroup', group },
  });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.3 : 1,
  };

  const handleBlur = () => {
    setIsEditing(false);
    if (title.trim() && title !== group.title) onRenameGroup(group.id, title);
    else setTitle(group.title);
  };

  const total = countChats(group);

  return (
    <div
      ref={(node) => { setSortRef(node); setDropRef(node); }}
      style={style}
      className={cn(
        "transition-colors rounded-md",
        isOver && !isDragging && "bg-emerald-500/5 ring-1 ring-emerald-500/20",
        isDragging && "ring-1 ring-emerald-500/50"
      )}
    >
      <div
        className="flex items-center gap-1.5 py-1.5 px-1 rounded-md hover:bg-zinc-800/50 cursor-default group/folder"
        style={{ paddingLeft: `${depth * 16 + 4}px` }}
        onClick={() => onToggleCollapse(group.id)}
      >
        <ChevronRight size={14} className={cn("text-zinc-600 transition-transform duration-200 flex-shrink-0", !group.isCollapsed && "rotate-90")} />
        {group.isCollapsed
          ? <Folder size={14} className="text-zinc-500 flex-shrink-0" />
          : <FolderOpen size={14} className="text-zinc-400 flex-shrink-0" />}
        {isEditing ? (
          <input
            autoFocus
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            onBlur={handleBlur}
            onKeyDown={(e) => {
              if (e.key === 'Enter') handleBlur();
              if (e.key === 'Escape') { setIsEditing(false); setTitle(group.title); }
            }}
            onClick={(e) => e.stopPropagation()}
            className="bg-zinc-900 text-zinc-100 text-xs px-1 py-0.5 rounded outline-none flex-1 border border-emerald-500/50"
          />
        ) : (
          <span
            className="text-xs font-medium text-zinc-400 truncate flex-1 select-none group-hover/folder:text-zinc-200"
            onDoubleClick={(e) => { e.stopPropagation(); setIsEditing(true); }}
          >
            {group.title}
          </span>
        )}
        <span className="text-[10px] text-zinc-600 mr-1">{total}</span>
        <div
          {...attributes}
          {...listeners}
          className="p-0.5 text-zinc-700 hover:text-zinc-400 opacity-0 group-hover/folder:opacity-100 transition-all cursor-grab active:cursor-grabbing"
          onClick={(e) => e.stopPropagation()}
          title="Drag to move"
        >
          <GripVertical size={12} />
        </div>
        <button
          onClick={(e) => { e.stopPropagation(); onUngroup(group.id); }}
          className="text-zinc-600 hover:text-zinc-300 opacity-0 group-hover/folder:opacity-100 transition-all p-0.5"
          title="Ungroup"
        >
          <X size={12} />
        </button>
      </div>

      <div
        className={cn(
          "rumi-history-collapse overflow-hidden",
          group.isCollapsed && "is-collapsed"
        )}
      >
        <div className="rumi-history-collapse-inner">
          <SortableContext items={group.chats.map(c => c.id)} strategy={verticalListSortingStrategy}>
            {group.chats.map(chat => (
              <SortableChatItem
                key={chat.id}
                chat={chat}
                activeChatId={activeChatId}
                onChatSelect={onChatSelect}
                onRename={onChatRename}
                onToggleChildren={onToggleChatChildren}
                isChildrenExpanded={isChatChildrenExpanded}
                depth={depth + 1}
              />
            ))}
          </SortableContext>
          {group.subGroups.map(sub => (
            <SubGroup
              key={sub.id}
              group={sub}
              activeChatId={activeChatId}
              onChatSelect={onChatSelect}
              onChatRename={onChatRename}
              onToggleCollapse={onToggleCollapse}
              onRenameGroup={onRenameGroup}
              onUngroup={onUngroup}
              onToggleChatChildren={onToggleChatChildren}
              isChatChildrenExpanded={isChatChildrenExpanded}
              depth={depth + 1}
            />
          ))}
        </div>
      </div>
    </div>
  );
}

// ============================================================
// DroppableColumn (top-level group)
// ============================================================

interface DroppableColumnProps {
  group: ChatGroup;
  activeChatId: string | null;
  onChatSelect: (chatId: string) => void;
  onNewTask: (groupId: string) => void;
  onSettingsClick: () => void;
  onRename: (id: string, newTitle: string) => void;
  onToggleCollapse: (id: string) => void;
  onChatRename: (chatId: string, newTitle: string) => void;
  onUngroup: (groupId: string) => void;
  onToggleChatChildren: (chatId: string) => void;
  isChatChildrenExpanded: (chatId: string) => boolean;
  isDraggedOver: boolean;
  isDragging: boolean;
  dragHandleProps?: React.HTMLAttributes<HTMLDivElement>;
}

function DroppableColumn({ group, activeChatId, onChatSelect, onNewTask, onSettingsClick, onRename, onToggleCollapse, onChatRename, onUngroup, onToggleChatChildren, isChatChildrenExpanded, isDraggedOver, isDragging, dragHandleProps }: DroppableColumnProps) {
  const [isEditing, setIsEditing] = useState(false);
  const [title, setTitle] = useState(group.title);

  const { setNodeRef: setDropRef } = useDroppable({
    id: group.id,
    data: { type: 'Column', group },
  });

  const handleBlur = () => {
    setIsEditing(false);
    if (title.trim() && title !== group.title) onRename(group.id, title);
    else setTitle(group.title);
  };

  const totalChats = countChats(group);

  return (
    <div
      ref={setDropRef}
      className={cn(
        "w-full flex-shrink-0 border-b border-zinc-800/60 bg-[#09090b] flex flex-col transition-all duration-300",
        isDraggedOver && !isDragging && "ring-2 ring-inset ring-emerald-500/50 bg-emerald-500/[0.08]",
      )}
    >
      {/* Header */}
      <div
        onClick={() => onToggleCollapse(group.id)}
        className={cn(
          "h-12 flex items-center px-3 border-b border-zinc-800/60 justify-between hover:bg-zinc-900/50 transition-colors cursor-pointer group/colheader",
          isDraggedOver && !isDragging && "bg-emerald-500/15"
        )}
      >
        <div className="flex items-center gap-2 text-zinc-100 font-medium flex-1 min-w-0">
          <div
            {...dragHandleProps}
            onClick={(event) => event.stopPropagation()}
            className={cn(
              "flex h-6 w-4 flex-shrink-0 items-center justify-center rounded text-zinc-700 transition-all cursor-grab active:cursor-grabbing hover:bg-zinc-800 hover:text-zinc-400",
              group.isCollapsed ? "opacity-100" : "opacity-0 group-hover/colheader:opacity-100"
            )}
            title="Drag group"
          >
            <GripVertical size={12} />
          </div>
          <ChevronRight size={14} className={cn("transition-transform duration-200 text-zinc-500 flex-shrink-0", !group.isCollapsed && "rotate-90")} />
          <div className="w-5 h-5 rounded bg-zinc-800 text-zinc-400 flex-shrink-0 flex items-center justify-center text-[10px] font-bold border border-zinc-700">
            {group.title.charAt(0)}
          </div>
          {isEditing ? (
            <input
              autoFocus
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              onBlur={handleBlur}
              onKeyDown={(e) => {
                if (e.key === 'Enter') handleBlur();
                if (e.key === 'Escape') { setIsEditing(false); setTitle(group.title); }
              }}
              onClick={(e) => e.stopPropagation()}
              className="bg-zinc-800 text-zinc-100 text-sm px-1 py-0.5 rounded outline-none w-full border border-emerald-500/50"
            />
          ) : (
            <span
              onDoubleClick={(e) => { e.stopPropagation(); setIsEditing(true); }}
              className="truncate flex-1 cursor-text select-none hover:text-white transition-colors text-sm"
            >
              {group.title}
            </span>
          )}
          <span className="text-[10px] text-zinc-600 flex-shrink-0">{totalChats}</span>
        </div>
        <div className="flex items-center gap-1 opacity-0 group-hover/colheader:opacity-100 transition-opacity" onClick={(e) => e.stopPropagation()}>
          <button onClick={() => onNewTask(group.id)} className="p-1 text-zinc-500 hover:text-emerald-400 transition-colors" title="New chat in group">
            <Plus size={14} />
          </button>
        </div>
      </div>

      {/* Content */}
      <div
        className={cn(
          "rumi-history-collapse overflow-hidden",
          group.isCollapsed && "is-collapsed"
        )}
      >
        <div className="rumi-history-collapse-inner px-1 py-2 space-y-0.5">
          <SortableContext items={group.chats.map(c => c.id)} strategy={verticalListSortingStrategy}>
            {group.chats.map(chat => (
              <SortableChatItem
                key={chat.id}
                chat={chat}
                activeChatId={activeChatId}
                onChatSelect={onChatSelect}
                onRename={onChatRename}
                onToggleChildren={onToggleChatChildren}
                isChildrenExpanded={isChatChildrenExpanded}
                depth={0}
              />
            ))}
          </SortableContext>
          {group.subGroups.map(sub => (
            <SubGroup
              key={sub.id}
              group={sub}
              activeChatId={activeChatId}
              onChatSelect={onChatSelect}
              onChatRename={onChatRename}
              onToggleCollapse={onToggleCollapse}
              onRenameGroup={onRename}
              onUngroup={onUngroup}
              onToggleChatChildren={onToggleChatChildren}
              isChatChildrenExpanded={isChatChildrenExpanded}
              depth={0}
            />
          ))}

          {isDraggedOver && !isDragging && (
            <div className="mx-2 my-2 p-3 border-2 border-dashed border-emerald-500/40 rounded-lg text-center">
              <FolderOpen size={18} className="text-emerald-400 mx-auto mb-1" />
              <p className="text-[11px] text-emerald-400 font-medium">フォルダとして追加</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ============================================================
// DraggableColumnHandle
// ============================================================

function DraggableColumnHandle({ group, children }: { group: ChatGroup; children: (dragHandleProps: React.HTMLAttributes<HTMLDivElement>) => React.ReactNode }) {
  const { attributes, listeners, setNodeRef, isDragging } = useSortable({
    id: `drag-col-${group.id}`,
    data: { type: 'ColumnDrag', group },
  });
  const dragHandleProps = { ...attributes, ...listeners } as React.HTMLAttributes<HTMLDivElement>;

  return (
    <div ref={setNodeRef} className={cn("relative", isDragging && "opacity-30")}>
      <div>{children(dragHandleProps)}</div>
    </div>
  );
}

// ============================================================
// ExtractDropZone
// ============================================================

function ExtractDropZone() {
  const { setNodeRef, isOver } = useDroppable({ id: 'extract-to-top-level' });

  return (
    <div
      ref={setNodeRef}
      className={cn(
        "w-[180px] flex-shrink-0 flex items-center justify-center border-r border-dashed border-zinc-800/60 transition-all duration-200",
        isOver ? "bg-emerald-500/10 border-emerald-500/40" : "bg-zinc-900/30"
      )}
    >
      <div className={cn(
        "text-center p-4 rounded-xl border-2 border-dashed transition-all",
        isOver ? "border-emerald-500/50 text-emerald-400 scale-105" : "border-zinc-800 text-zinc-600"
      )}>
        <Plus size={24} className="mx-auto mb-2" />
        <p className="text-xs font-medium">ドロップで<br/>独立カラムに</p>
      </div>
    </div>
  );
}

// ============================================================
// HistoryBoard (main export)
// ============================================================

interface HistoryBoardProps {
  activeChatId: string | null;
  chatItems: ChatItem[];
  account?: AccountInfo;
  onChatSelect: (chatId: string) => void;
  onNewTask: () => void;
  onSettingsClick: () => void;
  onMinimize?: () => void;
  onRestore?: () => void;
  isCompact?: boolean;
}

export function HistoryBoard({ activeChatId, chatItems, account, onChatSelect, onNewTask, onSettingsClick, onMinimize, onRestore, isCompact = false }: HistoryBoardProps) {
  const [customGroups, setCustomGroups] = useState<CustomGroupInfo[]>(() => loadCustomGroups());
  const [groups, setGroups] = useState<ChatGroup[]>(() => buildGroupsFromChats(chatItems, customGroups));
  const [expandedChatIds, setExpandedChatIds] = useState<Set<string>>(() => new Set());

  useEffect(() => {
    setGroups((previousGroups) => {
      const collapsedById = new Map(previousGroups.map((group) => [group.id, group.isCollapsed]));
      return buildGroupsFromChats(chatItems, customGroups).map((group) => ({
        ...group,
        isCollapsed: collapsedById.get(group.id) ?? group.isCollapsed,
      }));
    });
  }, [chatItems, customGroups]);

  const [activeColumnDrag, setActiveColumnDrag] = useState<ChatGroup | null>(null);
  const [activeChat, setActiveChat] = useState<ChatItem | null>(null);
  const [overColumnId, setOverColumnId] = useState<string | null>(null);
  const [activeType, setActiveType] = useState<string | null>(null);

  const sensors = useSensors(
    useSensor(PointerSensor, { activationConstraint: { distance: 8 } }),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates })
  );

  // --- Drag Start ---
  const handleDragStart = (event: DragStartEvent) => {
    const { active } = event;
    if (active.data.current?.type === 'ColumnDrag') {
      setActiveColumnDrag(active.data.current.group);
      setActiveType('ColumnDrag');
    } else if (active.data.current?.type === 'Chat') {
      setActiveChat(active.data.current.chat);
      setActiveType('Chat');
    }
  };

  // --- Drag Over ---
  const handleDragOver = (event: DragOverEvent) => {
    const { active, over } = event;
    if (!over) { setOverColumnId(null); return; }

    if (active.data.current?.type === 'ColumnDrag') {
      if (over.data.current?.type === 'Column') {
        setOverColumnId(over.id as string);
      } else {
        setOverColumnId(null);
      }
      return;
    }

    if (active.data.current?.type !== 'Chat') return;
    if (active.id === over.id) return;

    const isOverChat = over.data.current?.type === 'Chat';
    const isOverColumn = over.data.current?.type === 'Column';
    const isOverSubGroup = over.data.current?.type === 'SubGroup';

    if (isOverChat) {
      setGroups(prev => {
        const activeGroupId = findGroupContainingChat(prev, active.id as string);
        const overGroupId = findGroupContainingChat(prev, over.id as string);
        if (!activeGroupId || !overGroupId) return prev;

        if (activeGroupId === overGroupId) {
          return mapGroups(prev, g => {
            if (g.id === activeGroupId) {
              const oldIdx = g.chats.findIndex(c => c.id === active.id);
              const newIdx = g.chats.findIndex(c => c.id === over.id);
              if (oldIdx === -1 || newIdx === -1) return g;
              return { ...g, chats: arrayMove(g.chats, oldIdx, newIdx) };
            }
            return g;
          });
        } else {
          const { groups: stripped, chat } = removeChatFromTree(prev, active.id as string);
          if (!chat) return prev;
          return mapGroups(stripped, g => {
            if (g.id === overGroupId) {
              const overIdx = g.chats.findIndex(c => c.id === over.id);
              const newChats = [...g.chats];
              newChats.splice(overIdx, 0, chat);
              return { ...g, chats: newChats };
            }
            return g;
          });
        }
      });
    }

    if (isOverColumn || isOverSubGroup) {
      const targetId = isOverSubGroup ? over.data.current?.group?.id : over.id as string;
      if (!targetId) return;
      setGroups(prev => {
        const currentGroupId = findGroupContainingChat(prev, active.id as string);
        if (currentGroupId === targetId) return prev;
        const { groups: stripped, chat } = removeChatFromTree(prev, active.id as string);
        if (!chat) return prev;
        return addChatToGroup(stripped, targetId, chat);
      });
    }
  };

  // --- Drag End ---
  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;
    setActiveColumnDrag(null);
    setActiveChat(null);
    setOverColumnId(null);
    setActiveType(null);

    if (!over || active.id === over.id) return;

    // Column → Column: nest inside
    if (active.data.current?.type === 'ColumnDrag' && over.data.current?.type === 'Column') {
      const draggedGroupId = active.data.current.group.id;
      const targetGroupId = over.id as string;
      if (draggedGroupId === targetGroupId) return;

      setGroups(prev => {
        const draggedGroup = findGroupById(prev, draggedGroupId);
        if (!draggedGroup) return prev;
        if (findGroupById(draggedGroup.subGroups, targetGroupId)) return prev;

        const { groups: stripped, removed } = removeGroupFromTree(prev, draggedGroupId);
        if (!removed) return prev;

        return mapGroups(stripped, g => {
          if (g.id === targetGroupId) {
            return { ...g, subGroups: [...g.subGroups, { ...removed, isCollapsed: false }] };
          }
          return g;
        });
      });
    }

    // Column → SubGroup: nest inside subgroup
    if (active.data.current?.type === 'ColumnDrag' && over.data.current?.type === 'SubGroup') {
      const draggedGroupId = active.data.current.group.id;
      const targetGroupId = over.data.current.group.id;
      if (draggedGroupId === targetGroupId) return;

      setGroups(prev => {
        const draggedGroup = findGroupById(prev, draggedGroupId);
        if (!draggedGroup) return prev;
        if (findGroupById(draggedGroup.subGroups, targetGroupId)) return prev;

        const { groups: stripped, removed } = removeGroupFromTree(prev, draggedGroupId);
        if (!removed) return prev;

        return mapGroups(stripped, g => {
          if (g.id === targetGroupId) {
            return { ...g, subGroups: [...g.subGroups, { ...removed, isCollapsed: false }] };
          }
          return g;
        });
      });
    }

    // Column → extract zone: promote to top-level
    if (active.data.current?.type === 'ColumnDrag' && over.id === 'extract-to-top-level') {
      const draggedGroupId = active.data.current.group.id;
      setGroups(prev => {
        const { groups: stripped, removed } = removeGroupFromTree(prev, draggedGroupId);
        if (!removed) return prev;
        return [...stripped, { ...removed, isCollapsed: false }];
      });
    }
  };

  // --- Actions ---
  const handleRenameGroup = (id: string, newTitle: string) => {
    setGroups(prev => mapGroups(prev, g => g.id === id ? { ...g, title: newTitle } : g));
    setCustomGroups((prev) => {
      const next = prev.map((group) => group.id === id ? { ...group, title: newTitle } : group);
      saveCustomGroups(next);
      return next;
    });
  };

  const handleToggleCollapse = (id: string) => {
    setGroups(prev => mapGroups(prev, g => g.id === id ? { ...g, isCollapsed: !g.isCollapsed } : g));
  };

  const handleNewTaskInGroup = (groupId: string) => {
    void groupId;
    onNewTask();
  };

  const handleRenameChat = (chatId: string, newTitle: string) => {
    setGroups(prev => mapGroups(prev, g => ({
      ...g,
      chats: g.chats.map(c => c.id === chatId ? { ...c, title: newTitle } : c),
    })));
  };

  const handleUngroup = (subGroupId: string) => {
    setGroups(prev => mapGroups(prev, g => {
      const subIdx = g.subGroups.findIndex(s => s.id === subGroupId);
      if (subIdx !== -1) {
        const sub = g.subGroups[subIdx];
        return {
          ...g,
          chats: [...g.chats, ...sub.chats],
          subGroups: [...g.subGroups.filter(s => s.id !== subGroupId), ...sub.subGroups],
        };
      }
      return g;
    }));
  };

  const handleCreateGroup = () => {
    const customGroup: CustomGroupInfo = {
      id: `group-${Date.now()}`,
      title: `Group ${groups.length + 1}`,
    };
    setCustomGroups((prev) => {
      const next = [...prev, customGroup];
      saveCustomGroups(next);
      return next;
    });
    const newGroup: ChatGroup = {
      ...customGroup,
      chats: [],
      subGroups: [],
      isCollapsed: false,
      custom: true,
    };
    setGroups(prev => [...prev, newGroup]);
  };

  const handleCreateChat = () => {
    onNewTask();
  };

  const handleToggleChatChildren = (chatId: string) => {
    setExpandedChatIds((prev) => {
      const next = new Set(prev);
      if (next.has(chatId)) next.delete(chatId);
      else next.add(chatId);
      return next;
    });
  };

  const isChatChildrenExpanded = (chatId: string) => expandedChatIds.has(chatId);

  const allSortableIds = [
    ...getAllGroupDragIds(groups),
    ...getAllChatIds(groups),
  ];

  const collisionDetection = createCustomCollision(activeType);
  const accountName = account?.display_name || account?.email || 'Rumi';
  const accountPlan = account?.plan_label || 'Rumi Account';
  const accountInitial = account?.initial || accountName.charAt(0).toUpperCase();
  const accountIcon = account?.avatar_url || '';
  const accountIconIsImage = /^(https?:|data:image|\/)/.test(accountIcon);
  const compactChats = flattenChats(groups);

  if (isCompact) {
    return (
      <div className="flex h-full w-full flex-col items-center bg-[#09090b] text-zinc-400">
        <div className="flex w-full flex-col items-center gap-1 border-b border-zinc-800/60 px-1.5 py-2">
          {onRestore && (
            <button
              type="button"
              onClick={onRestore}
              className="flex h-9 w-9 items-center justify-center rounded-md text-zinc-500 transition-colors hover:bg-zinc-800 hover:text-zinc-100"
              title="RumiDP を開く"
              aria-label="RumiDP を開く"
            >
              <PanelLeftOpen size={16} />
            </button>
          )}
          <button
            onClick={handleCreateChat}
            className="flex h-9 w-9 items-center justify-center rounded-md text-zinc-500 transition-colors hover:bg-zinc-800 hover:text-zinc-100"
            title="New Chat"
            aria-label="New Chat"
          >
            <MessageSquarePlus size={16} />
          </button>
          <button
            onClick={handleCreateGroup}
            className="flex h-9 w-9 items-center justify-center rounded-md text-zinc-500 transition-colors hover:bg-zinc-800 hover:text-zinc-100"
            title="New Group"
            aria-label="New Group"
          >
            <FolderPlus size={16} />
          </button>
        </div>

        <div className="flex min-h-0 w-full flex-1 flex-col items-center gap-1.5 overflow-y-auto px-1.5 py-2">
          {compactChats.map((chat) => {
            const isActive = activeChatId === chat.id;
            return (
              <button
                key={chat.id}
                type="button"
                onClick={() => onChatSelect(chat.id)}
                className={cn(
                  "relative flex h-10 w-10 items-center justify-center rounded-md transition-colors",
                  isActive ? "bg-zinc-800 text-zinc-100" : "text-zinc-500 hover:bg-zinc-800/70 hover:text-zinc-100"
                )}
                title={chat.title}
                aria-label={chat.title}
              >
                <MessageSquare size={17} strokeWidth={1.9} />
                {isActive && <span className="absolute left-0 h-5 w-0.5 rounded-r bg-emerald-400" />}
              </button>
            );
          })}
        </div>

        <div className="flex w-full flex-col items-center border-t border-zinc-800/60 px-1.5 py-2">
          <button
            type="button"
            onClick={onSettingsClick}
            className="flex h-9 w-9 items-center justify-center rounded-md text-zinc-500 transition-colors hover:bg-zinc-800 hover:text-zinc-100"
            title="Settings"
            aria-label="Settings"
          >
            <Settings size={15} />
          </button>
        </div>
      </div>
    );
  }

  return (
    <DndContext
      sensors={sensors}
      collisionDetection={collisionDetection}
      onDragStart={handleDragStart}
      onDragOver={handleDragOver}
      onDragEnd={handleDragEnd}
    >
      <div className="relative flex flex-col h-full min-w-0">
        {/* Top action bar */}
        <div className="flex flex-col gap-1 px-3 py-2 border-b border-zinc-800/60 flex-shrink-0">
          <div className="flex h-8 items-center justify-between gap-2 px-2.5">
            <span className="text-xs font-semibold tracking-wide text-zinc-400">RumiDP</span>
            {onMinimize && (
              <button
                type="button"
                onClick={onMinimize}
                className="flex h-7 w-7 items-center justify-center rounded-md text-zinc-500 transition-colors hover:bg-zinc-800 hover:text-zinc-100"
                title="RumiDP を閉じる"
                aria-label="RumiDP を閉じる"
              >
                <PanelLeftClose size={15} />
              </button>
            )}
          </div>
          <button
            onClick={handleCreateChat}
            className="flex w-full items-center gap-2 rounded-md px-2.5 py-1.5 text-left text-xs font-medium text-zinc-400 transition-colors hover:bg-zinc-800 hover:text-zinc-100"
            title="New Chat"
          >
            <MessageSquarePlus size={14} />
            <span>New Chat</span>
          </button>
          <button
            onClick={handleCreateGroup}
            className="flex w-full items-center gap-2 rounded-md px-2.5 py-1.5 text-left text-xs font-medium text-zinc-400 transition-colors hover:bg-zinc-800 hover:text-zinc-100"
            title="New Group"
          >
            <FolderPlus size={14} />
            <span>New Group</span>
          </button>
        </div>

        {/* Columns */}
        <SortableContext items={allSortableIds} strategy={verticalListSortingStrategy}>
          <div className="flex flex-1 flex-col overflow-x-hidden overflow-y-auto pb-12">
            {groups.map((group) => (
              <DraggableColumnHandle key={group.id} group={group}>
                {(dragHandleProps) => (
                  <DroppableColumn
                    group={group}
                    activeChatId={activeChatId}
                    onChatSelect={onChatSelect}
                    onNewTask={handleNewTaskInGroup}
                    onSettingsClick={onSettingsClick}
                    onRename={handleRenameGroup}
                    onToggleCollapse={handleToggleCollapse}
                    onChatRename={handleRenameChat}
                    onUngroup={handleUngroup}
                    onToggleChatChildren={handleToggleChatChildren}
                    isChatChildrenExpanded={isChatChildrenExpanded}
                    isDraggedOver={overColumnId === group.id}
                    isDragging={activeColumnDrag?.id === group.id}
                    dragHandleProps={dragHandleProps}
                  />
                )}
              </DraggableColumnHandle>
            ))}

            {activeColumnDrag && <ExtractDropZone />}
          </div>
        </SortableContext>

        {/* Fixed Account Bar */}
        <div className="absolute bottom-0 left-0 right-0 h-12 px-3 border-t border-zinc-800/60 bg-[#09090b]/95 backdrop-blur-sm z-30 flex items-center">
          <div className="flex items-center gap-2.5 px-1 w-full">
            {accountIcon && accountIconIsImage ? (
              <img src={accountIcon} alt="" className="w-7 h-7 rounded-full object-cover flex-shrink-0 bg-zinc-800" />
            ) : (
              <div className="w-7 h-7 rounded-full bg-gradient-to-tr from-zinc-700 to-zinc-600 flex-shrink-0 flex items-center justify-center text-white text-[10px] font-medium">
                {accountIcon || accountInitial}
              </div>
            )}
            <div className="flex-1 overflow-hidden min-w-0">
              <p className="text-xs font-medium text-zinc-200 truncate">{accountName}</p>
              <p className="text-[10px] text-zinc-500 truncate">{accountPlan}</p>
            </div>
            <button
              onClick={onSettingsClick}
              className="p-1.5 hover:bg-zinc-800 rounded-md transition-colors text-zinc-500 hover:text-zinc-300 flex-shrink-0"
              title="Settings"
            >
              <Settings size={14} />
            </button>
          </div>
        </div>
      </div>

      <DragOverlay dropAnimation={{ sideEffects: defaultDropAnimationSideEffects({ styles: { active: { opacity: '0.3' } } }) }}>
        {activeColumnDrag ? (
          <div className="w-[260px] h-10 flex items-center px-4 border border-emerald-500/50 bg-zinc-900 rounded-lg shadow-2xl">
            <Folder size={16} className="text-emerald-400 mr-2" />
            <span className="truncate text-sm text-zinc-100 font-medium">{activeColumnDrag.title}</span>
          </div>
        ) : activeChat ? (
          <div className="w-[220px] flex items-center gap-2 px-3 py-2 rounded-lg bg-zinc-800 border border-emerald-500/50 shadow-2xl">
            <GripVertical size={12} className="text-zinc-500" />
            {activeChat.type === 'research' ? <Globe size={14} className="text-zinc-400" /> :
             activeChat.type === 'code' ? <Terminal size={14} className="text-zinc-400" /> :
             <MessageSquare size={14} className="text-zinc-400" />}
            <span className="text-sm truncate text-zinc-100">{activeChat.title}</span>
          </div>
        ) : null}
      </DragOverlay>
    </DndContext>
  );
}
