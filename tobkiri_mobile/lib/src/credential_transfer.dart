import 'dart:convert';
import 'dart:typed_data';

import 'package:cryptography/cryptography.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:http/http.dart' as http;
import 'package:uuid/uuid.dart';

const credentialTransferScope = 'credentials.request';
const credentialTransferAlgorithm = 'X25519-HKDF-SHA256-AES-256-GCM';

abstract class SecretStorage {
  Future<String?> read(String key);
  Future<void> write(String key, String value);
  Future<void> delete(String key);
}

class FlutterSecretStorage implements SecretStorage {
  FlutterSecretStorage({FlutterSecureStorage? storage})
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

class MobileCredentialIdentity {
  const MobileCredentialIdentity({
    required this.deviceId,
    required this.signingPublicKey,
    required this.signingPrivateKey,
    required this.encryptionPublicKey,
    required this.encryptionPrivateKey,
  });

  final String deviceId;
  final String signingPublicKey;
  final String signingPrivateKey;
  final String encryptionPublicKey;
  final String encryptionPrivateKey;

  Map<String, Object> publicRegistration() => {
        'device_id': deviceId,
        'public_key': signingPublicKey,
        'encryption_public_key': encryptionPublicKey,
        'scopes': const [credentialTransferScope],
      };

  Map<String, Object> toJson() => {
        'device_id': deviceId,
        'signing_public_key': signingPublicKey,
        'signing_private_key': signingPrivateKey,
        'encryption_public_key': encryptionPublicKey,
        'encryption_private_key': encryptionPrivateKey,
      };

  factory MobileCredentialIdentity.fromJson(Map<String, dynamic> json) =>
      MobileCredentialIdentity(
        deviceId: json['device_id'] as String? ?? '',
        signingPublicKey: json['signing_public_key'] as String? ?? '',
        signingPrivateKey: json['signing_private_key'] as String? ?? '',
        encryptionPublicKey: json['encryption_public_key'] as String? ?? '',
        encryptionPrivateKey: json['encryption_private_key'] as String? ?? '',
      );

  bool get isValid =>
      deviceId.isNotEmpty &&
      signingPublicKey.startsWith('ed25519:') &&
      _decode(signingPrivateKey).length == 32 &&
      encryptionPublicKey.startsWith('x25519:') &&
      _decode(encryptionPrivateKey).length == 32;
}

class MobileCredentialIdentityStore {
  MobileCredentialIdentityStore({SecretStorage? storage})
      : _storage = storage ?? FlutterSecretStorage();

  static const _identityKey = 'rumi.mobile.credential_identity.v1';
  final SecretStorage _storage;

  Future<MobileCredentialIdentity> loadOrCreate() async {
    final raw = await _storage.read(_identityKey);
    if (raw != null && raw.isNotEmpty) {
      final decoded = jsonDecode(raw);
      if (decoded is! Map) {
        throw StateError('stored device identity is invalid');
      }
      final identity = MobileCredentialIdentity.fromJson(
        Map<String, dynamic>.from(decoded),
      );
      if (!identity.isValid) {
        throw StateError('stored device identity is invalid');
      }
      return identity;
    }
    final signing = await Ed25519().newKeyPair();
    final signingData = await signing.extract();
    final signingPublic = await signing.extractPublicKey();
    final encryption = await X25519().newKeyPair();
    final encryptionData = await encryption.extract();
    final encryptionPublic = await encryption.extractPublicKey();
    final identity = MobileCredentialIdentity(
      deviceId:
          'mobile-${const Uuid().v4().replaceAll('-', '').substring(0, 16)}',
      signingPublicKey: 'ed25519:${_encode(signingPublic.bytes)}',
      signingPrivateKey: _encode(signingData.bytes),
      encryptionPublicKey: 'x25519:${_encode(encryptionPublic.bytes)}',
      encryptionPrivateKey: _encode(encryptionData.bytes),
    );
    await _storage.write(_identityKey, jsonEncode(identity.toJson()));
    final verifiedRaw = await _storage.read(_identityKey);
    if (verifiedRaw == null) {
      throw StateError('device identity persistence could not be verified');
    }
    final verified = MobileCredentialIdentity.fromJson(
      Map<String, dynamic>.from(jsonDecode(verifiedRaw) as Map),
    );
    if (!verified.isValid ||
        jsonEncode(verified.toJson()) != jsonEncode(identity.toJson())) {
      throw StateError('device identity persistence could not be verified');
    }
    return verified;
  }

  Future<String> signDigest(Uint8List digest) async {
    final identity = await loadOrCreate();
    final public = SimplePublicKey(
      _decodePrefixed(identity.signingPublicKey, 'ed25519:'),
      type: KeyPairType.ed25519,
    );
    final pair = SimpleKeyPairData(
      _decode(identity.signingPrivateKey),
      publicKey: public,
      type: KeyPairType.ed25519,
    );
    final signature = await Ed25519().sign(digest, keyPair: pair);
    return _encode(signature.bytes);
  }

  Future<Map<String, dynamic>> decryptEnvelope(
    Map<String, dynamic> envelope, {
    required String transferId,
    required String deviceId,
    required int expiresAt,
  }) async {
    if (envelope['version'] != 1 ||
        envelope['alg'] != credentialTransferAlgorithm) {
      throw const FormatException('unsupported credential transfer envelope');
    }
    final identity = await loadOrCreate();
    if (identity.deviceId != deviceId) {
      throw const FormatException('credential transfer recipient mismatch');
    }
    final localPublic = SimplePublicKey(
      _decodePrefixed(identity.encryptionPublicKey, 'x25519:'),
      type: KeyPairType.x25519,
    );
    final localPair = SimpleKeyPairData(
      _decode(identity.encryptionPrivateKey),
      publicKey: localPublic,
      type: KeyPairType.x25519,
    );
    final remotePublic = SimplePublicKey(
      _decodePrefixed(
        envelope['ephemeral_public_key'] as String? ?? '',
        'x25519:',
      ),
      type: KeyPairType.x25519,
    );
    final shared = await X25519().sharedSecretKey(
      keyPair: localPair,
      remotePublicKey: remotePublic,
    );
    final key = await Hkdf(hmac: Hmac.sha256(), outputLength: 32).deriveKey(
      secretKey: shared,
      nonce: utf8.encode('rumi-provider-credential-transfer-v1'),
      info: utf8.encode('$transferId:$deviceId:$expiresAt'),
    );
    final expectedAad = utf8.encode(
      'rumi-provider-credential-transfer:v1:$transferId:$deviceId:$expiresAt',
    );
    final aad = _decode(envelope['aad'] as String? ?? '');
    if (!_constantTimeEquals(aad, expectedAad)) {
      throw const FormatException('credential transfer binding mismatch');
    }
    final box = SecretBox(
      _decode(envelope['ciphertext'] as String? ?? ''),
      nonce: _decode(envelope['nonce'] as String? ?? ''),
      mac: Mac(_decode(envelope['tag'] as String? ?? '')),
    );
    final clear = await AesGcm.with256bits().decrypt(
      box,
      secretKey: key,
      aad: aad,
    );
    final decoded = jsonDecode(utf8.decode(clear));
    if (decoded is! Map) {
      throw const FormatException('invalid credential transfer payload');
    }
    return Map<String, dynamic>.from(decoded);
  }
}

class PendingCredentialTransfer {
  const PendingCredentialTransfer({
    required this.transferId,
    required this.deviceId,
    required this.providerId,
    required this.accountId,
    required this.expiresAt,
    required this.challenge,
    required this.status,
  });

  final String transferId;
  final String deviceId;
  final String providerId;
  final String accountId;
  final int expiresAt;
  final String challenge;
  final String status;

  factory PendingCredentialTransfer.fromJson(Map<String, dynamic> json) =>
      PendingCredentialTransfer(
        transferId: json['transfer_id'] as String? ?? '',
        deviceId: json['device_id'] as String? ?? '',
        providerId: json['provider_id'] as String? ?? '',
        accountId: json['api_id'] as String? ?? '',
        expiresAt: (json['expires_at'] as num?)?.toInt() ?? 0,
        challenge: json['redemption_challenge'] as String? ?? '',
        status: json['status'] as String? ?? '',
      );

  bool get isExpired => DateTime.now().millisecondsSinceEpoch >= expiresAt;

  String canonicalMessage() => jsonEncode({
        'api_id': accountId,
        'challenge': challenge,
        'device_id': deviceId,
        'expires_at': expiresAt,
        'provider_id': providerId,
        'transfer_id': transferId,
      });
}

class CredentialVault {
  CredentialVault({SecretStorage? storage})
      : _storage = storage ?? FlutterSecretStorage();
  final SecretStorage _storage;

  String _key(String providerId, String accountId) =>
      'rumi.mobile.credential.v1.${_component(providerId)}.${_component(accountId)}';

  Future<void> persistVerified({
    required String providerId,
    required String accountId,
    required String credential,
  }) async {
    if (providerId.isEmpty || accountId.isEmpty || credential.isEmpty) {
      throw const FormatException('credential binding is incomplete');
    }
    final key = _key(providerId, accountId);
    await _storage.write(key, credential);
    final readBack = await _storage.read(key);
    if (readBack != credential) {
      await _storage.delete(key);
      throw StateError('credential persistence could not be verified');
    }
  }
}

class CredentialTransferClient {
  CredentialTransferClient({
    required String baseUrl,
    required String deviceToken,
    required this.identityStore,
    required this.vault,
    http.Client? client,
  })  : baseUri = Uri.parse(baseUrl),
        deviceToken = deviceToken.trim(),
        _client = client ?? http.Client();

  final Uri baseUri;
  final String deviceToken;
  final MobileCredentialIdentityStore identityStore;
  final CredentialVault vault;
  final http.Client _client;
  final Map<String, Map<String, dynamic>> _memoryOnlyAccepted = {};
  bool _closed = false;

  Future<List<PendingCredentialTransfer>> listPending() async {
    final data = await _request('GET', '/api/mobile/v1/credential-transfers');
    final values = data['transfers'] as List? ?? const [];
    return values
        .whereType<Map>()
        .map((item) => PendingCredentialTransfer.fromJson(
              Map<String, dynamic>.from(item),
            ))
        .where((item) =>
            !item.isExpired &&
            (item.status == 'pending' || item.status == 'accepted'))
        .toList(growable: false);
  }

  Future<void> redeemAndPersist(PendingCredentialTransfer transfer) async {
    if (_closed) throw StateError('credential transfer client is closed');
    final retained = _memoryOnlyAccepted.containsKey(transfer.transferId);
    if (transfer.isExpired ||
        (transfer.status != 'pending' &&
            !(transfer.status == 'accepted' && retained))) {
      throw StateError('credential transfer is not redeemable');
    }
    final identity = await identityStore.loadOrCreate();
    if (identity.deviceId != transfer.deviceId) {
      throw StateError('credential transfer belongs to another device');
    }
    var payload = _memoryOnlyAccepted[transfer.transferId];
    if (payload == null) {
      final digest =
          await Sha256().hash(utf8.encode(transfer.canonicalMessage()));
      final signature =
          await identityStore.signDigest(Uint8List.fromList(digest.bytes));
      final data = await _request(
        'POST',
        '/api/mobile/v1/credential-transfers/${Uri.encodeComponent(transfer.transferId)}',
        body: {'signature': signature},
      );
      final envelope = data['envelope'];
      if (envelope is! Map) {
        throw const FormatException('missing credential envelope');
      }
      payload = await identityStore.decryptEnvelope(
        Map<String, dynamic>.from(envelope),
        transferId: transfer.transferId,
        deviceId: transfer.deviceId,
        expiresAt: transfer.expiresAt,
      );
      _memoryOnlyAccepted[transfer.transferId] = payload;
    }
    if (payload['provider_id'] != transfer.providerId ||
        payload['api_id'] != transfer.accountId ||
        payload['expires_at'] != transfer.expiresAt) {
      throw const FormatException('credential payload binding mismatch');
    }
    final credential = payload['api_key'] as String? ?? '';
    await vault.persistVerified(
      providerId: transfer.providerId,
      accountId: transfer.accountId,
      credential: credential,
    );
    await _request(
      'POST',
      '/api/mobile/v1/credential-transfers/${Uri.encodeComponent(transfer.transferId)}/ack',
      body: const {},
    );
    _memoryOnlyAccepted.remove(transfer.transferId)?.clear();
  }

  Future<void> reject(PendingCredentialTransfer transfer) => _request(
        'POST',
        '/api/mobile/v1/credential-transfers/${Uri.encodeComponent(transfer.transferId)}/reject',
        body: const {'reason': 'rejected by recipient'},
      ).then((_) {});

  Future<Map<String, dynamic>> _request(
    String method,
    String path, {
    Map<String, dynamic>? body,
  }) async {
    if (_closed || deviceToken.isEmpty || baseUri.host.isEmpty) {
      throw StateError('device-authenticated PC connection is unavailable');
    }
    final uri = baseUri.replace(
      path:
          '${baseUri.path.endsWith('/') ? baseUri.path.substring(0, baseUri.path.length - 1) : baseUri.path}$path',
      query: null,
      fragment: null,
    );
    final headers = {
      'Authorization': 'Bearer $deviceToken',
      'Accept': 'application/json',
      'Content-Type': 'application/json',
      'X-Rumi-Client': 'rumi-mobile',
    };
    final response = method == 'GET'
        ? await _client.get(uri, headers: headers)
        : await _client.post(uri,
            headers: headers, body: jsonEncode(body ?? const {}));
    if (response.statusCode < 200 || response.statusCode >= 300) {
      throw StateError(
          'credential transfer request failed (${response.statusCode})');
    }
    final decoded = jsonDecode(response.body);
    if (decoded is! Map || decoded['status'] != 'ok') {
      throw StateError('credential transfer response is invalid');
    }
    final data = decoded['data'];
    return data is Map ? Map<String, dynamic>.from(data) : <String, dynamic>{};
  }

  void close() {
    _closed = true;
    for (final payload in _memoryOnlyAccepted.values) {
      payload.clear();
    }
    _memoryOnlyAccepted.clear();
    _client.close();
  }
}

String _component(String value) =>
    base64Url.encode(utf8.encode(value)).replaceAll('=', '');
String _encode(List<int> bytes) => base64Url.encode(bytes).replaceAll('=', '');
Uint8List _decode(String value) => Uint8List.fromList(
      base64Url.decode(base64Url.normalize(value)),
    );
Uint8List _decodePrefixed(String value, String prefix) {
  if (!value.startsWith(prefix)) {
    throw const FormatException('invalid public key');
  }
  final bytes = _decode(value.substring(prefix.length));
  if (bytes.length != 32) throw const FormatException('invalid public key');
  return bytes;
}

bool _constantTimeEquals(List<int> left, List<int> right) {
  if (left.length != right.length) return false;
  var difference = 0;
  for (var i = 0; i < left.length; i++) {
    difference |= left[i] ^ right[i];
  }
  return difference == 0;
}
