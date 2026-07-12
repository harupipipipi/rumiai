import 'dart:convert';
import '../data/pc/device_store.dart';

sealed class ScannedPairingPayload {
  const ScannedPairingPayload();
}

class QrPairingV2 extends ScannedPairingPayload {
  const QrPairingV2(this.payload);
  final PairingV2Payload payload;
}

class QrUrl extends ScannedPairingPayload {
  const QrUrl(this.url);
  final String url;
}

class QrUnknown extends ScannedPairingPayload {
  const QrUnknown(this.raw);
  final String raw;
}

ScannedPairingPayload parsePairingPayload(String raw) {
  final trimmed = raw.trim();
  if (trimmed.isEmpty) return const QrUnknown('');
  if (trimmed.startsWith('{')) {
    try {
      final json = jsonDecode(trimmed) as Map<String, dynamic>;
      final kind = json['kind'] as String?;
      switch (kind) {
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
