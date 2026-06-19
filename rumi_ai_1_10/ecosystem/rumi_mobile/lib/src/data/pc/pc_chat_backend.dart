import '../../domain/chat_event.dart';
import '../../domain/conversation_backend.dart';
import '../../domain/conversation_locator.dart';

class PcConversationBackend implements ConversationBackend {
  PcConversationBackend({this.deviceId});

  final String? deviceId;

  @override
  ConversationAuthorityKind get authority => ConversationAuthorityKind.pc;

  @override
  bool get isConfigured => false;

  @override
  Future<List<ConversationSummary>> listConversations() async {
    // PC facade integration arrives in a later commit.
    return const [];
  }

  @override
  Future<ConversationSnapshot> getConversation(ConversationLocator locator) {
    throw UnimplementedError('PC conversation fetching is not available yet.');
  }

  @override
  Future<ConversationLocator> createConversation(
      CreateConversationRequest request) {
    throw UnimplementedError(
        'Creating conversations on the PC is not available yet.');
  }

  @override
  Stream<ChatEvent> sendMessage({
    required ConversationLocator locator,
    required String text,
    required String clientMessageId,
    required int expectedRevision,
  }) async* {
    yield ChatErrorEvent(
      locator: locator,
      runId: clientMessageId,
      message: 'PCとの接続が確立していません。',
    );
  }

  @override
  Future<void> stop(String conversationId) async {}
}
