import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';

import 'package:rumi_remote_app/src/data/pc/durable_device_store.dart';
import 'package:rumi_remote_app/src/settings/api_config_store.dart';

class _ControllableSecureStorage implements SecureKeyValueStorage {
  final Map<String, String> values = <String, String>{};

  bool failReads = false;
  bool failWrites = false;
  bool dropWrites = false;
  int readCount = 0;
  int writeCount = 0;
  int deleteCount = 0;

  @override
  Future<String?> read(String key) async {
    readCount += 1;
    if (failReads) throw StateError('secure storage locked');
    return values[key];
  }

  @override
  Future<void> write(String key, String? value) async {
    writeCount += 1;
    if (failWrites) throw StateError('secure storage write failed');
    if (dropWrites) return;
    if (value == null) {
      values.remove(key);
    } else {
      values[key] = value;
    }
  }

  @override
  Future<void> delete(String key) async {
    deleteCount += 1;
    values.remove(key);
  }
}

Matcher identityFailure(DeviceIdentityFailureCode code) => isA<DeviceIdentityStorageException>()
    .having((error) => error.code, 'code', code);

void main() {
  const identityKey = 'rumi.device.identity.v1';

  test('first run returns only an identity that was written and read back', () async {
    final storage = _ControllableSecureStorage();
    final store = DurableMobileDeviceStore(storage: storage);

    final identity = await store.loadOrCreateIdentity();
    final persisted = jsonDecode(storage.values[identityKey]!) as Map<String, dynamic>;

    expect(identity.deviceId, persisted['deviceId']);
    expect(identity.publicKey, persisted['publicKey']);
    expect(identity.encryptionPublicKey, persisted['encryptionPublicKey']);
    expect(storage.writeCount, 1);
    expect(storage.readCount, 2);
  });

  test('a secure-storage read failure never creates or writes a new principal', () async {
    final storage = _ControllableSecureStorage()..failReads = true;
    final store = DurableMobileDeviceStore(storage: storage);

    await expectLater(
      store.loadOrCreateIdentity(),
      throwsA(identityFailure(DeviceIdentityFailureCode.storageReadFailed)),
    );

    expect(storage.writeCount, 0);
    expect(storage.values, isEmpty);
  });

  test('corrupt identity data is preserved and never overwritten', () async {
    final storage = _ControllableSecureStorage();
    storage.values[identityKey] = '{not-json';
    final store = DurableMobileDeviceStore(storage: storage);

    await expectLater(
      store.loadOrCreateIdentity(),
      throwsA(identityFailure(DeviceIdentityFailureCode.corruptRecord)),
    );

    expect(storage.writeCount, 0);
    expect(storage.values[identityKey], '{not-json');
  });

  test('new identity is not returned when persistence fails', () async {
    final storage = _ControllableSecureStorage()..failWrites = true;
    final store = DurableMobileDeviceStore(storage: storage);

    await expectLater(
      store.loadOrCreateIdentity(),
      throwsA(identityFailure(DeviceIdentityFailureCode.storageWriteFailed)),
    );

    expect(storage.values, isEmpty);
    expect(storage.writeCount, 1);
  });

  test('new identity is not returned when write acknowledgement is false', () async {
    final storage = _ControllableSecureStorage()..dropWrites = true;
    final store = DurableMobileDeviceStore(storage: storage);

    await expectLater(
      store.loadOrCreateIdentity(),
      throwsA(identityFailure(DeviceIdentityFailureCode.storageVerificationFailed)),
    );

    expect(storage.values, isEmpty);
    expect(storage.writeCount, 1);
  });

  test('transient read failure preserves the existing identity and can retry', () async {
    final storage = _ControllableSecureStorage();
    final firstStore = DurableMobileDeviceStore(storage: storage);
    final firstIdentity = await firstStore.loadOrCreateIdentity();
    final persistedBeforeFailure = storage.values[identityKey];

    final restartedStore = DurableMobileDeviceStore(storage: storage);
    storage.failReads = true;
    await expectLater(
      restartedStore.loadOrCreateIdentity(),
      throwsA(identityFailure(DeviceIdentityFailureCode.storageReadFailed)),
    );
    expect(storage.writeCount, 1);
    expect(storage.values[identityKey], persistedBeforeFailure);

    storage.failReads = false;
    final recovered = await restartedStore.loadOrCreateIdentity();
    expect(recovered.deviceId, firstIdentity.deviceId);
    expect(recovered.publicKey, firstIdentity.publicKey);
    expect(storage.writeCount, 1);
  });

  test('partial encryption identity is invalid and never silently rotated', () async {
    final storage = _ControllableSecureStorage();
    final firstStore = DurableMobileDeviceStore(storage: storage);
    await firstStore.loadOrCreateIdentity();
    final record = jsonDecode(storage.values[identityKey]!) as Map<String, dynamic>;
    record['encryptionPrivateKey'] = '';
    storage.values[identityKey] = jsonEncode(record);
    final writeCountBeforeLoad = storage.writeCount;

    final restartedStore = DurableMobileDeviceStore(storage: storage);
    await expectLater(
      restartedStore.loadOrCreateIdentity(),
      throwsA(identityFailure(DeviceIdentityFailureCode.incompleteRecord)),
    );

    expect(storage.writeCount, writeCountBeforeLoad);
    final unchanged = jsonDecode(storage.values[identityKey]!) as Map<String, dynamic>;
    expect(unchanged['deviceId'], record['deviceId']);
    expect(unchanged['encryptionPrivateKey'], isEmpty);
  });

  test('signing-only legacy upgrade blocks use when the upgrade cannot persist', () async {
    final storage = _ControllableSecureStorage();
    final firstStore = DurableMobileDeviceStore(storage: storage);
    await firstStore.loadOrCreateIdentity();
    final record = jsonDecode(storage.values[identityKey]!) as Map<String, dynamic>;
    record['encryptionPublicKey'] = '';
    record['encryptionPrivateKey'] = '';
    storage.values[identityKey] = jsonEncode(record);
    storage.failWrites = true;

    final restartedStore = DurableMobileDeviceStore(storage: storage);
    await expectLater(
      restartedStore.loadOrCreateIdentity(),
      throwsA(identityFailure(DeviceIdentityFailureCode.storageWriteFailed)),
    );

    final unchanged = jsonDecode(storage.values[identityKey]!) as Map<String, dynamic>;
    expect(unchanged['deviceId'], record['deviceId']);
    expect(unchanged['encryptionPublicKey'], isEmpty);
    expect(unchanged['encryptionPrivateKey'], isEmpty);
  });

  test('concurrent callers share one durable identity creation', () async {
    final storage = _ControllableSecureStorage();
    final store = DurableMobileDeviceStore(storage: storage);

    final identities = await Future.wait(
      List<Future<dynamic>>.generate(
        20,
        (_) => store.loadOrCreateIdentity(),
      ),
    );

    expect(identities.map((identity) => identity.deviceId).toSet(), hasLength(1));
    expect(identities.map((identity) => identity.publicKey).toSet(), hasLength(1));
    expect(storage.writeCount, 1);
  });

  test('approval signing uses the pinned durable identity', () async {
    final storage = _ControllableSecureStorage();
    final store = DurableMobileDeviceStore(storage: storage);
    final identity = await store.loadOrCreateIdentity();

    storage.failReads = true;
    final signature = await store.signApprovalPayloadHash(
      List<String>.filled(32, '00').join(),
    );

    expect(signature, isNotEmpty);
    expect((await store.loadOrCreateIdentity()).deviceId, identity.deviceId);
    expect(storage.writeCount, 1);
  });
}
