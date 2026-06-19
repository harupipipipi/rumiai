import 'dart:convert';

import '../settings/api_config_store.dart';

sealed class QrPayload {
  const QrPayload();
}

class QrPcConnection extends QrPayload {
  const QrPcConnection({required this.baseUrl, required this.token});
  final String baseUrl;
  final String token;

  PcConnection toPcConnection() => PcConnection(baseUrl: baseUrl, token: token);
}

class QrApiImport extends QrPayload {
  const QrApiImport({
    required this.baseUrl,
    required this.apiKey,
    this.model,
    this.label,
  });
  final String baseUrl;
  final String apiKey;
  final String? model;
  final String? label;

  ApiConfig toApiConfig({required ApiConfig fallback}) {
    return fallback.copyWith(
      baseUrl: baseUrl,
      apiKey: apiKey,
      model: model,
      label: label,
    );
  }
}

class QrUrl extends QrPayload {
  const QrUrl(this.url);
  final String url;
}

class QrUnknown extends QrPayload {
  const QrUnknown(this.raw);
  final String raw;
}

QrPayload parseQrPayload(String raw) {
  final trimmed = raw.trim();
  if (trimmed.isEmpty) return const QrUnknown('');
  if (trimmed.startsWith('{')) {
    try {
      final json = jsonDecode(trimmed) as Map<String, dynamic>;
      final kind = json['kind'] as String?;
      switch (kind) {
        case 'rumi_pc':
          return QrPcConnection(
            baseUrl: (json['baseUrl'] as String?)?.trim() ?? '',
            token: (json['token'] as String?)?.trim() ?? '',
          );
        case 'rumi_api':
          return QrApiImport(
            baseUrl: (json['baseUrl'] as String?)?.trim() ?? '',
            apiKey: (json['apiKey'] as String?)?.trim() ??
                (json['api_key'] as String?)?.trim() ??
                '',
            model: (json['model'] as String?)?.trim(),
            label: (json['label'] as String?)?.trim(),
          );
      }
    } catch (_) {
      return QrUnknown(trimmed);
    }
  }
  if (trimmed.startsWith('http://') || trimmed.startsWith('https://')) {
    return QrUrl(trimmed);
  }
  return QrUnknown(trimmed);
}
