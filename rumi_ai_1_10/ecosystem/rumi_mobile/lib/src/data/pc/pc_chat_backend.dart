import 'dart:async';
import 'dart:convert';

import 'package:http/http.dart' as http;
import 'package:uuid/uuid.dart';

import '../../chat/chat_models.dart';
import '../../domain/chat_event.dart';
import '../../domain/conversation_backend.dart';
import '../../domain/conversation_locator.dart';
import '../../settings/api_config_store.dart';

class PcConversationBackend implements ConversationBackend {
  PcConversationBackend({
    required this.connection,
    this.deviceId,
    http.Client? client,
  })  : _http = client ?? http.Client(),
        _uuid = const Uuid();

  final PcConnection connection;
  final String? deviceId;
  final http.Client _http;
  final Uuid _uuid;
  bool _closed = false;

  @override
  ConversationAuthorityKind get authority => ConversationAuthorityKind.pc;

  @override
  bool get isConfigured => connection.isConfigured;

  void close() {
    _closed = true;
    _http.close();
  }

  Map<String, String> get _headers => {
        'Authorization': 'Bearer ${connection.token}',
        'Accept': 'application/json',
        'Content-Type': 'application/json',
      };

  Uri _uri(String path) {
    var trimmed = connection.baseUrl.trim();
    if (!trimmed.contains('://')) trimmed = 'https://$trimmed';
    final base = Uri.parse(trimmed);
    return base.replace(path: '${_trimTrailingSlash(base.path)}$path');
  }

  @override
  Future<List<ConversationSummary>> listConversations() async {
    _checkReady();
    final uri = _uri('/api/mobile/v1/conversations');
    final resp = await _http
        .get(uri, headers: _headers)
        .timeout(const Duration(seconds: 15));
    _checkResponse(resp);
    final data = _decodeData(resp.body);
    final list = data['conversations'] as List? ?? const [];
    return list
        .map((e) => _parseConversationSummary(e as Map<String, dynamic>))
        .toList();
  }

  @override
  Future<ConversationSnapshot> getConversation(
      ConversationLocator locator) async {
    _checkReady();
    final uri = _uri('/api/mobile/v1/conversations/${locator.conversationId}');
    final resp = await _http
        .get(uri, headers: _headers)
        .timeout(const Duration(seconds: 15));
    _checkResponse(resp);
    final data = _decodeData(resp.body);
    final convoJson = data['conversation'] as Map<String, dynamic>? ?? data;
    final conversation = _parseConversation(convoJson);
    return ConversationSnapshot(
      locator: locator,
      conversation: conversation,
      revision: conversation.revision,
    );
  }

  @override
  Future<ConversationLocator> createConversation(
      CreateConversationRequest request) async {
    _checkReady();
    final uri = _uri('/api/mobile/v1/conversations');
    final body = <String, dynamic>{};
    if (request.title != null && request.title!.trim().isNotEmpty) {
      body['title'] = request.title!.trim();
    }
    final resp = await _http
        .post(uri, headers: _headers, body: jsonEncode(body))
        .timeout(const Duration(seconds: 15));
    _checkResponse(resp);
    final data = _decodeData(resp.body);
    final id = data['conversation_id'] as String? ??
        (data['conversation'] as Map<String, dynamic>?)?['id'] as String? ??
        '';
    return ConversationLocator.pc(id, deviceId: deviceId);
  }

  @override
  Stream<ChatEvent> sendMessage({
    required ConversationLocator locator,
    required String text,
    required String clientMessageId,
    required int expectedRevision,
  }) async* {
    _checkReady();

    final runId = _uuid.v4();
    final assistantId = _uuid.v4();

    yield ChatRunStarted(
      locator: locator,
      runId: runId,
      assistantMessageId: assistantId,
    );

    final uri =
        _uri('/api/mobile/v1/conversations/${locator.conversationId}/stream');
    final body = jsonEncode({
      'message': text,
      'client_message_id': clientMessageId,
      'expected_revision': expectedRevision,
    });

    try {
      final request = http.Request('POST', uri);
      request.headers.addAll({
        ..._headers,
        'Accept': 'text/event-stream',
      });
      request.body = body;

      final streamed =
          await _http.send(request).timeout(const Duration(seconds: 30));

      if (streamed.statusCode < 200 || streamed.statusCode >= 300) {
        final errBody = await streamed.stream.bytesToString();
        yield ChatErrorEvent(
          locator: locator,
          runId: runId,
          assistantMessageId: assistantId,
          message: 'PC API エラー (HTTP ${streamed.statusCode}): $errBody',
        );
        return;
      }

      final buffer = StringBuffer();
      final contentBuffer = StringBuffer();

      await for (final chunk in streamed.stream.transform(utf8.decoder)) {
        if (_closed) break;
        buffer.write(chunk);
        while (true) {
          final nl = buffer.toString().indexOf('\n');
          if (nl < 0) break;
          final line = buffer.toString().substring(0, nl);
          final remaining = buffer.toString().substring(nl + 1);
          buffer.clear();
          buffer.write(remaining);
          final trimmed = line.trim();
          if (trimmed.isEmpty) continue;
          if (!trimmed.startsWith('data:')) continue;
          final data = trimmed.substring(5).trim();
          if (data == '[DONE]') {
            yield ChatMessageCommitted(
              locator: locator,
              runId: runId,
              messageId: assistantId,
              content: contentBuffer.toString(),
              error: false,
            );
            yield ChatRunCompleted(locator: locator, runId: runId);
            return;
          }
          final event = _parseSseEvent(
            data,
            locator: locator,
            runId: runId,
            assistantId: assistantId,
            contentBuffer: contentBuffer,
          );
          if (event != null) yield event;
        }
      }

      if (!_closed) {
        yield ChatMessageCommitted(
          locator: locator,
          runId: runId,
          messageId: assistantId,
          content: contentBuffer.toString(),
          error: false,
        );
        yield ChatRunCompleted(locator: locator, runId: runId);
      }
    } catch (error) {
      yield ChatErrorEvent(
        locator: locator,
        runId: runId,
        assistantMessageId: assistantId,
        message: 'PC通信エラー: $error',
      );
    }
  }

  @override
  Future<void> stop(String conversationId) async {
    _checkReady();
    final uri = _uri('/api/mobile/v1/conversations/$conversationId/stop');
    try {
      await _http
          .post(uri, headers: _headers)
          .timeout(const Duration(seconds: 10));
    } catch (_) {
      // ignore stop errors
    }
  }

  ChatEvent? _parseSseEvent(
    String data, {
    required ConversationLocator locator,
    required String runId,
    required String assistantId,
    required StringBuffer contentBuffer,
  }) {
    try {
      final json = jsonDecode(data) as Map<String, dynamic>;
      final type = json['type'] as String? ?? 'delta';

      switch (type) {
        case 'delta':
          final delta = json['delta'] as String? ?? '';
          final content = json['content'] as String? ?? '';
          if (content.isNotEmpty) {
            contentBuffer.clear();
            contentBuffer.write(content);
          } else if (delta.isNotEmpty) {
            contentBuffer.write(delta);
          }
          if (delta.isNotEmpty || content.isNotEmpty) {
            return ChatDelta(
              locator: locator,
              runId: runId,
              assistantMessageId: assistantId,
              delta: delta,
              accumulatedContent:
                  content.isNotEmpty ? content : contentBuffer.toString(),
            );
          }
          return null;

        case 'tool_call':
          return ToolCallEvent(
            locator: locator,
            runId: runId,
            toolId: json['tool_id'] as String? ?? '',
            toolName: json['tool_name'] as String? ?? '',
            status: json['tool_status'] as String? ?? 'running',
            arguments: (json['arguments'] as Map<String, dynamic>?) ?? const {},
            summary: json['summary'] as String?,
            output: json['output'] as String?,
          );

        case 'approval':
          return ApprovalEvent(
            locator: locator,
            runId: runId,
            approvalId: json['approval_id'] as String? ?? '',
            toolName: json['tool_name'] as String? ?? '',
            prompt: json['prompt'] as String? ?? '',
            arguments: (json['arguments'] as Map<String, dynamic>?) ?? const {},
            approved: json['approved'] as bool? ?? false,
            pending: json['pending'] as bool? ?? true,
          );

        case 'error':
          return ChatErrorEvent(
            locator: locator,
            runId: runId,
            assistantMessageId: assistantId,
            message: json['message'] as String? ?? 'Unknown error',
          );

        case 'done':
          return null;

        default:
          return null;
      }
    } catch (_) {
      return null;
    }
  }

  ConversationSummary _parseConversationSummary(Map<String, dynamic> json) {
    return ConversationSummary(
      id: json['id'] as String? ?? '',
      title: json['title'] as String? ?? '無題',
      authority: ConversationAuthorityKind.pc,
      messageCount: (json['message_count'] as num?)?.toInt() ?? 0,
      updatedAt: DateTime.tryParse(json['updated_at'] as String? ?? '') ??
          DateTime.now(),
      pinned: json['pinned'] as bool? ?? false,
      revision: (json['revision'] as num?)?.toInt() ?? 0,
    );
  }

  Conversation _parseConversation(Map<String, dynamic> json) {
    final messages = (json['messages'] as List? ?? [])
        .map((m) => _parseMessage(m as Map<String, dynamic>))
        .toList();
    return Conversation(
      id: json['id'] as String? ?? '',
      title: json['title'] as String? ?? '無題',
      messages: messages,
      createdAt: DateTime.tryParse(json['created_at'] as String? ?? '') ??
          DateTime.now(),
      updatedAt: DateTime.tryParse(json['updated_at'] as String? ?? '') ??
          DateTime.now(),
      pinned: json['pinned'] as bool? ?? false,
      revision: (json['revision'] as num?)?.toInt() ?? 0,
    );
  }

  ChatMessage _parseMessage(Map<String, dynamic> json) {
    return ChatMessage(
      id: json['id'] as String? ?? '',
      role: ChatRole.fromString(json['role'] as String? ?? 'assistant'),
      content: json['content'] as String? ?? '',
      createdAt: DateTime.tryParse(json['created_at'] as String? ?? ''),
      pending: json['pending'] as bool? ?? false,
      error: json['error'] as bool? ?? false,
    );
  }

  Map<String, dynamic> _decodeData(String body) {
    try {
      final decoded = jsonDecode(body) as Map<String, dynamic>;
      if (decoded['status'] != 'ok') {
        final err = decoded['error'];
        final msg = err is Map ? err['message'] as String? : null;
        throw StateError(msg ?? 'PCからエラーが返されました。');
      }
      return decoded['data'] as Map<String, dynamic>? ?? const {};
    } catch (e) {
      if (e is StateError) rethrow;
      throw StateError('PC応答の解析に失敗しました: $e');
    }
  }

  void _checkReady() {
    if (!connection.isConfigured) {
      throw StateError('PC接続が設定されていません。');
    }
    if (_closed) {
      throw StateError('クライアントは閉じられました。');
    }
  }

  void _checkResponse(http.Response resp) {
    if (resp.statusCode < 200 || resp.statusCode >= 300) {
      throw StateError('PC API エラー (HTTP ${resp.statusCode}): ${resp.body}');
    }
  }

  String _trimTrailingSlash(String path) {
    if (path.isEmpty || path == '/') return '';
    return path.endsWith('/') ? path.substring(0, path.length - 1) : path;
  }
}
