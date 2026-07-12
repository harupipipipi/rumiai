import 'dart:convert';

class MobilePairingPayload {
  const MobilePairingPayload({required this.pairingId, required this.baseUrl});
  final String pairingId;
  final String baseUrl;

  static MobilePairingPayload parse(String raw) {
    final trimmed = raw.trim();
    if (trimmed.startsWith('rumi_api:') || trimmed.startsWith('rumi_api://')) {
      throw const FormatException(
          'legacy credential-bearing QR is not supported');
    }
    final decoded = jsonDecode(trimmed);
    if (decoded is! Map || decoded['version'] != 2) {
      throw const FormatException('unsupported pairing payload');
    }
    final pairingId = decoded['pairing_id'] as String? ?? '';
    final baseUrl = decoded['base_url'] as String? ?? '';
    final uri = Uri.tryParse(baseUrl);
    if (pairingId.isEmpty ||
        uri == null ||
        !uri.hasScheme ||
        uri.host.isEmpty) {
      throw const FormatException('invalid pairing payload');
    }
    if (decoded.keys.any((key) => const {
          'token',
          'credential',
          'api_key',
          'secret',
          'private_key'
        }.contains(key))) {
      throw const FormatException('pairing QR must not contain credentials');
    }
    return MobilePairingPayload(pairingId: pairingId, baseUrl: baseUrl);
  }
}
