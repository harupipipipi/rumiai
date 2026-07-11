import 'dart:convert';
import '../data/pc/device_store.dart';
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

class QrPairingV2 extends QrPayload {
  const QrPairingV2(this.payload);
  final PairingV2Payload payload;
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
          return QrUnknown(trimmed);
        case 'rumi_mobile_pair_v1':
        case 'rumi_pair_v2':
          return QrPairingV2(PairingV2Payload.fromJson(json));
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
