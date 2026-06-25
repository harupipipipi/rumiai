import 'package:flutter_test/flutter_test.dart';

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

void main() {
  test('mobile notification settings default PC task finish notifications on',
      () async {
    final store = ApiConfigStore(storage: _FakeSecureStorage());

    final settings = await store.loadNotificationSettings();

    expect(settings.pcTaskFinishedEnabled, isTrue);
  });

  test('mobile notification settings persist PC task finish preference',
      () async {
    final storage = _FakeSecureStorage();
    final store = ApiConfigStore(storage: storage);

    await store.saveNotificationSettings(
      const MobileNotificationSettings(pcTaskFinishedEnabled: false),
    );

    final settings = await store.loadNotificationSettings();
    expect(settings.pcTaskFinishedEnabled, isFalse);
  });

  test('provider configs persist and replace by provider id', () async {
    final store = ApiConfigStore(storage: _FakeSecureStorage());

    await store.upsertProviderConfig(
      const MobileProviderConfig(
        providerId: 'openrouter',
        displayName: 'OpenRouter',
        label: 'Router',
        apiKey: 'sk-one',
        baseUrl: 'https://openrouter.ai/api/v1',
        model: 'openai/gpt-4o-mini',
      ),
    );
    await store.upsertProviderConfig(
      const MobileProviderConfig(
        providerId: 'openrouter',
        displayName: 'OpenRouter',
        label: 'Router 2',
        apiKey: 'sk-two',
        baseUrl: 'https://openrouter.ai/api/v1',
        model: 'openai/gpt-4o-mini',
      ),
    );

    final configs = await store.loadProviderConfigs();
    expect(configs, hasLength(1));
    expect(configs.single.providerId, 'openrouter');
    expect(configs.single.label, 'Router 2');
    expect(configs.single.apiKey, 'sk-two');
  });
}
