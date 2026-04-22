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
  GripVertical, FolderOpen, Folder, FolderPlus, MessageSquarePlus, X,
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
};

export type ChatGroup = {
  id: string;
  title: string;
  chats: ChatItem[];
  subGroups: ChatGroup[];
  isCollapsed?: boolean;
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

function buildGroupsFromChats(chatItems: ChatItem[]): ChatGroup[] {
  const buckets: Record<'today' | 'recent' | 'older', ChatItem[]> = {
    today: [],
    recent: [],
    older: [],
  };

  chatItems.forEach((chat) => {
    const normalized = {
      ...chat,
      type: classifyChatType(chat),
    };
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

  return groups.filter((group) => group.chats.length > 0);
}

// ============================================================
// Utility functions
// ============================================================

function countChats(group: ChatGroup): number {
  let count = group.chats.length;
  for (const sub of group.subGroups) count += countChats(sub);
  return count;
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
    ids.push(...g.chats.map(c => c.id));
    ids.push(...getAllChatIds(g.subGroups));
  }
  return ids;
}

function getAllGroupDragIds(groups: ChatGroup[]): string[] {
  const ids: string[] = [];
  for (const g of groups) {
    ids.push(`drag-col-${g.id}`);
    ids.push(...getAllGroupDragIds(g.subGroups));
  }
  return ids;
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
  isActive: boolean;
  onClick: () => void;
  onRename: (id: string, newTitle: string) => void;
  depth?: number;
}

function SortableChatItem({ chat, isActive, onClick, onRename, depth = 0 }: SortableChatItemProps) {
  const [isEditing, setIsEditing] = useState(false);
  const [title, setTitle] = useState(chat.title);

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
    <div
      ref={setNodeRef}
      style={style}
      {...attributes}
      {...listeners}
      className={cn(
        "w-full flex items-center gap-2 pr-2 py-1.5 rounded-md text-left group/chat transition-colors cursor-grab active:cursor-grabbing outline-none",
        isActive ? "bg-zinc-800/80" : "hover:bg-zinc-800/50",
        isDragging && "ring-1 ring-emerald-500/50 z-50"
      )}
      onClick={() => { if (!isEditing) onClick(); }}
      onDoubleClick={(e) => { e.stopPropagation(); setIsEditing(true); }}
      tabIndex={0}
    >
      <GripVertical size={12} className="text-zinc-700 group-hover/chat:text-zinc-500 flex-shrink-0" />
      {icon}
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
  depth: number;
}

function SubGroup({ group, activeChatId, onChatSelect, onChatRename, onToggleCollapse, onRenameGroup, onUngroup, depth }: SubGroupProps) {
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

      {!group.isCollapsed && (
        <div>
          <SortableContext items={group.chats.map(c => c.id)} strategy={verticalListSortingStrategy}>
            {group.chats.map(chat => (
              <SortableChatItem
                key={chat.id}
                chat={chat}
                isActive={activeChatId === chat.id}
                onClick={() => onChatSelect(chat.id)}
                onRename={onChatRename}
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
              depth={depth + 1}
            />
          ))}
        </div>
      )}
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
  isDraggedOver: boolean;
  isDragging: boolean;
}

function DroppableColumn({ group, activeChatId, onChatSelect, onNewTask, onSettingsClick, onRename, onToggleCollapse, onChatRename, onUngroup, isDraggedOver, isDragging }: DroppableColumnProps) {
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
        "flex-shrink-0 border-r border-zinc-800/60 bg-[#09090b] flex flex-col h-full transition-all duration-300",
        group.isCollapsed ? "w-[48px]" : "w-[280px]",
        isDraggedOver && !isDragging && "ring-2 ring-inset ring-emerald-500/50 bg-emerald-500/[0.08]",
      )}
    >
      {/* Header */}
      <div
        onClick={() => onToggleCollapse(group.id)}
        className={cn(
          "h-12 flex items-center px-3 border-b border-zinc-800/60 justify-between hover:bg-zinc-900/50 transition-colors cursor-pointer group/colheader",
          group.isCollapsed && "px-0 justify-center",
          isDraggedOver && !isDragging && "bg-emerald-500/15"
        )}
      >
        <div className="flex items-center gap-2 text-zinc-100 font-medium flex-1 min-w-0">
          <ChevronRight size={14} className={cn("transition-transform duration-200 text-zinc-500 flex-shrink-0", !group.isCollapsed && "rotate-90")} />
          {!group.isCollapsed && (
            <>
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
            </>
          )}
        </div>
        {!group.isCollapsed && (
          <div className="flex items-center gap-1 opacity-0 group-hover/colheader:opacity-100 transition-opacity" onClick={(e) => e.stopPropagation()}>
            <button onClick={() => onNewTask(group.id)} className="p-1 text-zinc-500 hover:text-emerald-400 transition-colors" title="New chat in group">
              <Plus size={14} />
            </button>
          </div>
        )}
      </div>

      {/* Content */}
      {!group.isCollapsed && (
        <div className="flex-1 overflow-y-auto px-1 py-2 space-y-0.5">
          <SortableContext items={group.chats.map(c => c.id)} strategy={verticalListSortingStrategy}>
            {group.chats.map(chat => (
              <SortableChatItem
                key={chat.id}
                chat={chat}
                isActive={activeChatId === chat.id}
                onClick={() => onChatSelect(chat.id)}
                onRename={onChatRename}
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
      )}
    </div>
  );
}

// ============================================================
// DraggableColumnHandle
// ============================================================

function DraggableColumnHandle({ group, children }: { group: ChatGroup; children: React.ReactNode }) {
  const { attributes, listeners, setNodeRef, isDragging } = useSortable({
    id: `drag-col-${group.id}`,
    data: { type: 'ColumnDrag', group },
  });

  return (
    <div ref={setNodeRef} className={cn("relative", isDragging && "opacity-30")}>
      <div
        {...attributes}
        {...listeners}
        className="absolute top-0 left-0 right-0 h-12 z-20 cursor-grab active:cursor-grabbing"
      />
      <div>{children}</div>
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
  onChatSelect: (chatId: string) => void;
  onNewTask: () => void;
  onSettingsClick: () => void;
}

export function HistoryBoard({ activeChatId, chatItems, onChatSelect, onNewTask, onSettingsClick }: HistoryBoardProps) {
  const [groups, setGroups] = useState<ChatGroup[]>(() => buildGroupsFromChats(chatItems));

  useEffect(() => {
    setGroups(buildGroupsFromChats(chatItems));
  }, [chatItems]);

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
    const newGroup: ChatGroup = {
      id: `group-${Date.now()}`,
      title: `Group ${groups.length + 1}`,
      chats: [],
      subGroups: [],
      isCollapsed: false,
    };
    setGroups(prev => [...prev, newGroup]);
  };

  const handleCreateChat = () => {
    onNewTask();
  };

  const allSortableIds = [
    ...getAllGroupDragIds(groups),
    ...getAllChatIds(groups),
  ];

  const collisionDetection = createCustomCollision(activeType);

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
        <div className="flex items-center gap-1 px-3 py-2 border-b border-zinc-800/60 flex-shrink-0">
          <button
            onClick={handleCreateChat}
            className="flex items-center gap-1.5 px-2.5 py-1.5 text-xs font-medium text-zinc-400 hover:text-zinc-100 hover:bg-zinc-800 rounded-md transition-colors"
            title="New Chat"
          >
            <MessageSquarePlus size={14} />
            <span>New Chat</span>
          </button>
          <button
            onClick={handleCreateGroup}
            className="flex items-center gap-1.5 px-2.5 py-1.5 text-xs font-medium text-zinc-400 hover:text-zinc-100 hover:bg-zinc-800 rounded-md transition-colors"
            title="New Group"
          >
            <FolderPlus size={14} />
            <span>New Group</span>
          </button>
        </div>

        {/* Columns */}
        <SortableContext items={allSortableIds} strategy={verticalListSortingStrategy}>
          <div className="flex flex-1 overflow-x-auto overflow-y-hidden pb-12">
            {groups.map((group) => (
              <DraggableColumnHandle key={group.id} group={group}>
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
                  isDraggedOver={overColumnId === group.id}
                  isDragging={activeColumnDrag?.id === group.id}
                />
              </DraggableColumnHandle>
            ))}

            {activeColumnDrag && <ExtractDropZone />}
          </div>
        </SortableContext>

        {/* Fixed Account Bar */}
        <div className="absolute bottom-0 left-0 right-0 h-12 px-3 border-t border-zinc-800/60 bg-[#09090b]/95 backdrop-blur-sm z-30 flex items-center">
          <div className="flex items-center gap-2.5 px-1 w-full">
            <div className="w-7 h-7 rounded-full bg-gradient-to-tr from-zinc-700 to-zinc-600 flex-shrink-0 flex items-center justify-center text-white text-[10px] font-medium">
              U
            </div>
            <div className="flex-1 overflow-hidden min-w-0">
              <p className="text-xs font-medium text-zinc-200 truncate">User Account</p>
              <p className="text-[10px] text-zinc-500 truncate">Pro Plan</p>
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
