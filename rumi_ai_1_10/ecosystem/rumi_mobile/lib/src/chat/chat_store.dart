import 'dart:convert';

import 'package:shared_preferences/shared_preferences.dart';
import 'package:uuid/uuid.dart';

import 'chat_models.dart';

const _kConversationsKey = 'rumi_chat.conversations.v1';
const _kActiveConversationKey = 'rumi_chat.active_id.v1';

class ChatStore {
  ChatStore();

  final _uuid = const Uuid();
  List<Conversation> _conversations = const [];
  String? _activeId;

  List<Conversation> get conversations =>
      List<Conversation>.unmodifiable(_conversations);

  Conversation? get active =>
      _activeId == null ? null : _firstWhere(_conversations, (c) => c.id == _activeId);

  Future<void> load() async {
    final prefs = await SharedPreferences.getInstance();
    final raw = prefs.getString(_kConversationsKey);
    if (raw != null && raw.trim().isNotEmpty) {
      try {
        final list = jsonDecode(raw) as List;
        _conversations = list
            .map((m) => Conversation.fromJson(m as Map<String, dynamic>))
            .toList();
      } catch (_) {
        _conversations = const [];
      }
    }
    _activeId = prefs.getString(_kActiveConversationKey);
    if (_activeId != null &&
        !_conversations.any((c) => c.id == _activeId)) {
      _activeId = _conversations.isEmpty ? null : _conversations.first.id;
    }
    if (_activeId == null && _conversations.isNotEmpty) {
      _activeId = _conversations.first.id;
    }
  }

  Future<void> _persist() async {
    final prefs = await SharedPreferences.getInstance();
    final raw = jsonEncode(_conversations.map((c) => c.toJson()).toList());
    await prefs.setString(_kConversationsKey, raw);
    if (_activeId != null) {
      await prefs.setString(_kActiveConversationKey, _activeId!);
    } else {
      await prefs.remove(_kActiveConversationKey);
    }
  }

  Conversation newConversation() {
    final convo = Conversation(
      id: _uuid.v4(),
      title: '新しいチャット',
      messages: <ChatMessage>[],
      createdAt: DateTime.now(),
      updatedAt: DateTime.now(),
    );
    _conversations = [convo, ..._conversations];
    _activeId = convo.id;
    return convo;
  }

  Future<Conversation> createAndPersist() async {
    final convo = newConversation();
    await _persist();
    return convo;
  }

  Future<void> select(String id) async {
    _activeId = id;
    await _persist();
  }

  Future<void> delete(String id) async {
    _conversations = _conversations.where((c) => c.id != id).toList();
    if (_activeId == id) {
      _activeId = _conversations.isEmpty ? null : _conversations.first.id;
    }
    await _persist();
  }

  Future<void> rename(String id, String title) async {
    final convo = _firstWhere(_conversations, (c) => c.id == id);
    if (convo == null) return;
    convo.title = title.trim().isEmpty ? '新しいチャット' : title.trim();
    convo.updatedAt = DateTime.now();
    await _persist();
  }

  Future<void> togglePin(String id) async {
    final convo = _firstWhere(_conversations, (c) => c.id == id);
    if (convo == null) return;
    convo.pinned = !convo.pinned;
    await _persist();
  }

  Future<void> addMessage(String conversationId, ChatMessage message) async {
    final convo = _firstWhere(_conversations, (c) => c.id == conversationId);
    if (convo == null) return;
    convo.messages.add(message);
    convo.updatedAt = DateTime.now();
    if (convo.title == '新しいチャット' && message.role == ChatRole.user && message.content.trim().isNotEmpty) {
      convo.title = _deriveTitle(message.content);
    }
    await _persist();
  }

  Future<void> updateMessage(
      String conversationId, String messageId, String content,
      {bool? pending, bool? error}) async {
    final convo = _firstWhere(_conversations, (c) => c.id == conversationId);
    if (convo == null) return;
    final msg = _firstWhere(convo.messages, (m) => m.id == messageId);
    if (msg == null) return;
    msg.content = content;
    if (pending != null) msg.pending = pending;
    if (error != null) msg.error = error;
    convo.updatedAt = DateTime.now();
    await _persist();
  }

  Future<void> persist() => _persist();

  String _deriveTitle(String content) {
    final single = content.replaceAll('\n', ' ').trim();
    if (single.length <= 32) return single;
    return '${single.substring(0, 30)}…';
  }

  T? _firstWhere<T>(Iterable<T> items, bool Function(T) test) {
    for (final item in items) {
      if (test(item)) return item;
    }
    return null;
  }
}
