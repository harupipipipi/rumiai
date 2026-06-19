import 'dart:async';

import 'package:flutter/material.dart';
import 'package:uuid/uuid.dart';

import '../settings/api_config_store.dart';
import '../settings/settings_screen.dart';
import '../app_theme.dart';
import 'chat_drawer.dart';
import 'chat_models.dart';
import 'chat_store.dart';
import 'composer_bar.dart';
import 'message_view.dart';
import 'openai_client.dart';

class ChatScreen extends StatefulWidget {
  const ChatScreen({
    super.key,
    required this.store,
    required this.configStore,
  });

  final ChatStore store;
  final ApiConfigStore configStore;

  @override
  State<ChatScreen> createState() => _ChatScreenState();
}

class _ChatScreenState extends State<ChatScreen> {
  final _uuid = const Uuid();
  final _scrollController = ScrollController();
  ApiConfig? _apiConfig;
  OpenAiClient? _client;
  bool _busy = false;
  bool _streaming = false;
  late Future<void> _initFuture;

  @override
  void initState() {
    super.initState();
    _initFuture = _init();
    _scrollController.addListener(_onScroll);
  }

  @override
  void dispose() {
    _scrollController.removeListener(_onScroll);
    _scrollController.dispose();
    _client?.close();
    super.dispose();
  }

  Future<void> _init() async {
    try {
      await widget.store.load();
      _apiConfig = await widget.configStore.loadApi();
      final active = widget.store.active;
      if (active == null) {
        await widget.store.createAndPersist();
      }
    } catch (error, stack) {
      debugPrint('Rumi init error: $error\n$stack');
    }
    if (mounted) setState(() {});
  }

  void _onScroll() {
    // intentionally simple; auto-scroll handles new content
  }

  void _scrollToBottom({bool animate = true}) {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!_scrollController.hasClients) return;
      final max = _scrollController.position.maxScrollExtent;
      if (animate) {
        _scrollController.animateTo(max,
            duration: const Duration(milliseconds: 180),
            curve: Curves.easeOut);
      } else {
        _scrollController.jumpTo(max);
      }
    });
  }

  Future<void> _newChat() async {
    await widget.store.createAndPersist();
    if (mounted) setState(() {});
  }

  Future<void> _select(String id) async {
    await widget.store.select(id);
    if (mounted) setState(() {});
  }

  Future<void> _delete(String id) async {
    await widget.store.delete(id);
    if (mounted) setState(() {});
  }

  Future<void> _pin(String id) async {
    await widget.store.togglePin(id);
    if (mounted) setState(() {});
  }

  Future<void> _rename(String id) async {
    final convo = widget.store.conversations.firstWhere((c) => c.id == id);
    final controller = TextEditingController(text: convo.title);
    final result = await showDialog<String>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('名前を変更'),
        content: TextField(
          controller: controller,
          autofocus: true,
          decoration: const InputDecoration(hintText: 'チャット名'),
        ),
        actions: [
          TextButton(
              onPressed: () => Navigator.pop(context),
              child: const Text('キャンセル')),
          FilledButton(
            onPressed: () => Navigator.pop(context, controller.text.trim()),
            child: const Text('保存'),
          ),
        ],
      ),
    );
    if (result != null) {
      await widget.store.rename(id, result);
      if (mounted) setState(() {});
    }
  }

  void _openSettings() async {
    await Navigator.of(context).push(MaterialPageRoute(
      builder: (_) => SettingsScreen(
        configStore: widget.configStore,
        onApiChanged: (next) {
          setState(() => _apiConfig = next);
        },
      ),
    ));
    // refresh config after returning
    final refreshed = await widget.configStore.loadApi();
    if (mounted) setState(() => _apiConfig = refreshed);
  }

  Future<void> _send(String text) async {
    if (text.trim().isEmpty) return;
    final config = _apiConfig;
    if (config == null || !config.isConfigured) {
      _promptConfigure();
      return;
    }

    final convo = widget.store.active ?? await widget.store.createAndPersist();
    final userMsg = ChatMessage(
      id: _uuid.v4(),
      role: ChatRole.user,
      content: text,
      createdAt: DateTime.now(),
    );
    await widget.store.addMessage(convo.id, userMsg);
    final assistantId = _uuid.v4();
    final assistantMsg = ChatMessage(
      id: assistantId,
      role: ChatRole.assistant,
      content: '',
      createdAt: DateTime.now(),
      pending: true,
    );
    await widget.store.addMessage(convo.id, assistantMsg);
    setState(() {
      _busy = true;
      _streaming = true;
    });
    _scrollToBottom();

    _client?.close();
    _client = OpenAiClient();
    final history = List<ChatMessage>.from(convo.messages)
      ..removeWhere((m) => m.id == assistantId);
    final buffer = StringBuffer();
    try {
      await for (final delta
          in _client!.streamChat(config: config, history: history)) {
        buffer.write(delta);
        await widget.store.updateMessage(convo.id, assistantId, buffer.toString(),
            pending: true);
        if (mounted) setState(() {});
        _scrollToBottom(animate: false);
      }
      await widget.store.updateMessage(convo.id, assistantId, buffer.toString(),
          pending: false);
    } catch (error) {
      final message = buffer.toString().isEmpty
          ? 'エラー: ${_friendlyError(error)}'
          : '${buffer.toString()}\n\n_エラー: ${_friendlyError(error)}_';
      await widget.store.updateMessage(convo.id, assistantId, message,
          pending: false, error: true);
    } finally {
      if (mounted) {
        setState(() {
          _busy = false;
          _streaming = false;
        });
      }
    }
    if (mounted) setState(() {});
  }

  void _stop() {
    _client?.cancel();
    setState(() => _streaming = false);
  }

  void _promptConfigure() {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: const Text('APIを設定してください'),
        action: SnackBarAction(
          label: '設定',
          onPressed: _openSettings,
        ),
      ),
    );
  }

  String _friendlyError(Object error) {
    if (error is OpenAiException) return error.message;
    return '$error';
  }

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<void>(
      future: _initFuture,
      builder: (context, snapshot) {
        return Scaffold(
          drawer: Drawer(
            width: 320,
            child: ChatDrawer(
              conversations: widget.store.conversations,
              activeId: widget.store.active?.id,
              onNewChat: () {
                Navigator.of(context).pop();
                _newChat();
              },
              onSelect: (id) {
                Navigator.of(context).pop();
                _select(id);
              },
              onDelete: _delete,
              onRename: _rename,
              onPin: _pin,
              onOpenSettings: () {
                Navigator.of(context).pop();
                _openSettings();
              },
            ),
          ),
          appBar: AppBar(
            leading: Builder(
              builder: (context) => IconButton(
                tooltip: 'チャット一覧',
                icon: const Icon(Icons.menu),
                onPressed: () => Scaffold.of(context).openDrawer(),
              ),
            ),
            title: Text(
              widget.store.active?.title ?? 'Rumi',
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
            ),
            actions: [
              IconButton(
                tooltip: '新規チャット',
                icon: const Icon(Icons.add_comment_outlined),
                onPressed: _newChat,
              ),
              IconButton(
                tooltip: '設定',
                icon: const Icon(Icons.settings_outlined),
                onPressed: _openSettings,
              ),
            ],
          ),
          body: _buildBody(snapshot),
        );
      },
    );
  }

  Widget _buildBody(AsyncSnapshot<void> snapshot) {
    if (snapshot.connectionState != ConnectionState.done) {
      return const Center(child: CircularProgressIndicator());
    }
    final convo = widget.store.active;
    if (convo == null || convo.messages.isEmpty) {
      return _EmptyState(onSuggest: _send, busy: _busy);
    }
    return Column(
      children: [
        Expanded(
          child: ListView.builder(
            controller: _scrollController,
            padding: const EdgeInsets.symmetric(vertical: 12),
            itemCount: convo.messages.length,
            itemBuilder: (context, index) {
              final message = convo.messages[index];
              return MessageView(
                  key: ValueKey(message.id), message: message);
            },
          ),
        ),
        ComposerBar(
          onSend: _send,
          onStop: _stop,
          busy: _streaming,
        ),
      ],
    );
  }
}

class _EmptyState extends StatelessWidget {
  const _EmptyState({required this.onSuggest, required this.busy});
  final ValueChanged<String> onSuggest;
  final bool busy;

  static const _suggestions = [
    '今日のニュースを要約して',
    'PythonでFizzBuzzを書いて',
    'アイデア出しを手伝って',
    'この文章を校正して',
  ];

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colors = theme.extension<RumiColors>() ?? RumiColors.dark;
    return Column(
      children: [
        Expanded(
          child: Center(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Container(
                  width: 56,
                  height: 56,
                  decoration: BoxDecoration(
                    color: colors.accent,
                    borderRadius: BorderRadius.circular(16),
                  ),
                  child: const Icon(Icons.auto_awesome,
                      color: Colors.white, size: 28),
                ),
                const SizedBox(height: 16),
                Text('Rumiへようこそ',
                    style: theme.textTheme.titleLarge
                        ?.copyWith(fontWeight: FontWeight.w700)),
                const SizedBox(height: 6),
                Text('何でも聞いてください。スマホ単体でも動作します。',
                    style: theme.textTheme.bodySmall),
                const SizedBox(height: 24),
                Wrap(
                  spacing: 8,
                  runSpacing: 8,
                  alignment: WrapAlignment.center,
                  children: _suggestions
                      .map((s) => ActionChip(
                            label: Text(s),
                            onPressed: busy ? null : () => onSuggest(s),
                          ))
                      .toList(),
                ),
              ],
            ),
          ),
        ),
        ComposerBar(onSend: onSuggest, onStop: () {}, busy: busy),
      ],
    );
  }
}
