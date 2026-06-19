import 'package:uuid/uuid.dart';

import '../../chat/chat_models.dart';
import '../../chat/chat_store.dart';
import '../../chat/openai_client.dart';
import '../../domain/chat_event.dart';
import '../../domain/conversation_backend.dart';
import '../../domain/conversation_locator.dart';
import '../../settings/api_config_store.dart';

class LocalConversationBackend implements ConversationBackend {
  LocalConversationBackend({
    required ChatStore store,
    required ApiConfigStore configStore,
    OpenAiClient? client,
    OpenAiClient Function()? createClient,
  })  : _store = store,
        _configStore = configStore,
        _uuid = const Uuid(),
        _client = client,
        _createClient = createClient;

  final ChatStore _store;
  final ApiConfigStore _configStore;
  final Uuid _uuid;
  OpenAiClient? _client;
  final OpenAiClient Function()? _createClient;

  OpenAiClient _newClient() => _createClient?.call() ?? OpenAiClient();

  @override
  ConversationAuthorityKind get authority => ConversationAuthorityKind.local;

  Conversation? _find(String id) {
    for (final c in _store.conversations) {
      if (c.id == id) return c;
    }
    return null;
  }

  @override
  bool get isConfigured {
    // Best-effort: cannot be synchronous with secure storage. Callers that
    // need an authoritative answer should await configStore.loadApi().
    return true;
  }

  Future<ApiConfig> _loadConfig() => _configStore.loadApi();

  @override
  Future<List<ConversationSummary>> listConversations() async {
    await _store.load();
    return _store.conversations
        .map((c) => ConversationSummary.from(c))
        .toList();
  }

  @override
  Future<ConversationSnapshot> getConversation(
      ConversationLocator locator) async {
    final convo = _find(locator.conversationId);
    if (convo == null) {
      throw StateError('Conversation not found: ${locator.conversationId}');
    }
    return ConversationSnapshot(
      locator: locator,
      conversation: convo,
      revision: convo.revision,
    );
  }

  @override
  Future<ConversationLocator> createConversation(
      CreateConversationRequest request) async {
    final convo = await _store.createAndPersist();
    if (request.title != null && request.title!.trim().isNotEmpty) {
      await _store.rename(convo.id, request.title!);
    }
    return ConversationLocator.local(convo.id);
  }

  @override
  Stream<ChatEvent> sendMessage({
    required ConversationLocator locator,
    required String text,
    required String clientMessageId,
    required int expectedRevision,
  }) async* {
    if (text.trim().isEmpty) return;

    final config = await _loadConfig();
    if (!config.isConfigured) {
      yield ChatErrorEvent(
        locator: locator,
        runId: clientMessageId,
        message: 'APIのURLとキーを設定してください。',
      );
      return;
    }

    final convo = _find(locator.conversationId);
    if (convo == null) {
      yield ChatErrorEvent(
        locator: locator,
        runId: clientMessageId,
        message: '会話が見つかりません。',
      );
      return;
    }

    final userMsg = ChatMessage(
      id: clientMessageId,
      role: ChatRole.user,
      content: text,
      createdAt: DateTime.now(),
    );
    await _store.addMessage(convo.id, userMsg);

    final assistantId = _uuid.v4();
    final assistantMsg = ChatMessage(
      id: assistantId,
      role: ChatRole.assistant,
      content: '',
      createdAt: DateTime.now(),
      pending: true,
    );
    await _store.addMessage(convo.id, assistantMsg);

    final runId = _uuid.v4();
    yield ChatRunStarted(
      locator: locator,
      runId: runId,
      assistantMessageId: assistantId,
    );

    _client?.close();
    _client = _newClient();

    final history = List<ChatMessage>.from(convo.messages)
      ..removeWhere((m) => m.id == assistantId);
    final buffer = StringBuffer();

    try {
      await for (final delta
          in _client!.streamChat(config: config, history: history)) {
        buffer.write(delta);
        final accumulated = buffer.toString();
        await _store.updateMessage(
          convo.id,
          assistantId,
          accumulated,
          pending: true,
        );
        yield ChatDelta(
          locator: locator,
          runId: runId,
          assistantMessageId: assistantId,
          delta: delta,
          accumulatedContent: accumulated,
        );
      }
      final finalContent = buffer.toString();
      await _store.updateMessage(
        convo.id,
        assistantId,
        finalContent,
        pending: false,
      );
      yield ChatMessageCommitted(
        locator: locator,
        runId: runId,
        messageId: assistantId,
        content: finalContent,
        error: false,
      );
      yield ChatRunCompleted(locator: locator, runId: runId);
    } catch (error) {
      final partial = buffer.toString();
      final message = partial.isEmpty
          ? 'エラー: ${_friendlyError(error)}'
          : '$partial\n\n_エラー: ${_friendlyError(error)}_';
      await _store.updateMessage(
        convo.id,
        assistantId,
        message,
        pending: false,
        error: true,
      );
      yield ChatErrorEvent(
        locator: locator,
        runId: runId,
        message: _friendlyError(error),
        assistantMessageId: assistantId,
      );
    }
  }

  @override
  Future<void> stop(String conversationId) async {
    _client?.cancel();
  }

  void dispose() {
    _client?.close();
  }

  String _friendlyError(Object error) {
    if (error is OpenAiException) return error.message;
    return '$error';
  }
}
