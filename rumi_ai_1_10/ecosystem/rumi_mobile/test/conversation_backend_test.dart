import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:rumi_remote_app/src/chat/chat_models.dart';
import 'package:rumi_remote_app/src/chat/chat_store.dart';
import 'package:rumi_remote_app/src/chat/openai_client.dart';
import 'package:rumi_remote_app/src/data/local/local_chat_backend.dart';
import 'package:rumi_remote_app/src/domain/branch_lineage.dart';
import 'package:rumi_remote_app/src/domain/chat_event.dart';
import 'package:rumi_remote_app/src/domain/connection_state.dart';
import 'package:rumi_remote_app/src/domain/conversation_backend.dart';
import 'package:rumi_remote_app/src/domain/conversation_locator.dart';
import 'package:rumi_remote_app/src/settings/api_config_store.dart';

class _FakeSecureStorage implements SecureKeyValueStorage {
  final Map<String, String> _values = {};

  @override
  Future<String?> read(String key) async => _values[key];

  @override
  Future<void> write(String key, String? value) async {
    if (value == null) {
      _values.remove(key);
    } else {
      _values[key] = value;
    }
  }

  @override
  Future<void> delete(String key) async {
    _values.remove(key);
  }
}

class _FakeChatStorage implements ChatKeyValueStorage {
  final Map<String, String> _values = {};

  @override
  Future<String?> read(String key) async => _values[key];

  @override
  Future<void> write(String key, String value) async {
    _values[key] = value;
  }

  @override
  Future<void> delete(String key) async {
    _values.remove(key);
  }
}

http.Client _sseClient(
    void Function(http.Request) onRequest, List<String> chunks) {
  return MockClient.streaming((request, bodyStream) async {
    onRequest(request as http.Request);
    final bytes = chunks.map(utf8.encode).toList();
    final stream = Stream<List<int>>.fromIterable(bytes);
    return http.StreamedResponse(stream, 200);
  });
}

void main() {
  group('ConversationLocator', () {
    test('local/pc factories set authority', () {
      expect(ConversationLocator.local('a').authority,
          ConversationAuthorityKind.local);
      expect(
          ConversationLocator.pc('b').authority, ConversationAuthorityKind.pc);
    });

    test('equality considers authority, id, device', () {
      expect(ConversationLocator.local('a'), ConversationLocator.local('a'));
      expect(ConversationLocator.local('a') == ConversationLocator.pc('a'),
          isFalse);
      expect(
          ConversationLocator.pc('a', deviceId: 'd') ==
              ConversationLocator.pc('a', deviceId: 'd'),
          isTrue);
    });
  });

  group('BranchLineage', () {
    test('round-trips through json', () {
      final lineage = BranchLineage(
        parentConversationId: 'p1',
        forkedAtMessageId: 'm3',
        parentAuthority: ConversationAuthorityKind.pc,
        parentDeviceId: 'mac',
        reason: BranchReason.offlineContinue,
      );
      final decoded = BranchLineage.fromJson(lineage.toJson());
      expect(decoded.parentConversationId, 'p1');
      expect(decoded.parentAuthority, ConversationAuthorityKind.pc);
      expect(decoded.reason, BranchReason.offlineContinue);
    });
  });

  group('DeviceConnectionView', () {
    test('unpaired default has no capabilities', () {
      const view = DeviceConnectionView.unpaired;
      expect(view.pairingState, PairingState.unpaired);
      expect(view.canWritePcConversations, isFalse);
      expect(view.isPcOnline, isFalse);
    });
  });

  group('LocalConversationBackend', () {
    late ChatStore store;
    late ApiConfigStore configStore;

    setUp(() async {
      store = ChatStore(storage: _FakeChatStorage());
      await store.load();
      final storage = _FakeSecureStorage();
      await storage.write(
        'rumi.api_config.v1',
        jsonEncode(const ApiConfig(
          baseUrl: 'https://api.example.com/v1',
          apiKey: 'sk-test',
          model: 'gpt-test',
        ).toJson()),
      );
      configStore = ApiConfigStore(storage: storage);
    });

    test('create + get conversation', () async {
      final backend =
          LocalConversationBackend(store: store, configStore: configStore);
      final locator = await backend.createConversation(
        const CreateConversationRequest(
            authority: ConversationAuthorityKind.local),
      );
      expect(locator.isLocal, isTrue);
      final snap = await backend.getConversation(locator);
      expect(snap.conversation.id, locator.conversationId);
      expect(snap.revision, 0);
    });

    test('listConversations reflects store', () async {
      await store.createAndPersist();
      final backend =
          LocalConversationBackend(store: store, configStore: configStore);
      final list = await backend.listConversations();
      expect(list.length, 1);
      expect(list.first.authority, ConversationAuthorityKind.local);
    });

    test('sendMessage streams deltas and commits assistant content', () async {
      final convo = await store.createAndPersist();
      final locator = ConversationLocator.local(convo.id);

      final client = _sseClient(
        (request) {
          expect(request.url.toString(),
              'https://api.example.com/v1/chat/completions');
        },
        [
          'data: {"choices":[{"delta":{"content":"Hello"}}]}\n\n',
          'data: {"choices":[{"delta":{"content":" world"}}]}\n\n',
          'data: [DONE]\n\n',
        ],
      );

      final backend = LocalConversationBackend(
        store: store,
        configStore: configStore,
        createClient: () => OpenAiClient(client: client),
      );

      final events = await backend
          .sendMessage(
            locator: locator,
            text: 'hi',
            clientMessageId: 'u1',
            expectedRevision: 0,
          )
          .toList();

      final deltas = events.whereType<ChatDelta>().toList();
      expect(deltas, isNotEmpty);
      expect(deltas.last.accumulatedContent, 'Hello world');
      expect(events.whereType<ChatRunStarted>(), isNotEmpty);
      expect(events.whereType<ChatMessageCommitted>().single.content,
          'Hello world');
      expect(events.whereType<ChatMessageCommitted>().single.error, isFalse);
      expect(events.whereType<ChatRunCompleted>(), isNotEmpty);

      final updated = store.conversations.firstWhere((c) => c.id == convo.id);
      expect(updated.messages.length, 2);
      expect(updated.messages.first.role, ChatRole.user);
      expect(updated.messages.last.content, 'Hello world');
      expect(updated.messages.last.pending, isFalse);
    });

    test('sendMessage surfaces unconfigured api as error event', () async {
      final convo = await store.createAndPersist();
      final locator = ConversationLocator.local(convo.id);
      final emptyStorage = _FakeSecureStorage();
      final emptyConfig = ApiConfigStore(storage: emptyStorage);
      final backend = LocalConversationBackend(
        store: store,
        configStore: emptyConfig,
      );
      final events = await backend
          .sendMessage(
            locator: locator,
            text: 'hi',
            clientMessageId: 'u1',
            expectedRevision: 0,
          )
          .toList();
      expect(events, isA<List<ChatEvent>>());
      expect(events.single, isA<ChatErrorEvent>());
      expect((events.single as ChatErrorEvent).message, contains('APIのURLとキー'));
    });
  });
}
