import 'dart:async';

import 'package:flutter/material.dart';

import 'canonical_conversation_client.dart';
import 'chat_models.dart';
import 'composer_bar.dart';
import 'message_view.dart';

typedef ConversationClientFactory = ConversationTransport Function(
  MobileChatConnection connection,
);

class ChatScreen extends StatefulWidget {
  const ChatScreen({
    super.key,
    this.connectionStore,
    this.clientFactory,
    this.transport,
  });

  final ChatConnectionStore? connectionStore;
  final ConversationClientFactory? clientFactory;
  final ConversationTransport? transport;

  @override
  State<ChatScreen> createState() => _ChatScreenState();
}

class _ChatScreenState extends State<ChatScreen> {
  final _messages = <ChatMessage>[];
  final _scrollController = ScrollController();
  late final ChatConnectionStore _connectionStore;
  ConversationTransport? _transport;
  String? _conversationId;
  String? _connectionError;
  bool _busy = false;
  bool _ownsTransport = false;
  int _sequence = 0;

  @override
  void initState() {
    super.initState();
    _connectionStore = widget.connectionStore ?? MobileChatConnectionStore();
    unawaited(_initialize());
  }

  Future<void> _initialize() async {
    if (widget.transport != null) {
      _transport = widget.transport;
      if (mounted) setState(() {});
      return;
    }
    try {
      final connection = await _connectionStore.load();
      if (connection == null) {
        _connectionError = 'ペアリング済みのチャット接続がありません。';
      } else {
        final factory = widget.clientFactory ??
            (value) => CanonicalConversationClient(connection: value);
        _transport = factory(connection);
        _ownsTransport = true;
      }
    } catch (_) {
      _connectionError = 'チャット接続を安全に読み込めませんでした。';
    }
    if (mounted) setState(() {});
  }

  String _id(String prefix) {
    _sequence += 1;
    return '$prefix-${DateTime.now().microsecondsSinceEpoch}-$_sequence';
  }

  Future<void> _send(String text) async {
    final transport = _transport;
    if (transport == null || _busy) return;
    final userId = _id('user');
    final assistantId = _id('assistant');
    setState(() {
      _busy = true;
      _connectionError = null;
      _messages.addAll([
        ChatMessage(id: userId, role: ChatRole.user, content: text),
        ChatMessage(
          id: assistantId,
          role: ChatRole.assistant,
          content: '',
          pending: true,
        ),
      ]);
    });
    _scrollToEnd();

    try {
      final conversationId =
          _conversationId ?? await transport.createConversation();
      _conversationId = conversationId;
      final revision = await transport.revision(conversationId);
      await for (final update in transport.send(
        conversationId: conversationId,
        text: text,
        clientMessageId: userId,
        expectedRevision: revision,
      )) {
        if (!mounted) return;
        switch (update.kind) {
          case CanonicalChatUpdateKind.delta:
            _updateAssistant(
              assistantId,
              (current) => current.copyWith(
                content: update.replace
                    ? update.content
                    : '${current.content}${update.content}',
              ),
            );
            break;
          case CanonicalChatUpdateKind.attention:
            _updateAssistant(
              assistantId,
              (current) => current.copyWith(content: update.content),
            );
            break;
          case CanonicalChatUpdateKind.error:
            _updateAssistant(
              assistantId,
              (current) => current.copyWith(
                content: update.content,
                pending: false,
                error: true,
              ),
            );
            break;
          case CanonicalChatUpdateKind.done:
            _updateAssistant(
              assistantId,
              (current) => current.copyWith(pending: false),
            );
            break;
        }
        _scrollToEnd();
      }
    } catch (_) {
      if (!mounted) return;
      _updateAssistant(
        assistantId,
        (current) => current.copyWith(
          content: current.content,
          pending: false,
          error: true,
        ),
      );
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  void _updateAssistant(
    String id,
    ChatMessage Function(ChatMessage current) update,
  ) {
    final index = _messages.indexWhere((message) => message.id == id);
    if (index < 0) return;
    setState(() => _messages[index] = update(_messages[index]));
  }

  Future<void> _stop() async {
    final transport = _transport;
    final conversationId = _conversationId;
    if (transport == null || conversationId == null) return;
    try {
      await transport.stop(conversationId);
    } finally {
      if (mounted) {
        setState(() {
          _busy = false;
          for (var index = 0; index < _messages.length; index += 1) {
            final message = _messages[index];
            if (message.pending) {
              _messages[index] = message.copyWith(pending: false);
            }
          }
        });
      }
    }
  }

  Future<void> _showOptions() async {
    final connection = await showModalBottomSheet<MobileChatConnection>(
      context: context,
      showDragHandle: true,
      isScrollControlled: true,
      builder: (context) => const _ConnectionSheet(),
    );
    if (connection == null) return;
    try {
      await _connectionStore.saveVerified(connection);
      if (!mounted) return;
      if (_ownsTransport) _transport?.close();
      final factory = widget.clientFactory ??
          (value) => CanonicalConversationClient(connection: value);
      setState(() {
        _transport = factory(connection);
        _ownsTransport = true;
        _connectionError = null;
        _conversationId = null;
      });
    } catch (_) {
      if (!mounted) return;
      setState(() => _connectionError = 'チャット接続を安全に保存できませんでした。');
    }
  }

  void _scrollToEnd() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!_scrollController.hasClients) return;
      _scrollController.animateTo(
        _scrollController.position.maxScrollExtent,
        duration: const Duration(milliseconds: 180),
        curve: Curves.easeOut,
      );
    });
  }

  @override
  void dispose() {
    _scrollController.dispose();
    if (_ownsTransport) _transport?.close();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final connected = _transport != null;
    return Scaffold(
      appBar: AppBar(title: const Text('Tobkiri チャット')),
      body: Column(
        children: [
          if (_connectionError != null)
            MaterialBanner(
              content: Text(_connectionError!),
              leading: const Icon(Icons.link_off),
              actions: [
                TextButton(
                  onPressed: () => unawaited(_showOptions()),
                  child: const Text('接続方法'),
                ),
              ],
            ),
          Expanded(
            child: _messages.isEmpty
                ? Center(
                    child: Text(
                      connected ? 'メッセージを送信して会話を始めましょう。' : 'チャット接続を待っています。',
                    ),
                  )
                : ListView.builder(
                    controller: _scrollController,
                    itemCount: _messages.length,
                    itemBuilder: (context, index) =>
                        MessageView(message: _messages[index]),
                  ),
          ),
          ComposerBar(
            busy: _busy,
            enabled: connected,
            onSend: (text) => unawaited(_send(text)),
            onStop: () => unawaited(_stop()),
            onAdd: () => unawaited(_showOptions()),
          ),
        ],
      ),
    );
  }
}

class _ConnectionSheet extends StatefulWidget {
  const _ConnectionSheet();

  @override
  State<_ConnectionSheet> createState() => _ConnectionSheetState();
}

class _ConnectionSheetState extends State<_ConnectionSheet> {
  final _url = TextEditingController();
  final _deviceId = TextEditingController();
  final _token = TextEditingController();
  String? _error;

  @override
  void dispose() {
    _url.dispose();
    _deviceId.dispose();
    _token.dispose();
    super.dispose();
  }

  void _save() {
    final connection = MobileChatConnection(
      baseUrl: _url.text.trim(),
      deviceId: _deviceId.text.trim(),
      token: _token.text.trim(),
      scopes: mobileChatScopes,
    );
    if (!connection.isValid) {
      setState(() => _error = 'PC URL、端末 ID、承認済みトークンを確認してください。');
      return;
    }
    Navigator.of(context).pop(connection);
  }

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      child: Padding(
        padding: EdgeInsets.fromLTRB(
          24,
          8,
          24,
          24 + MediaQuery.viewInsetsOf(context).bottom,
        ),
        child: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Text('承認済みチャット接続', style: Theme.of(context).textTheme.titleLarge),
              const SizedBox(height: 8),
              const Text(
                'PC のペアリング画面で発行された chat.read / chat.write '
                '専用の端末トークンだけを使用してください。',
              ),
              const SizedBox(height: 16),
              TextField(
                controller: _url,
                keyboardType: TextInputType.url,
                textInputAction: TextInputAction.next,
                decoration: const InputDecoration(
                  labelText: 'Tobkiri PC URL',
                  hintText: 'https://pc.example:8765',
                ),
              ),
              const SizedBox(height: 12),
              TextField(
                controller: _deviceId,
                textInputAction: TextInputAction.next,
                decoration: const InputDecoration(labelText: '端末 ID'),
              ),
              const SizedBox(height: 12),
              TextField(
                controller: _token,
                obscureText: true,
                autocorrect: false,
                enableSuggestions: false,
                onSubmitted: (_) => _save(),
                decoration: const InputDecoration(labelText: '端末トークン'),
              ),
              if (_error != null) ...[
                const SizedBox(height: 12),
                Text(
                  _error!,
                  style: TextStyle(color: Theme.of(context).colorScheme.error),
                ),
              ],
              const SizedBox(height: 16),
              FilledButton.icon(
                onPressed: _save,
                icon: const Icon(Icons.lock_outline),
                label: const Text('安全に保存して接続'),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
