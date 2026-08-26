import 'dart:async';

import 'package:flutter/material.dart';

import 'canonical_conversation_client.dart';
import 'chat_draft_store.dart';
import 'chat_models.dart';
import 'composer_bar.dart';
import 'message_view.dart';

typedef ConversationClientFactory = ConversationTransport Function(
    MobileChatConnection connection);

final class _ChatSubmission {
  _ChatSubmission({
    required this.text,
    required this.userId,
    required this.assistantId,
  });

  final String text;
  final String userId;
  final String assistantId;
  String? conversationId;
  int? expectedRevision;
  bool accepted = false;
}

class ChatScreen extends StatefulWidget {
  const ChatScreen({
    super.key,
    this.connectionStore,
    this.clientFactory,
    this.transport,
    this.draftStore,
    this.draftScope,
  });

  final ChatConnectionStore? connectionStore;
  final ConversationClientFactory? clientFactory;
  final ConversationTransport? transport;
  final ChatDraftStore? draftStore;
  final String? draftScope;

  @override
  State<ChatScreen> createState() => _ChatScreenState();
}

class _ChatScreenState extends State<ChatScreen> with WidgetsBindingObserver {
  final _messages = <ChatMessage>[];
  final _scrollController = ScrollController();
  late final ChatConnectionStore _connectionStore;
  late final ChatDraftStore _draftStore;
  ConversationTransport? _transport;
  String? _conversationId;
  String? _connectionError;
  String? _deliveryWarning;
  bool _busy = false;
  bool _ownsTransport = false;
  int _sequence = 0;
  String _draftScope = 'unpaired';
  String _draftText = '';
  Timer? _draftSaveTimer;
  _ChatSubmission? _retrySubmission;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _connectionStore = widget.connectionStore ?? MobileChatConnectionStore();
    _draftStore = widget.draftStore ?? MobileChatDraftStore();
    unawaited(_initialize());
  }

  Future<void> _initialize() async {
    if (widget.transport != null) {
      _transport = widget.transport;
      await _switchDraftScope(widget.draftScope ?? 'local');
      if (mounted) setState(() {});
      return;
    }
    try {
      final connection = await _connectionStore.load();
      if (connection == null) {
        _connectionError = 'ペアリング済みのチャット接続がありません。';
        await _switchDraftScope('unpaired');
      } else {
        final factory = widget.clientFactory ??
            (value) => CanonicalConversationClient(connection: value);
        _transport = factory(connection);
        _ownsTransport = true;
        await _switchDraftScope('pc:${connection.deviceId}');
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

  Future<ComposerSendResult> _send(String text) async {
    final transport = _transport;
    if (transport == null) {
      unawaited(_showOptions());
      return const ComposerSendResult.rejected('チャット接続を設定してから再試行してください。');
    }
    if (_busy) {
      return const ComposerSendResult.queued('前の送信が完了するまでお待ちください。');
    }
    final retry = _retrySubmission;
    final submission =
        retry != null && !retry.accepted && retry.text.trim() == text.trim()
            ? retry
            : _ChatSubmission(
                text: text,
                userId: _id('user'),
                assistantId: _id('assistant'),
              );
    final acceptance = Completer<ComposerSendResult>();
    unawaited(_runSubmission(transport, submission, acceptance));
    return acceptance.future;
  }

  Future<void> _runSubmission(
    ConversationTransport transport,
    _ChatSubmission submission,
    Completer<ComposerSendResult> acceptance,
  ) async {
    setState(() {
      _busy = true;
      _connectionError = null;
      _deliveryWarning = null;
    });

    var sendStarted = false;
    try {
      final conversationId = submission.conversationId ??
          _conversationId ??
          await transport.createConversation();
      submission.conversationId = conversationId;
      _conversationId = conversationId;
      final revision = submission.expectedRevision ??
          await transport.revision(conversationId);
      submission.expectedRevision = revision;
      sendStarted = true;
      await for (final update in transport.send(
        conversationId: conversationId,
        text: submission.text,
        clientMessageId: submission.userId,
        expectedRevision: revision,
      )) {
        if (!mounted) return;
        switch (update.kind) {
          case CanonicalChatUpdateKind.accepted:
            _commitSubmission(submission);
            submission.accepted = true;
            _retrySubmission = null;
            if (!acceptance.isCompleted) {
              acceptance.complete(const ComposerSendResult.accepted());
            }
            break;
          case CanonicalChatUpdateKind.delta:
            if (!submission.accepted) continue;
            _updateAssistant(
              submission.assistantId,
              (current) => current.copyWith(
                content: update.replace
                    ? update.content
                    : '${current.content}${update.content}',
              ),
            );
            break;
          case CanonicalChatUpdateKind.attention:
            if (!submission.accepted) continue;
            _updateAssistant(
              submission.assistantId,
              (current) => current.copyWith(content: update.content),
            );
            break;
          case CanonicalChatUpdateKind.error:
            if (submission.accepted) {
              _markCommittedRetry(
                submission,
                update.content.isEmpty ? '応答を完了できませんでした。' : update.content,
              );
            } else if (!acceptance.isCompleted) {
              _retrySubmission = submission;
              acceptance.complete(
                ComposerSendResult.rejected(
                  update.content.isEmpty
                      ? '送信が拒否されました。内容を確認して再試行してください。'
                      : update.content,
                ),
              );
            }
            break;
          case CanonicalChatUpdateKind.done:
            if (!submission.accepted) continue;
            _updateAssistant(
              submission.assistantId,
              (current) => current.copyWith(pending: false),
            );
            break;
        }
        _scrollToEnd();
      }
      if (!submission.accepted && !acceptance.isCompleted) {
        _retrySubmission = submission;
        acceptance.complete(
          const ComposerSendResult.queued('送信結果を確認できませんでした。同じ内容を安全に再試行できます。'),
        );
      }
    } catch (error) {
      if (!mounted) return;
      final ambiguous = sendStarted &&
          (error is! ConversationSendException || error.ambiguous);
      _retrySubmission = submission;
      if (submission.accepted) {
        _markCommittedRetry(submission, '応答状態を確認できませんでした。');
      } else if (!acceptance.isCompleted) {
        acceptance.complete(
          ambiguous
              ? const ComposerSendResult.queued(
                  '送信結果を確認できませんでした。同じ内容を安全に再試行できます。',
                )
              : const ComposerSendResult.rejected(
                  '送信を開始できませんでした。接続を確認して再試行してください。',
                ),
        );
      }
    } finally {
      if (mounted) setState(() => _busy = false);
      if (!acceptance.isCompleted) {
        acceptance.complete(
          const ComposerSendResult.rejected('送信を開始できませんでした。内容は保存されています。'),
        );
      }
    }
  }

  void _commitSubmission(_ChatSubmission submission) {
    if (_messages.any((message) => message.id == submission.userId)) return;
    setState(() {
      _messages.addAll([
        ChatMessage(
          id: submission.userId,
          role: ChatRole.user,
          content: submission.text,
        ),
        ChatMessage(
          id: submission.assistantId,
          role: ChatRole.assistant,
          content: '',
          pending: true,
        ),
      ]);
    });
    _scrollToEnd();
  }

  void _markCommittedRetry(_ChatSubmission submission, String message) {
    _retrySubmission = submission;
    _deliveryWarning = '応答状態を確認できませんでした。同じ送信 ID で再試行できます。';
    _updateAssistant(
      submission.assistantId,
      (current) => current.copyWith(
        content: current.content.isEmpty ? message : current.content,
        pending: false,
        error: true,
      ),
    );
  }

  void _retryCommittedSubmission() {
    final transport = _transport;
    final submission = _retrySubmission;
    if (transport == null || submission == null || _busy) return;
    _updateAssistant(
      submission.assistantId,
      (current) => current.copyWith(content: '', pending: true, error: false),
    );
    final acceptance = Completer<ComposerSendResult>();
    unawaited(_runSubmission(transport, submission, acceptance));
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
      await _switchDraftScope(
        'pc:${connection.deviceId}',
        preserveCurrent: true,
      );
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

  Future<void> _switchDraftScope(
    String scope, {
    bool preserveCurrent = false,
  }) async {
    _draftSaveTimer?.cancel();
    final previousScope = _draftScope;
    final previousText = _draftText;
    if (previousScope.isNotEmpty && previousText.isNotEmpty) {
      await _persistDraft(previousScope, previousText);
    }
    var nextText = '';
    try {
      nextText = await _draftStore.load(scope);
    } catch (_) {
      // Keep the in-memory draft usable when protected storage is unavailable.
    }
    if (scope == previousScope && _draftText != previousText) {
      nextText = _draftText;
      await _persistDraft(scope, nextText);
    }
    if (preserveCurrent && nextText.isEmpty && previousText.isNotEmpty) {
      nextText = previousText;
      await _persistDraft(scope, nextText);
    }
    _draftScope = scope;
    _draftText = nextText;
  }

  void _onDraftChanged(String value) {
    _draftText = value;
    if (_retrySubmission != null &&
        !_retrySubmission!.accepted &&
        _retrySubmission!.text.trim() != value.trim()) {
      _retrySubmission = null;
    }
    _draftSaveTimer?.cancel();
    if (value.isEmpty) {
      unawaited(_persistDraft(_draftScope, value));
      return;
    }
    _draftSaveTimer = Timer(const Duration(milliseconds: 250), () {
      unawaited(_persistDraft(_draftScope, _draftText));
    });
  }

  Future<void> _persistDraft(String scope, String text) async {
    try {
      await _draftStore.save(scope, text);
    } catch (_) {
      // Persistence must never make the live composer unusable or clear text.
    }
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.inactive ||
        state == AppLifecycleState.paused ||
        state == AppLifecycleState.detached ||
        state == AppLifecycleState.hidden) {
      _draftSaveTimer?.cancel();
      unawaited(_persistDraft(_draftScope, _draftText));
    }
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _draftSaveTimer?.cancel();
    unawaited(_persistDraft(_draftScope, _draftText));
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
          if (_deliveryWarning != null)
            MaterialBanner(
              content: Text(_deliveryWarning!),
              leading: const Icon(Icons.sync_problem_outlined),
              actions: [
                TextButton(
                  key: const ValueKey('chat-retry-committed'),
                  onPressed: _busy ? null : _retryCommittedSubmission,
                  child: const Text('安全に再試行'),
                ),
                TextButton(
                  onPressed: () => setState(() => _deliveryWarning = null),
                  child: const Text('閉じる'),
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
            key: ValueKey('composer:$_draftScope'),
            busy: _busy,
            enabled: true,
            initialText: _draftText,
            onChanged: _onDraftChanged,
            onSend: _send,
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
