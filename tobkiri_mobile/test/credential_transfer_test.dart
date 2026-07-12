import 'dart:convert';
import 'dart:typed_data';

import 'package:cryptography/cryptography.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:rumi_remote_app/src/credential_transfer.dart';
import 'package:rumi_remote_app/src/pairing_payload.dart';

class MemorySecretStorage implements SecretStorage {
  final values = <String, String>{};
  bool corruptWrites = false;

  @override
  Future<void> delete(String key) async => values.remove(key);

  @override
  Future<String?> read(String key) async => values[key];

  @override
  Future<void> write(String key, String value) async {
    values[key] = corruptWrites ? '$value-corrupt' : value;
  }
}

String encodeBytes(List<int> bytes) =>
    base64Url.encode(bytes).replaceAll('=', '');

Uint8List decodeBytes(String value) =>
    Uint8List.fromList(base64Url.decode(base64Url.normalize(value)));

Future<Map<String, dynamic>> makeEnvelope({
  required MobileCredentialIdentity identity,
  required String transferId,
  required int expiresAt,
  Map<String, dynamic>? payload,
}) async {
  final ephemeral = await X25519().newKeyPair();
  final ephemeralPublic = await ephemeral.extractPublicKey();
  final recipient = SimplePublicKey(
    decodeBytes(identity.encryptionPublicKey.substring('x25519:'.length)),
    type: KeyPairType.x25519,
  );
  final shared = await X25519().sharedSecretKey(
    keyPair: ephemeral,
    remotePublicKey: recipient,
  );
  final key = await Hkdf(hmac: Hmac.sha256(), outputLength: 32).deriveKey(
    secretKey: shared,
    nonce: utf8.encode('rumi-provider-credential-transfer-v1'),
    info: utf8.encode('$transferId:${identity.deviceId}:$expiresAt'),
  );
  final aad = utf8.encode(
    'rumi-provider-credential-transfer:v1:$transferId:${identity.deviceId}:$expiresAt',
  );
  final box = await AesGcm.with256bits().encrypt(
    utf8.encode(jsonEncode(payload ??
        {
          'provider_id': 'provider-a',
          'api_id': 'account-a',
          'expires_at': expiresAt,
          'api_key': 'test-secret',
        })),
    secretKey: key,
    aad: aad,
  );
  return {
    'version': 1,
    'alg': credentialTransferAlgorithm,
    'ephemeral_public_key': 'x25519:${encodeBytes(ephemeralPublic.bytes)}',
    'nonce': encodeBytes(box.nonce),
    'ciphertext': encodeBytes(box.cipherText),
    'tag': encodeBytes(box.mac.bytes),
    'aad': encodeBytes(aad),
  };
}

void main() {
  test(
      'identity persists Ed25519 and X25519 private keys only in secure storage',
      () async {
    final storage = MemorySecretStorage();
    final store = MobileCredentialIdentityStore(storage: storage);
    final identity = await store.loadOrCreate();
    final reloaded = await store.loadOrCreate();

    expect(reloaded.deviceId, identity.deviceId);
    expect(identity.publicRegistration(), {
      'device_id': identity.deviceId,
      'public_key': identity.signingPublicKey,
      'encryption_public_key': identity.encryptionPublicKey,
      'scopes': [credentialTransferScope],
    });
    expect(identity.publicRegistration().toString(),
        isNot(contains(identity.signingPrivateKey)));
    expect(identity.publicRegistration().toString(),
        isNot(contains(identity.encryptionPrivateKey)));
  });

  test('redemption message matches the backend cross-language vector', () {
    const transfer = PendingCredentialTransfer(
      transferId: 'ctr_vector',
      deviceId: 'device-vector',
      providerId: 'fake-provider',
      accountId: 'fake-account',
      expiresAt: 1893456000000,
      challenge: 'rch_vector',
      status: 'pending',
    );
    expect(
      transfer.canonicalMessage(),
      '{"api_id":"fake-account","challenge":"rch_vector",'
      '"device_id":"device-vector","expires_at":1893456000000,'
      '"provider_id":"fake-provider","transfer_id":"ctr_vector"}',
    );
  });

  test('decrypts the exact bound X25519 HKDF AES-GCM envelope', () async {
    final store = MobileCredentialIdentityStore(storage: MemorySecretStorage());
    final identity = await store.loadOrCreate();
    const transferId = 'ctr-test';
    const expiresAt = 1893456000000;
    final envelope = await makeEnvelope(
      identity: identity,
      transferId: transferId,
      expiresAt: expiresAt,
    );
    final clear = await store.decryptEnvelope(
      envelope,
      transferId: transferId,
      deviceId: identity.deviceId,
      expiresAt: expiresAt,
    );
    expect(clear['api_key'], 'test-secret');

    await expectLater(
      store.decryptEnvelope(
        envelope,
        transferId: '$transferId-altered',
        deviceId: identity.deviceId,
        expiresAt: expiresAt,
      ),
      throwsFormatException,
    );
  });

  test('credential vault requires a verified durable read-back', () async {
    final storage = MemorySecretStorage()..corruptWrites = true;
    final vault = CredentialVault(storage: storage);
    await expectLater(
      vault.persistVerified(
        providerId: 'provider-a',
        accountId: 'account-a',
        credential: 'test-secret',
      ),
      throwsStateError,
    );
    expect(storage.values, isEmpty);
  });

  test('ACK follows verified storage and accepted payload retries in memory',
      () async {
    final identityStorage = MemorySecretStorage();
    final identityStore = MobileCredentialIdentityStore(
      storage: identityStorage,
    );
    final identity = await identityStore.loadOrCreate();
    final vaultStorage = MemorySecretStorage()..corruptWrites = true;
    const expiresAt = 1893456000000;
    final transfer = PendingCredentialTransfer(
      transferId: 'ctr-retry',
      deviceId: identity.deviceId,
      providerId: 'provider-a',
      accountId: 'account-a',
      expiresAt: expiresAt,
      challenge: 'challenge-a',
      status: 'pending',
    );
    final envelope = await makeEnvelope(
      identity: identity,
      transferId: transfer.transferId,
      expiresAt: expiresAt,
    );
    var redeemRequests = 0;
    var ackRequests = 0;
    final httpClient = MockClient((request) async {
      if (request.url.path.endsWith('/ack')) {
        ackRequests += 1;
        return http.Response('{"status":"ok","data":{}}', 200);
      }
      redeemRequests += 1;
      return http.Response(
        jsonEncode({
          'status': 'ok',
          'data': {'envelope': envelope}
        }),
        200,
      );
    });
    final client = CredentialTransferClient(
      baseUrl: 'https://pc.example',
      deviceToken: 'device-token',
      identityStore: identityStore,
      vault: CredentialVault(storage: vaultStorage),
      client: httpClient,
    );

    await expectLater(client.redeemAndPersist(transfer), throwsStateError);
    expect(redeemRequests, 1);
    expect(ackRequests, 0);

    vaultStorage.corruptWrites = false;
    await client.redeemAndPersist(PendingCredentialTransfer(
      transferId: transfer.transferId,
      deviceId: transfer.deviceId,
      providerId: transfer.providerId,
      accountId: transfer.accountId,
      expiresAt: transfer.expiresAt,
      challenge: transfer.challenge,
      status: 'accepted',
    ));
    expect(redeemRequests, 1,
        reason: 'accepted envelope must stay memory-only');
    expect(ackRequests, 1);
    client.close();
  });

  test('pairing payload rejects legacy or credential-bearing QR values', () {
    expect(
      () => MobilePairingPayload.parse('rumi_api://host?token=secret'),
      throwsFormatException,
    );
    expect(
      () => MobilePairingPayload.parse(jsonEncode({
        'version': 2,
        'pairing_id': 'pair-1',
        'base_url': 'https://pc.example',
        'token': 'secret',
      })),
      throwsFormatException,
    );
    final parsed = MobilePairingPayload.parse(jsonEncode({
      'version': 2,
      'pairing_id': 'pair-1',
      'base_url': 'https://pc.example',
    }));
    expect(parsed.pairingId, 'pair-1');
  });
}
