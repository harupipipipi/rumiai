import 'dart:convert';
import 'dart:typed_data';

import 'package:cryptography/cryptography.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:http/http.dart' as http;

const mobileAuthorityScopes = <String>{
  'authority.request.list',
  'authority.request.read',
  'authority.request.approve',
  'authority.request.deny',
};

abstract class AuthoritySecretStore {
  Future<String?> read(String key);
  Future<void> write(String key, String value);
  Future<void> delete(String key);
}

class FlutterAuthoritySecretStore implements AuthoritySecretStore {
  FlutterAuthoritySecretStore({FlutterSecureStorage? storage})
      : _storage = storage ??
            const FlutterSecureStorage(
              aOptions: AndroidOptions(encryptedSharedPreferences: true),
            );

  final FlutterSecureStorage _storage;

  @override
  Future<String?> read(String key) => _storage.read(key: key);

  @override
  Future<void> write(String key, String value) =>
      _storage.write(key: key, value: value);

  @override
  Future<void> delete(String key) => _storage.delete(key: key);
}

class MobileAuthorityConnection {
  const MobileAuthorityConnection({
    required this.baseUrl,
    required this.deviceId,
    required this.approvalToken,
    required this.approvalScopes,
  });

  final String baseUrl;
  final String deviceId;
  final String approvalToken;
  final Set<String> approvalScopes;

  bool get isValid {
    final uri = Uri.tryParse(baseUrl);
    return uri != null &&
        uri.hasScheme &&
        uri.host.isNotEmpty &&
        deviceId.isNotEmpty &&
        approvalToken.isNotEmpty &&
        approvalScopes.containsAll(mobileAuthorityScopes) &&
        approvalScopes.every(mobileAuthorityScopes.contains);
  }

  Map<String, Object> toJson() => {
        'base_url': baseUrl,
        'device_id': deviceId,
        'approval_token': approvalToken,
        'approval_scopes': approvalScopes.toList()..sort(),
      };

  factory MobileAuthorityConnection.fromJson(Map<String, dynamic> json) =>
      MobileAuthorityConnection(
        baseUrl: json['base_url'] as String? ?? '',
        deviceId: json['device_id'] as String? ?? '',
        approvalToken: json['approval_token'] as String? ?? '',
        approvalScopes: (json['approval_scopes'] as List? ?? const [])
            .map((value) => value.toString())
            .toSet(),
      );
}

class MobileAuthorityConnectionStore {
  MobileAuthorityConnectionStore({AuthoritySecretStore? storage})
      : _storage = storage ?? FlutterAuthoritySecretStore();

  static const storageKey = 'rumi.mobile.authority_connection.v1';
  final AuthoritySecretStore _storage;

  Future<void> saveVerified(MobileAuthorityConnection connection) async {
    if (!connection.isValid) {
      throw StateError('authority connection is invalid');
    }
    final encoded = jsonEncode(connection.toJson());
    await _storage.write(storageKey, encoded);
    if (await _storage.read(storageKey) != encoded) {
      await _storage.delete(storageKey);
      throw StateError(
          'authority connection persistence could not be verified');
    }
  }

  Future<MobileAuthorityConnection?> load() async {
    final raw = await _storage.read(storageKey);
    if (raw == null || raw.isEmpty) return null;
    try {
      final decoded = jsonDecode(raw);
      if (decoded is! Map) throw const FormatException();
      final connection = MobileAuthorityConnection.fromJson(
        Map<String, dynamic>.from(decoded),
      );
      if (!connection.isValid) throw const FormatException();
      return connection;
    } catch (_) {
      throw StateError('stored authority connection is invalid');
    }
  }

  Future<void> clear() => _storage.delete(storageKey);
}

abstract class AuthorityPayloadSigner {
  Future<String> signPayloadHash(String payloadHash);
}

class SharedMobileIdentitySigner implements AuthorityPayloadSigner {
  SharedMobileIdentitySigner({AuthoritySecretStore? storage})
      : _storage = storage ?? FlutterAuthoritySecretStore();

  static const sharedIdentityKey = 'rumi.mobile.credential_identity.v1';
  final AuthoritySecretStore _storage;

  @override
  Future<String> signPayloadHash(String payloadHash) async {
    final raw = await _storage.read(sharedIdentityKey);
    if (raw == null || raw.isEmpty) {
      throw StateError('paired device signing identity is unavailable');
    }
    final decoded = jsonDecode(raw);
    if (decoded is! Map) throw StateError('paired device identity is invalid');
    final identity = Map<String, dynamic>.from(decoded);
    final publicValue = identity['signing_public_key'] as String? ?? '';
    final privateValue = identity['signing_private_key'] as String? ?? '';
    if (!publicValue.startsWith('ed25519:')) {
      throw StateError('paired device signing identity is invalid');
    }
    final publicBytes = _decode(publicValue.substring('ed25519:'.length));
    final privateBytes = _decode(privateValue);
    if (publicBytes.length != 32 || privateBytes.length != 32) {
      throw StateError('paired device signing identity is invalid');
    }
    final digest = _hexBytes(payloadHash);
    if (digest.length != 32) {
      throw StateError('approval payload hash is invalid');
    }
    final pair = SimpleKeyPairData(
      privateBytes,
      publicKey: SimplePublicKey(publicBytes, type: KeyPairType.ed25519),
      type: KeyPairType.ed25519,
    );
    final signature = await Ed25519().sign(digest, keyPair: pair);
    return base64Url.encode(signature.bytes).replaceAll('=', '');
  }
}

class AuthorityRequestItem {
  const AuthorityRequestItem({
    required this.requestId,
    required this.status,
    required this.principalId,
    required this.permissionId,
    required this.reason,
    required this.riskLevel,
    required this.resource,
    this.expiresAt = '',
  });

  final String requestId;
  final String status;
  final String principalId;
  final String permissionId;
  final String reason;
  final String riskLevel;
  final Map<String, dynamic> resource;
  final String expiresAt;

  bool get isPending => status == 'pending';
  bool get isExpired {
    if (expiresAt.isEmpty) return false;
    final value = DateTime.tryParse(expiresAt);
    return value != null && !value.isAfter(DateTime.now().toUtc());
  }

  bool get isHighImpact => const {'high', 'critical'}.contains(riskLevel);

  factory AuthorityRequestItem.fromJson(Map<String, dynamic> json) =>
      AuthorityRequestItem(
        requestId: json['request_id'] as String? ?? '',
        status: json['status'] as String? ?? '',
        principalId: json['principal_id'] as String? ?? '',
        permissionId: json['permission_id'] as String? ?? '',
        reason: json['reason'] as String? ?? '',
        riskLevel: json['risk_level'] as String? ?? 'low',
        resource: json['resource'] is Map
            ? Map<String, dynamic>.from(json['resource'] as Map)
            : <String, dynamic>{},
        expiresAt: json['expires_at'] as String? ?? '',
      );
}

class MobileAuthorityClient {
  MobileAuthorityClient({
    required this.connection,
    required this.signer,
    http.Client? client,
    this.timeout = const Duration(seconds: 15),
  }) : _client = client ?? http.Client();

  final MobileAuthorityConnection connection;
  final AuthorityPayloadSigner signer;
  final http.Client _client;
  final Duration timeout;
  bool _closed = false;

  Future<List<AuthorityRequestItem>> listPending() async {
    final data = await _request('GET', '/api/authority/requests',
        query: const {'status': 'pending'});
    final raw =
        (data['pending'] as List?) ?? (data['requests'] as List?) ?? const [];
    return raw
        .whereType<Map>()
        .map((item) =>
            AuthorityRequestItem.fromJson(Map<String, dynamic>.from(item)))
        .where((item) => item.requestId.isNotEmpty && item.isPending)
        .toList(growable: false);
  }

  Future<AuthorityRequestItem> getRequest(String requestId) async {
    final data = await _request(
      'GET',
      '/api/authority/requests/${Uri.encodeComponent(requestId)}',
    );
    return AuthorityRequestItem.fromJson(data);
  }

  Future<Map<String, dynamic>> approve(AuthorityRequestItem request) =>
      _settle(request, decision: 'approve');

  Future<Map<String, dynamic>> deny(
    AuthorityRequestItem request, {
    String reason = '',
  }) =>
      _settle(request, decision: 'deny', reason: reason);

  Future<Map<String, dynamic>> _settle(
    AuthorityRequestItem request, {
    required String decision,
    String reason = '',
  }) async {
    if (!request.isPending || request.isExpired) {
      throw StateError('authority request is not pending');
    }
    final encodedId = Uri.encodeComponent(request.requestId);
    final current = await getRequest(request.requestId);
    if (!current.isPending || current.isExpired) {
      throw StateError('authority request is not pending');
    }
    final challenge = await _request(
      'POST',
      '/api/authority/requests/$encodedId/challenge',
      body: {'decision': decision, 'scope': 'once'},
    );
    final payloadHash = challenge['payload_hash'] as String? ?? '';
    final challengeData = challenge['challenge'] is Map
        ? Map<String, dynamic>.from(challenge['challenge'] as Map)
        : const <String, dynamic>{};
    final challengeId = challengeData['challenge_id'] as String? ?? '';
    if (payloadHash.isEmpty || challengeId.isEmpty) {
      throw StateError('authority challenge is incomplete');
    }
    final signature = await signer.signPayloadHash(payloadHash);
    final attestation = {
      'challenge_id': challengeId,
      'payload_hash': payloadHash,
      'signature': signature,
      'signature_algorithm': 'ed25519',
    };
    return _request(
      'POST',
      '/api/authority/requests/$encodedId/${decision == 'approve' ? 'approve' : 'deny'}',
      body: {
        if (decision == 'approve') 'scope': 'once',
        if (decision == 'deny' && reason.isNotEmpty) 'reason': reason,
        'attestation': attestation,
      },
    );
  }

  Future<Map<String, dynamic>> _request(
    String method,
    String path, {
    Map<String, String>? query,
    Map<String, dynamic>? body,
  }) async {
    if (_closed) throw StateError('authority client is closed');
    if (!connection.isValid) {
      throw StateError('authority connection is invalid');
    }
    final base = Uri.parse(connection.baseUrl);
    var uri = base.replace(
      path: '${_trimTrailingSlash(base.path)}$path',
      query: null,
      fragment: null,
    );
    if (query != null) uri = uri.replace(queryParameters: query);
    final request = http.Request(method, uri)
      ..headers.addAll({
        'Accept': 'application/json',
        'Authorization': 'Bearer ${connection.approvalToken}',
        'X-Rumi-Client': 'rumi-mobile',
        if (body != null) 'Content-Type': 'application/json; charset=utf-8',
      });
    if (body != null) request.body = jsonEncode(body);
    final response = await http.Response.fromStream(
      await _client.send(request).timeout(timeout),
    );
    final decoded = response.body.trim().isEmpty
        ? <String, dynamic>{}
        : jsonDecode(utf8.decode(response.bodyBytes));
    if (response.statusCode < 200 ||
        response.statusCode >= 300 ||
        decoded is! Map ||
        decoded['status'] == 'error' ||
        decoded['success'] == false) {
      throw StateError('authority request failed (${response.statusCode})');
    }
    final data = decoded['data'];
    return data is Map ? Map<String, dynamic>.from(data) : <String, dynamic>{};
  }

  void close() {
    _closed = true;
    _client.close();
  }
}

String _trimTrailingSlash(String path) {
  if (path.isEmpty || path == '/') return '';
  return path.endsWith('/') ? path.substring(0, path.length - 1) : path;
}

Uint8List _decode(String value) => Uint8List.fromList(
      base64Url.decode(base64Url.normalize(value)),
    );

Uint8List _hexBytes(String value) {
  final normalized = value.trim();
  if (normalized.length.isOdd ||
      !RegExp(r'^[0-9a-fA-F]+$').hasMatch(normalized)) {
    return Uint8List(0);
  }
  return Uint8List.fromList(List<int>.generate(
    normalized.length ~/ 2,
    (index) =>
        int.parse(normalized.substring(index * 2, index * 2 + 2), radix: 16),
  ));
}
