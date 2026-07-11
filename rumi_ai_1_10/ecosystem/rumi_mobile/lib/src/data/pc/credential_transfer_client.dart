import 'dart:convert';

import 'package:cryptography/cryptography.dart';
import 'package:http/http.dart' as http;

import '../../settings/api_config_store.dart';
import 'device_store.dart';

class CredentialTransferException implements Exception {
  const CredentialTransferException(this.message, {this.statusCode});
  final String message;
  final int? statusCode;

  @override
  String toString() => message;
}

class CredentialTransfer {
  const CredentialTransfer({
    required this.transferId,
    required this.status,
    required this.deviceId,
    required this.providerId,
    required this.apiId,
    required this.expiresAt,
    this.deviceLabel = '',
    this.profileId = '',
    this.providerLabel = '',
    this.redemptionChallenge = '',
    this.reason = '',
  });

  final String transferId;
  final String status;
  final String deviceId;
  final String deviceLabel;
  final String profileId;
  final String providerId;
  final String providerLabel;
  final String apiId;
  final int expiresAt;
  final String redemptionChallenge;
  final String reason;

  bool get isPending => status == 'pending';
  bool get isAccepted => status == 'accepted';
  bool get isTerminal => const {
        'completed',
        'rejected',
        'expired',
        'revoked',
        'cancelled'
      }.contains(status);
  bool get isExpired => DateTime.now().millisecondsSinceEpoch >= expiresAt;

  factory CredentialTransfer.fromJson(Map<String, dynamic> json) {
    final transfer = json['transfer'] as Map<String, dynamic>? ?? json;
    return CredentialTransfer(
      transferId: transfer['transfer_id'] as String? ?? '',
      status: transfer['status'] as String? ?? '',
      deviceId: transfer['device_id'] as String? ?? '',
      deviceLabel: transfer['device_label'] as String? ?? '',
      profileId: transfer['profile_id'] as String? ?? '',
      providerId: transfer['provider_id'] as String? ?? '',
      providerLabel: transfer['provider_label'] as String? ?? '',
      apiId: transfer['api_id'] as String? ?? '',
      expiresAt: (transfer['expires_at'] as num?)?.toInt() ?? 0,
      redemptionChallenge: transfer['redemption_challenge'] as String? ?? '',
      reason: transfer['reason'] as String? ?? '',
    );
  }

  Map<String, dynamic> redemptionPayload() => {
        // Keep this order identical to Python json.dumps(sort_keys=True,
        // separators=(",", ":")); it is the signed protocol contract.
        'api_id': apiId,
        'challenge': redemptionChallenge,
        'device_id': deviceId,
        'expires_at': expiresAt,
        'provider_id': providerId,
        'transfer_id': transferId,
      };

  String canonicalRedemptionMessage() => jsonEncode(redemptionPayload());
}

class CredentialTransferClient {
  CredentialTransferClient({http.Client? client})
      : _http = client ?? http.Client();

  final http.Client _http;
  final Map<String, Map<String, dynamic>> _pendingPersistence = {};
  bool _closed = false;

  void close() {
    _closed = true;
    for (final payload in _pendingPersistence.values) {
      payload.clear();
    }
    _pendingPersistence.clear();
    _http.close();
  }

  Map<String, String> _headers(String token) => {
        'Authorization': 'Bearer $token',
        'Accept': 'application/json',
        'Content-Type': 'application/json',
      };

  Uri _uri(String baseUrl, String path) {
    var trimmed = baseUrl.trim();
    if (!trimmed.contains('://')) trimmed = 'https://$trimmed';
    final base = Uri.parse(trimmed);
    return base.replace(path: '${_trimTrailingSlash(base.path)}$path');
  }

  Future<List<CredentialTransfer>> listPending(PcConnection pc) async {
    final data =
        await _request(pc, 'GET', '/api/mobile/v1/credential-transfers');
    final transfers = data['transfers'] as List? ?? const [];
    return transfers
        .whereType<Map>()
        .map((value) => CredentialTransfer.fromJson(
              Map<String, dynamic>.from(value),
            ))
        .where((transfer) =>
            !transfer.isExpired && (transfer.isPending || transfer.isAccepted))
        .toList();
  }

  Future<Map<String, dynamic>> redeem(
    PcConnection pc, {
    required CredentialTransfer transfer,
    required MobileDeviceStore deviceStore,
  }) async {
    if (transfer.isExpired || !transfer.isPending) {
      throw const CredentialTransferException(
        'この転送は期限切れまたは受領済みです。',
      );
    }
    final identity = await deviceStore.loadOrCreateIdentity();
    if (identity.deviceId != transfer.deviceId) {
      throw const CredentialTransferException('この転送は別の端末宛てです。');
    }
    final encoded = transfer.canonicalRedemptionMessage();
    final digest = await Sha256().hash(utf8.encode(encoded));
    final signature = await deviceStore.signApprovalPayloadHash(
      _hex(digest.bytes),
    );
    final data = await _request(
      pc,
      'POST',
      '/api/mobile/v1/credential-transfers/${transfer.transferId}',
      body: {'signature': signature},
    );
    final envelope = Map<String, dynamic>.from(data['envelope'] as Map);
    return deviceStore.decryptCredentialTransferEnvelope(
      envelope,
      transferId: transfer.transferId,
      deviceId: transfer.deviceId,
      expiresAt: transfer.expiresAt,
    );
  }

  Future<void> reject(PcConnection pc, CredentialTransfer transfer) async {
    await _request(
      pc,
      'POST',
      '/api/mobile/v1/credential-transfers/${transfer.transferId}/reject',
      body: {'reason': 'rejected by recipient'},
    );
  }

  Future<void> acknowledge(PcConnection pc, CredentialTransfer transfer) async {
    await _request(
      pc,
      'POST',
      '/api/mobile/v1/credential-transfers/${transfer.transferId}/ack',
      body: const {},
    );
  }

  Future<void> redeemAndStore(
    PcConnection pc, {
    required CredentialTransfer transfer,
    required MobileDeviceStore deviceStore,
    required ApiConfigStore configStore,
  }) async {
    final payload = _pendingPersistence[transfer.transferId] ??
        await redeem(
          pc,
          transfer: transfer,
          deviceStore: deviceStore,
        );
    _pendingPersistence[transfer.transferId] = payload;
    if (payload['provider_id'] != transfer.providerId ||
        payload['api_id'] != transfer.apiId ||
        payload['expires_at'] != transfer.expiresAt) {
      throw const CredentialTransferException(
        '暗号化payloadの転送内容が一致しません。',
      );
    }
    final apiKey = payload['api_key'] as String? ?? '';
    if (apiKey.trim().isEmpty) {
      throw const CredentialTransferException('credentialが空です。');
    }
    final existing = await configStore.loadProviderConfigs();
    final previous = existing
        .where((config) => config.providerId == transfer.providerId)
        .firstOrNull;
    final next = MobileProviderConfig(
      providerId: transfer.providerId,
      displayName: transfer.providerLabel,
      label: payload['label'] as String? ?? transfer.providerLabel,
      apiKey: apiKey,
      baseUrl: payload['base_url'] as String? ?? previous?.baseUrl ?? '',
      model: payload['default_model'] as String? ?? previous?.model ?? '',
      openaiCompatible: previous?.openaiCompatible ?? true,
      local: false,
      catalogOnly: false,
      apiCompatibility: previous?.apiCompatibility ?? 'openai',
    );
    try {
      // ACK is a statement that durable secure storage succeeded.  A failed
      // or unverifiable write deliberately leaves the server in accepted so
      // the user can retry local persistence without claiming completion.
      await configStore.upsertProviderConfigVerified(next);
    } catch (_) {
      // Keep only in process memory so the user can retry a transient secure
      // storage failure without replaying the one-time server redemption.
      rethrow;
    }
    await acknowledge(pc, transfer);
    _pendingPersistence.remove(transfer.transferId)?.clear();
  }

  Future<Map<String, dynamic>> _request(
    PcConnection pc,
    String method,
    String path, {
    Map<String, dynamic>? body,
  }) async {
    if (!pc.isConfigured) {
      throw const CredentialTransferException('PC接続が設定されていません。');
    }
    if (_closed) {
      throw const CredentialTransferException('クライアントは閉じられました。');
    }
    final uri = _uri(pc.baseUrl, path);
    final headers = _headers(pc.token);
    final response = method == 'GET'
        ? await _http
            .get(uri, headers: headers)
            .timeout(const Duration(seconds: 15))
        : await _http
            .post(uri, headers: headers, body: jsonEncode(body ?? const {}))
            .timeout(const Duration(seconds: 15));
    if (response.statusCode < 200 || response.statusCode >= 300) {
      throw CredentialTransferException(
        'credential転送に失敗しました (HTTP ${response.statusCode})',
        statusCode: response.statusCode,
      );
    }
    return _decodeData(response.body);
  }

  Map<String, dynamic> _decodeData(String body) {
    try {
      final decoded = jsonDecode(body) as Map<String, dynamic>;
      if (decoded['status'] != 'ok') {
        final err = decoded['error'];
        final message = err is Map ? err['message'] as String? : null;
        throw CredentialTransferException(
          message ?? 'PCからエラーが返されました。',
        );
      }
      return decoded['data'] as Map<String, dynamic>? ?? const {};
    } catch (error) {
      if (error is CredentialTransferException) rethrow;
      throw const CredentialTransferException('PC応答の解析に失敗しました。');
    }
  }

  String _trimTrailingSlash(String path) {
    if (path.isEmpty || path == '/') return '';
    return path.endsWith('/') ? path.substring(0, path.length - 1) : path;
  }
}

String _hex(List<int> bytes) =>
    bytes.map((value) => value.toRadixString(16).padLeft(2, '0')).join();
