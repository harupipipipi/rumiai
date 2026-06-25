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
  approvalScopes: ['tools.approve'],
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

  test('legacy pc connection does not resurrect paired state', () async {
    final storage = _FakeSecureStorage();
    final store = MobileDeviceStore(storage: storage);

    await storage.write(
      'rumi.pc_connection.v1',
      jsonEncode({
        'baseUrl': 'http://192.168.11.25:8765',
        'token': 'dtk-legacy',
      }),
    );

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
    expect(reloaded.scopes, ['chat.read', 'chat.write']);
    expect(reloaded.approvalScopes, ['tools.approve']);
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
}
