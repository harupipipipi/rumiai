import 'package:flutter/material.dart';

import '../domain/conversation_locator.dart';
import 'chat_models.dart';

class ChatDrawer extends StatelessWidget {
  const ChatDrawer({
    super.key,
    required this.conversations,
    required this.activeId,
    required this.onNewChat,
    required this.onSelect,
    required this.onDelete,
    required this.onRename,
    required this.onPin,
    required this.onOpenSettings,
    this.pcConnected = false,
  });

  final List<Conversation> conversations;
  final String? activeId;
  final VoidCallback onNewChat;
  final ValueChanged<String> onSelect;
  final ValueChanged<String> onDelete;
  final ValueChanged<String> onRename;
  final ValueChanged<String> onPin;
  final VoidCallback onOpenSettings;
  final bool pcConnected;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);

    final localPinned =
        conversations.where((c) => c.pinned && !_isPc(c)).toList();
    final localOthers =
        conversations.where((c) => !c.pinned && !_isPc(c)).toList();
    final pcPinned = conversations.where((c) => c.pinned && _isPc(c)).toList();
    final pcOthers = conversations.where((c) => !c.pinned && _isPc(c)).toList();

    return SafeArea(
      child: Column(
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 16, 12, 8),
            child: Row(
              children: [
                Expanded(
                  child: Text('Rumi',
                      style: theme.textTheme.titleLarge
                          ?.copyWith(fontWeight: FontWeight.w700)),
                ),
                IconButton(
                  tooltip: '新規チャット',
                  icon: const Icon(Icons.edit_square),
                  onPressed: onNewChat,
                ),
              ],
            ),
          ),
          Padding(
            padding: const EdgeInsets.fromLTRB(12, 0, 12, 8),
            child: FilledButton.icon(
              onPressed: onNewChat,
              icon: const Icon(Icons.add),
              label: const Text('新規チャット'),
              style: FilledButton.styleFrom(
                minimumSize: const Size.fromHeight(46),
                shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(12)),
              ),
            ),
          ),
          Expanded(
            child: ListView(
              padding: const EdgeInsets.symmetric(horizontal: 8),
              children: [
                if (pcPinned.isNotEmpty || pcOthers.isNotEmpty) ...[
                  _GroupHeader('PC会話'),
                  for (final c in pcPinned)
                    _ConversationTile(
                      conversation: c,
                      selected: c.id == activeId,
                      onSelect: () => onSelect(c.id),
                      onDelete: () => onDelete(c.id),
                      onRename: () => onRename(c.id),
                      onPin: () => onPin(c.id),
                      offline: !pcConnected,
                    ),
                  for (final c in pcOthers)
                    _ConversationTile(
                      conversation: c,
                      selected: c.id == activeId,
                      onSelect: () => onSelect(c.id),
                      onDelete: () => onDelete(c.id),
                      onRename: () => onRename(c.id),
                      onPin: () => onPin(c.id),
                      offline: !pcConnected,
                    ),
                  const SizedBox(height: 8),
                ],
                if (localPinned.isNotEmpty) ...[
                  _GroupHeader('ピン留め'),
                  for (final c in localPinned)
                    _ConversationTile(
                      conversation: c,
                      selected: c.id == activeId,
                      onSelect: () => onSelect(c.id),
                      onDelete: () => onDelete(c.id),
                      onRename: () => onRename(c.id),
                      onPin: () => onPin(c.id),
                    ),
                  const SizedBox(height: 8),
                ],
                _GroupHeader('チャット'),
                if (localOthers.isEmpty &&
                    localPinned.isEmpty &&
                    pcOthers.isEmpty &&
                    pcPinned.isEmpty)
                  const Padding(
                    padding: EdgeInsets.all(24),
                    child: Center(
                      child: Text('チャット履歴がありません',
                          style: TextStyle(color: Colors.grey)),
                    ),
                  ),
                for (final c in localOthers)
                  _ConversationTile(
                    conversation: c,
                    selected: c.id == activeId,
                    onSelect: () => onSelect(c.id),
                    onDelete: () => onDelete(c.id),
                    onRename: () => onRename(c.id),
                    onPin: () => onPin(c.id),
                  ),
              ],
            ),
          ),
          const Divider(),
          ListTile(
            leading: const Icon(Icons.settings_outlined),
            title: const Text('設定'),
            onTap: onOpenSettings,
          ),
        ],
      ),
    );
  }

  bool _isPc(Conversation c) => c.authority == ConversationAuthorityKind.pc;
}

class _GroupHeader extends StatelessWidget {
  const _GroupHeader(this.text);
  final String text;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(12, 12, 12, 4),
      child: Text(text,
          style: const TextStyle(
              fontSize: 12, fontWeight: FontWeight.w600, color: Colors.grey)),
    );
  }
}

class _ConversationTile extends StatelessWidget {
  const _ConversationTile({
    required this.conversation,
    required this.selected,
    required this.onSelect,
    required this.onDelete,
    required this.onRename,
    required this.onPin,
    this.offline = false,
  });

  final Conversation conversation;
  final bool selected;
  final VoidCallback onSelect;
  final VoidCallback onDelete;
  final VoidCallback onRename;
  final VoidCallback onPin;
  final bool offline;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Opacity(
      opacity: offline ? 0.5 : 1.0,
      child: Material(
        color: selected
            ? theme.colorScheme.primaryContainer.withValues(alpha: 0.5)
            : Colors.transparent,
        borderRadius: BorderRadius.circular(10),
        child: ListTile(
          shape:
              RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
          leading: Icon(
            conversation.pinned ? Icons.push_pin : Icons.chat_bubble_outline,
            size: 18,
            color: offline ? Colors.red.shade300 : Colors.grey,
          ),
          title: Text(
            conversation.title,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: offline ? const TextStyle(color: Colors.grey) : null,
          ),
          subtitle: Text(
            conversation.preview,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: TextStyle(fontSize: 12, color: offline ? Colors.grey : null),
          ),
          trailing: PopupMenuButton<String>(
            icon: const Icon(Icons.more_horiz, size: 18),
            onSelected: (value) {
              switch (value) {
                case 'rename':
                  onRename();
                  break;
                case 'pin':
                  onPin();
                  break;
                case 'delete':
                  onDelete();
                  break;
              }
            },
            itemBuilder: (_) => [
              const PopupMenuItem(value: 'rename', child: Text('名前を変更')),
              PopupMenuItem(
                  value: 'pin',
                  child: Text(conversation.pinned ? 'ピン留め解除' : 'ピン留め')),
              const PopupMenuItem(
                  value: 'delete',
                  child: Text('削除', style: TextStyle(color: Colors.redAccent))),
            ],
          ),
          onTap: onSelect,
        ),
      ),
    );
  }
}
