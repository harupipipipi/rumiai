import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';

import 'package:rumi_remote_app/src/data/pc/device_store.dart';
import 'package:rumi_remote_app/src/settings/api_config_store.dart';

class _FakeSecureStorage implements SecureKeyValueStorage {
  final Map<String, String> _values = {};

  @override
  Future<String?> read(String key) async => _values[key];

  @override
  Future<void> write(String key, String? value) async {
    if (value == null) {
      _values.remove(key);
    } else {
      _values[key] = value;
    }
  }

  @override
  Future<void> delete(String key) async {
    _values.remove(key);
  }
}

const _validDevice = PairedDevice(
  deviceId: 'mobile-1',
  deviceToken: 'dtk-test',
  approvalToken: 'dtk-approve',
  label: 'iPhone',
  scopes: ['chat.read', 'chat.write'],
  approvalScopes: [
    'authority.request.approve',
    'authority.request.deny',
    'authority.request.list',
    'authority.request.read',
  ],
  pcBaseUrl: 'http://192.168.11.25:8765',
  pcLabel: 'Mac',
  pairingId: 'pair-1',
);

const _missingTokenDevice = PairedDevice(
  deviceId: 'mobile-2',
  deviceToken: '',
  label: 'iPhone',
  scopes: ['chat.read', 'chat.write'],
  pcBaseUrl: 'http://192.168.11.25:8765',
  pcLabel: 'Mac',
  pairingId: 'pair-2',
);

void main() {
  test('preferredPairingBaseUrl prefers reachable LAN addresses', () {
    final selected = preferredPairingBaseUrl(const [
      'http://169.254.193.88:8765',
      'http://172.16.0.2:8765',
      'http://192.168.11.25:8765',
      'http://[fe80::1]:8765',
    ]);

    expect(selected, 'http://192.168.11.25:8765');
  });

  test('preferredPairingBaseUrl falls back to first usable url', () {
    final selected = preferredPairingBaseUrl(const [
      '',
      'http://[fe80::1]:8765',
      'http://169.254.193.88:8765',
    ]);

    expect(selected, 'http://[fe80::1]:8765');
  });

  test('does not persist or load paired devices without a token', () async {
    final store = MobileDeviceStore(storage: _FakeSecureStorage());

    await store.savePairedDevice(_missingTokenDevice);

    expect(await store.loadPairedDevice(), isNull);
    expect(await store.loadPairedDevices(), isEmpty);
  });

  test('clear removes the active device and paired device list', () async {
    final store = MobileDeviceStore(storage: _FakeSecureStorage());

    await store.savePairedDevice(_validDevice);
    expect(await store.loadPairedDevice(), isNotNull);
    expect(await store.loadPairedDevices(), hasLength(1));

    await store.clear();

    expect(await store.loadPairedDevice(), isNull);
    expect(await store.loadPairedDevices(), isEmpty);
  });

  test('keeps multiple PCs paired to the same mobile device id', () async {
    final store = MobileDeviceStore(storage: _FakeSecureStorage());
    final secondPc = PairedDevice(
      deviceId: _validDevice.deviceId,
      deviceToken: 'dtk-second',
      approvalToken: 'dtk-approve-second',
      label: _validDevice.label,
      scopes: _validDevice.scopes,
      approvalScopes: _validDevice.approvalScopes,
      pcBaseUrl: 'http://192.168.11.26:8765',
      pcLabel: 'Studio Mac',
      pairingId: 'pair-2',
    );

    await store.savePairedDevice(_validDevice);
    await store.savePairedDevice(secondPc);

    final devices = await store.loadPairedDevices();
    expect(devices, hasLength(2));
    expect(
      devices.map((d) => d.connectionId),
      containsAll(['pair-1', 'pair-2']),
    );

    await store.removePairedDevice(_validDevice.connectionId);
    final remaining = await store.loadPairedDevices();
    expect(remaining, hasLength(1));
    expect(remaining.single.pcLabel, 'Studio Mac');
  });

  test('migrates legacy pc connection into paired devices once', () async {
    final storage = _FakeSecureStorage();
    final store = MobileDeviceStore(storage: storage);

    await storage.write(
      'rumi.pc_connection.v1',
      jsonEncode({
        'baseUrl': 'http://192.168.11.25:8765',
        'token': 'dtk-legacy',
      }),
    );

    final migrated = await store.loadPairedDevice();
    expect(migrated, isNotNull);
    expect(migrated!.deviceToken, 'dtk-legacy');
    expect(migrated.approvalToken, isEmpty);
    expect(migrated.scopes, ['chat.read', 'chat.write', 'tools.observe']);
    expect(migrated.approvalScopes, isEmpty);
    expect(migrated.canApprovePcTools, isFalse);
    expect(migrated.pcBaseUrl, 'http://192.168.11.25:8765');
    expect(storage._values.containsKey('rumi.pc_connection.v1'), isFalse);

    final devices = await store.loadPairedDevices();
    expect(devices, hasLength(1));
    expect(devices.single.connectionId, migrated.connectionId);

    await store.removePairedDevice(migrated.connectionId);
    expect(await store.loadPairedDevice(), isNull);
    expect(await store.loadPairedDevices(), isEmpty);
  });

  test('paired device keeps normal and approval tokens separate', () {
    expect(_validDevice.toPcConnection().token, 'dtk-test');
    expect(_validDevice.toPcConnection().approvalToken, 'dtk-approve');
    expect(_validDevice.canApprovePcTools, isTrue);

    final json = _validDevice.toJson();
    final reloaded = PairedDevice.fromJson(json);
    expect(reloaded.deviceToken, 'dtk-test');
    expect(reloaded.approvalToken, 'dtk-approve');
    expect(reloaded.clientToken, 'dtk-test');
    expect(reloaded.approverToken, 'dtk-approve');
    expect(reloaded.scopes, ['chat.read', 'chat.write']);
    expect(reloaded.approvalScopes, [
      'authority.request.approve',
      'authority.request.deny',
      'authority.request.list',
      'authority.request.read',
    ]);
    expect(reloaded.canApprovePcTools, isTrue);
  });

  test('tools.approve in normal scopes does not enable approvals', () {
    const device = PairedDevice(
      deviceId: 'mobile-3',
      deviceToken: 'dtk-test',
      label: 'iPhone',
      scopes: ['chat.read', 'tools.approve'],
      pcBaseUrl: 'http://192.168.11.25:8765',
      pcLabel: 'Mac',
      pairingId: 'pair-3',
    );

    expect(device.canApprovePcTools, isFalse);
  });

  test('device identity stores an Ed25519 signing key', () async {
    final store = MobileDeviceStore(storage: _FakeSecureStorage());

    final identity = await store.loadOrCreateIdentity();
    final signature = await store.signApprovalPayloadHash(
      List.filled(32, '00').join(),
    );

    expect(identity.publicKey, startsWith('ed25519:'));
    expect(identity.privateKey, isNotEmpty);
    expect(signature, isNotEmpty);
  });
}
