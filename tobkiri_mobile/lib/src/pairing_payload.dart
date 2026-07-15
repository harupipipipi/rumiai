import 'dart:convert';

class MobilePairingPayload {
  const MobilePairingPayload({
    required this.pairingId,
    required this.baseUrl,
    required this.code,
    required this.pickupSecret,
    required this.expiresAt,
  });
  final String pairingId;
  final String baseUrl;
  final String code;
  final String pickupSecret;
  final int expiresAt;

  bool get isExpired => DateTime.now().millisecondsSinceEpoch >= expiresAt;

  static MobilePairingPayload parse(String raw) {
    // iOS may turn straight quotes into smart quotes when a QR payload is
    // manually pasted or typed. Normalize only the JSON delimiters before
    // decoding so the same public, credential-free payload remains usable.
    final trimmed = raw
        .trim()
        .replaceAll('\u201c', '"')
        .replaceAll('\u201d', '"');
    if (trimmed.startsWith('rumi_api:') || trimmed.startsWith('rumi_api://')) {
      throw const FormatException(
        'legacy credential-bearing QR is not supported',
      );
    }
    final decoded = jsonDecode(trimmed);
    if (decoded is! Map ||
        !const {'rumi_pair_v2', 'rumi_mobile_pair_v1'}
            .contains(decoded['kind'])) {
      throw const FormatException('unsupported pairing payload');
    }
    final pairingId = decoded['pairing_id'] as String? ?? '';
    final urls = (decoded['base_urls'] as List? ?? const [])
        .whereType<String>()
        .where((value) => value.trim().isNotEmpty)
        .toList();
    final baseUrl =
        urls.isNotEmpty ? urls.first : decoded['base_url'] as String? ?? '';
    final code = decoded['code'] as String? ?? '';
    final pickupSecret = decoded['pickup_secret'] as String? ?? '';
    final expiresAt = (decoded['expires_at'] as num?)?.toInt() ?? 0;
    final uri = Uri.tryParse(baseUrl);
    if (pairingId.isEmpty ||
        code.isEmpty ||
        pickupSecret.isEmpty ||
        expiresAt <= 0 ||
        uri == null ||
        !uri.hasScheme ||
        uri.host.isEmpty) {
      throw const FormatException('invalid pairing payload');
    }
    if (decoded.keys.any((key) => const {
          'token',
          'credential',
          'api_key',
          'private_key',
        }.contains(key))) {
      throw const FormatException('pairing QR must not contain credentials');
    }
    return MobilePairingPayload(
      pairingId: pairingId,
      baseUrl: baseUrl,
      code: code,
      pickupSecret: pickupSecret,
      expiresAt: expiresAt,
    );
  }
}
