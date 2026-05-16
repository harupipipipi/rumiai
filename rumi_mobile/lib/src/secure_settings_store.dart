import 'package:flutter_secure_storage/flutter_secure_storage.dart';

class RumiRemoteSettings {
  const RumiRemoteSettings({
    required this.baseUrl,
    required this.token,
    required this.autoRefresh,
  });

  static const defaults = RumiRemoteSettings(
    baseUrl: 'http://127.0.0.1:8765',
    token: '',
    autoRefresh: false,
  );

  final String baseUrl;
  final String token;
  final bool autoRefresh;

  RumiRemoteSettings copyWith({
    String? baseUrl,
    String? token,
    bool? autoRefresh,
  }) {
    return RumiRemoteSettings(
      baseUrl: baseUrl ?? this.baseUrl,
      token: token ?? this.token,
      autoRefresh: autoRefresh ?? this.autoRefresh,
    );
  }
}

class SecureSettingsStore {
  SecureSettingsStore({
    FlutterSecureStorage storage = const FlutterSecureStorage(
      aOptions: AndroidOptions(encryptedSharedPreferences: true),
    ),
  }) : _storage = storage;

  static const _baseUrlKey = 'rumi_remote.base_url';
  static const _tokenKey = 'rumi_remote.token';
  static const _autoRefreshKey = 'rumi_remote.auto_refresh';

  final FlutterSecureStorage _storage;

  Future<RumiRemoteSettings> load() async {
    final values = await Future.wait([
      _storage.read(key: _baseUrlKey),
      _storage.read(key: _tokenKey),
      _storage.read(key: _autoRefreshKey),
    ]);
    return RumiRemoteSettings(
      baseUrl: _withDefault(values[0], RumiRemoteSettings.defaults.baseUrl),
      token: values[1] ?? '',
      autoRefresh: values[2] == 'true',
    );
  }

  Future<void> save(RumiRemoteSettings settings) async {
    await Future.wait([
      _storage.write(key: _baseUrlKey, value: settings.baseUrl.trim()),
      _storage.write(key: _tokenKey, value: settings.token.trim()),
      _storage.write(key: _autoRefreshKey, value: settings.autoRefresh.toString()),
    ]);
  }
}

String _withDefault(String? value, String fallback) {
  final trimmed = value?.trim() ?? '';
  return trimmed.isEmpty ? fallback : trimmed;
}
