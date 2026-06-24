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
  label: 'iPhone',
  scopes: ['chat.read', 'chat.write'],
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
}
