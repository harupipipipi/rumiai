import 'dart:convert';

import 'package:flutter/services.dart';

class ApiConfig {
  const ApiConfig({
    required this.baseUrl,
    required this.apiKey,
    required this.model,
    this.label = '',
    this.systemPrompt = '',
    this.temperature = 0.7,
  });

  static const empty = ApiConfig(
    baseUrl: 'https://api.openai.com/v1',
    apiKey: '',
    model: 'gpt-4o-mini',
  );

  static const defaults = ApiConfig(
    baseUrl: 'https://api.openai.com/v1',
    apiKey: '',
    model: 'gpt-4o-mini',
  );

  final String baseUrl;
  final String apiKey;
  final String model;
  final String label;
  final String systemPrompt;
  final double temperature;

  bool get isConfigured =>
      baseUrl.trim().isNotEmpty && apiKey.trim().isNotEmpty;

  ApiConfig copyWith({
    String? baseUrl,
    String? apiKey,
    String? model,
    String? label,
    String? systemPrompt,
    double? temperature,
  }) {
    return ApiConfig(
      baseUrl: baseUrl ?? this.baseUrl,
      apiKey: apiKey ?? this.apiKey,
      model: model ?? this.model,
      label: label ?? this.label,
      systemPrompt: systemPrompt ?? this.systemPrompt,
      temperature: temperature ?? this.temperature,
    );
  }

  Map<String, dynamic> toJson() => {
        'baseUrl': baseUrl,
        'apiKey': apiKey,
        'model': model,
        'label': label,
        'systemPrompt': systemPrompt,
        'temperature': temperature,
      };

  factory ApiConfig.fromJson(Map<String, dynamic> json) => ApiConfig(
        baseUrl: json['baseUrl'] as String? ?? defaults.baseUrl,
        apiKey: json['apiKey'] as String? ?? '',
        model: json['model'] as String? ?? defaults.model,
        label: json['label'] as String? ?? '',
        systemPrompt: json['systemPrompt'] as String? ?? '',
        temperature: (json['temperature'] as num?)?.toDouble() ?? 0.7,
      );
}

class PcConnection {
  const PcConnection({required this.baseUrl, required this.token});

  final String baseUrl;
  final String token;

  bool get isConfigured => baseUrl.trim().isNotEmpty && token.trim().isNotEmpty;

  Map<String, dynamic> toJson() => {'baseUrl': baseUrl, 'token': token};

  factory PcConnection.fromJson(Map<String, dynamic> json) => PcConnection(
        baseUrl: json['baseUrl'] as String? ?? '',
        token: json['token'] as String? ?? '',
      );
}

abstract class SecureKeyValueStorage {
  Future<String?> read(String key);
  Future<void> write(String key, String? value);
  Future<void> delete(String key);
}

class PlatformSecureStorage implements SecureKeyValueStorage {
  PlatformSecureStorage({MethodChannel? channel})
      : _channel =
            channel ?? const MethodChannel('ai.rumi.remote/secure_storage');

  final MethodChannel _channel;

  @override
  Future<String?> read(String key) async {
    return _channel.invokeMethod<String>('read', {'key': key});
  }

  @override
  Future<void> write(String key, String? value) async {
    if (value == null) {
      await delete(key);
      return;
    }
    await _channel.invokeMethod<void>('write', {'key': key, 'value': value});
  }

  @override
  Future<void> delete(String key) async {
    await _channel.invokeMethod<void>('delete', {'key': key});
  }
}

class ApiConfigStore {
  ApiConfigStore({
    SecureKeyValueStorage? storage,
  }) : _storage = storage ?? PlatformSecureStorage();

  static const _apiKey = 'rumi.api_config.v1';
  static const _pcKey = 'rumi.pc_connection.v1';

  final SecureKeyValueStorage _storage;

  Future<ApiConfig> loadApi() async {
    try {
      final raw = await _storage.read(_apiKey);
      if (raw == null || raw.trim().isEmpty) return ApiConfig.defaults;
      return ApiConfig.fromJson(jsonDecode(raw) as Map<String, dynamic>);
    } catch (_) {
      return ApiConfig.defaults;
    }
  }

  Future<void> saveApi(ApiConfig config) async {
    try {
      await _storage.write(_apiKey, jsonEncode(config.toJson()));
    } catch (_) {
      // ignore secure storage failures (e.g. simulator keychain unavailable)
    }
  }

  Future<PcConnection?> loadPc() async {
    try {
      final raw = await _storage.read(_pcKey);
      if (raw == null || raw.trim().isEmpty) return null;
      return PcConnection.fromJson(jsonDecode(raw) as Map<String, dynamic>);
    } catch (_) {
      return null;
    }
  }

  Future<void> savePc(PcConnection? pc) async {
    try {
      if (pc == null || !pc.isConfigured) {
        await _storage.delete(_pcKey);
        return;
      }
      await _storage.write(_pcKey, jsonEncode(pc.toJson()));
    } catch (_) {
      // ignore secure storage failures
    }
  }
}
