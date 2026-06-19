import 'dart:async';
import 'dart:convert';

import 'package:http/http.dart' as http;

import '../settings/api_config_store.dart';
import 'chat_models.dart';

class OpenAiClient {
  OpenAiClient({http.Client? client}) : _http = client ?? http.Client();

  final http.Client _http;
  bool _cancelled = false;

  void cancel() => _cancelled = true;
  void close() => _http.close();

  Stream<String> streamChat({
    required ApiConfig config,
    required List<ChatMessage> history,
  }) async* {
    _cancelled = false;
    if (!config.isConfigured) {
      throw const OpenAiException('APIのURLとキーを設定してください。');
    }

    final uri = _chatCompletionsUri(config.baseUrl);
    final body = jsonEncode({
      'model': config.model,
      'messages': _buildMessages(config, history),
      'stream': true,
      'temperature': config.temperature,
    });

    final request = http.Request('POST', uri);
    request.headers.addAll({
      'Content-Type': 'application/json',
      'Accept': 'text/event-stream',
      'Authorization': 'Bearer ${config.apiKey.trim()}',
    });
    request.body = body;

    final streamed = await _http.send(request).timeout(const Duration(seconds: 30));
    if (streamed.statusCode < 200 || streamed.statusCode >= 300) {
      final text = await streamed.stream.bytesToString();
      throw OpenAiException(
        _friendlyHttpError(streamed.statusCode, text),
        statusCode: streamed.statusCode,
      );
    }

    final buffer = StringBuffer();
    await for (final chunk in streamed.stream.transform(utf8.decoder)) {
      if (_cancelled) {
        await streamed.stream.drain<void>();
        break;
      }
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
        if (data == '[DONE]') return;
        final delta = _parseDelta(data);
        if (delta.isNotEmpty) {
          yield delta;
        }
      }
    }
  }

  List<Map<String, String>> _buildMessages(
      ApiConfig config, List<ChatMessage> history) {
    final messages = <Map<String, String>>[];
    if (config.systemPrompt.trim().isNotEmpty) {
      messages.add({'role': 'system', 'content': config.systemPrompt.trim()});
    }
    for (final m in history) {
      if (m.content.trim().isEmpty && m.role != ChatRole.user) continue;
      messages.add({'role': m.role.value, 'content': m.content});
    }
    return messages;
  }

  String _parseDelta(String json) {
    try {
      final decoded = jsonDecode(json) as Map<String, dynamic>;
      final choices = decoded['choices'] as List?;
      if (choices == null || choices.isEmpty) return '';
      final choice = choices.first as Map<String, dynamic>;
      final delta = choice['delta'] as Map<String, dynamic>?;
      if (delta == null) return '';
      final content = delta['content'];
      return content is String ? content : '';
    } catch (_) {
      return '';
    }
  }

  Uri _chatCompletionsUri(String baseUrl) {
    var trimmed = baseUrl.trim();
    if (trimmed.isEmpty) {
      throw const OpenAiException('APIのURLを設定してください。');
    }
    if (!trimmed.contains('://')) trimmed = 'https://$trimmed';
    final uri = Uri.parse(trimmed);
    if (uri.host.isEmpty) {
      throw OpenAiException('APIのURLが不正です: $baseUrl');
    }
    final path = _trimTrailingSlash(uri.path);
    if (path.endsWith('/chat/completions')) return uri;
    return uri.replace(path: '$path/chat/completions');
  }

  String _friendlyHttpError(int code, String body) {
    try {
      final decoded = jsonDecode(body);
      if (decoded is Map<String, dynamic>) {
        final err = decoded['error'];
        if (err is Map && err['message'] is String) {
          return 'HTTP $code: ${err['message']}';
        }
        if (decoded['message'] is String) {
          return 'HTTP $code: ${decoded['message']}';
        }
      }
    } catch (_) {
      // ignore
    }
    return 'HTTP $code';
  }

  String _trimTrailingSlash(String path) {
    if (path.isEmpty || path == '/') return '';
    return path.endsWith('/') ? path.substring(0, path.length - 1) : path;
  }
}

class OpenAiException implements Exception {
  const OpenAiException(this.message, {this.statusCode});
  final String message;
  final int? statusCode;

  @override
  String toString() => message;
}
