import 'dart:convert';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:uuid/uuid.dart';

import '../../settings/api_config_store.dart';

class DeviceIdentity {
  const DeviceIdentity({
    required this.deviceId,
    required this.deviceLabel,
    required this.publicKey,
  });

  final String deviceId;
  final String deviceLabel;
  final String publicKey;

  Map<String, dynamic> toJson() => {
        'deviceId': deviceId,
        'deviceLabel': deviceLabel,
        'publicKey': publicKey,
      };

  factory DeviceIdentity.fromJson(Map<String, dynamic> json) {
    return DeviceIdentity(
      deviceId: json['deviceId'] as String? ?? '',
      deviceLabel: json['deviceLabel'] as String? ?? '',
      publicKey: json['publicKey'] as String? ?? '',
    );
  }
}

class PairedDevice {
  const PairedDevice({
    required this.deviceId,
    required this.deviceToken,
    required this.label,
    required this.scopes,
    required this.pcBaseUrl,
    required this.pcLabel,
    required this.pairingId,
  });

  final String deviceId;
  final String deviceToken;
  final String label;
  final List<String> scopes;
  final String pcBaseUrl;
  final String pcLabel;
  final String pairingId;

  bool get canReadPcConversations => scopes.contains('chat.read');
  bool get canWritePcConversations => scopes.contains('chat.write');
  bool get canObservePcTools => scopes.contains('tools.observe');
  bool get canApprovePcTools => scopes.contains('tools.approve');
  bool get canRequestCredentialCopy => scopes.contains('credentials.request');

  PcConnection toPcConnection() =>
      PcConnection(baseUrl: pcBaseUrl, token: deviceToken);

  Map<String, dynamic> toJson() => {
        'deviceId': deviceId,
        'deviceToken': deviceToken,
        'label': label,
        'scopes': scopes,
        'pcBaseUrl': pcBaseUrl,
        'pcLabel': pcLabel,
        'pairingId': pairingId,
      };

  factory PairedDevice.fromJson(Map<String, dynamic> json) {
    return PairedDevice(
      deviceId: json['deviceId'] as String? ?? '',
      deviceToken: json['deviceToken'] as String? ?? '',
      label: json['label'] as String? ?? '',
      scopes: (json['scopes'] as List? ?? []).map((e) => e.toString()).toList(),
      pcBaseUrl: json['pcBaseUrl'] as String? ?? '',
      pcLabel: json['pcLabel'] as String? ?? '',
      pairingId: json['pairingId'] as String? ?? '',
    );
  }
}

class PairingV2Payload {
  const PairingV2Payload({
    required this.pairingId,
    required this.code,
    required this.baseUrls,
    required this.serverPublicKey,
    required this.expiresAt,
  });

  final String pairingId;
  final String code;
  final List<String> baseUrls;
  final String serverPublicKey;
  final int expiresAt;

  bool get isExpired => DateTime.now().millisecondsSinceEpoch > expiresAt;

  factory PairingV2Payload.fromJson(Map<String, dynamic> json) {
    return PairingV2Payload(
      pairingId: json['pairingId'] as String? ?? '',
      code: json['code'] as String? ?? '',
      baseUrls:
          (json['baseUrls'] as List? ?? []).map((e) => e.toString()).toList(),
      serverPublicKey: json['serverPublicKey'] as String? ?? '',
      expiresAt: (json['expiresAt'] as num?)?.toInt() ?? 0,
    );
  }
}

class _SecureStorageAdapter implements SecureKeyValueStorage {
  _SecureStorageAdapter([FlutterSecureStorage? storage])
      : _storage = storage ?? const FlutterSecureStorage();
  final FlutterSecureStorage _storage;

  @override
  Future<String?> read(String key) => _storage.read(key: key);

  @override
  Future<void> write(String key, String? value) =>
      _storage.write(key: key, value: value);

  @override
  Future<void> delete(String key) => _storage.delete(key: key);
}

class MobileDeviceStore {
  MobileDeviceStore({SecureKeyValueStorage? storage})
      : _storage = storage ?? _SecureStorageAdapter();

  static const _identityKey = 'rumi.device.identity.v1';
  static const _pairedKey = 'rumi.paired_device.v1';
  static const _legacyPcKey = 'rumi.pc_connection.v1';

  final SecureKeyValueStorage _storage;
  final _uuid = const Uuid();

  Future<DeviceIdentity> loadOrCreateIdentity() async {
    try {
      final raw = await _storage.read(_identityKey);
      if (raw != null && raw.trim().isNotEmpty) {
        return DeviceIdentity.fromJson(jsonDecode(raw) as Map<String, dynamic>);
      }
    } catch (_) {
      // fall through to create new
    }
    final identity = DeviceIdentity(
      deviceId: 'mobile-${_uuid.v4().substring(0, 12)}',
      deviceLabel: 'Rumi Mobile',
      publicKey: 'pk-${_uuid.v4()}',
    );
    try {
      await _storage.write(_identityKey, jsonEncode(identity.toJson()));
    } catch (_) {
      // ignore secure storage failures
    }
    return identity;
  }

  Future<PairedDevice?> loadPairedDevice() async {
    try {
      final raw = await _storage.read(_pairedKey);
      if (raw != null && raw.trim().isNotEmpty) {
        return PairedDevice.fromJson(jsonDecode(raw) as Map<String, dynamic>);
      }
    } catch (_) {
      // fall through to check legacy
    }
    // Migration: check legacy PcConnection
    try {
      final legacy = await _storage.read(_legacyPcKey);
      if (legacy != null && legacy.trim().isNotEmpty) {
        final pc =
            PcConnection.fromJson(jsonDecode(legacy) as Map<String, dynamic>);
        if (pc.isConfigured) {
          return PairedDevice(
            deviceId: 'legacy',
            deviceToken: pc.token,
            label: 'PC (legacy)',
            scopes: const ['chat.read', 'chat.write', 'tools.observe'],
            pcBaseUrl: pc.baseUrl,
            pcLabel: 'PC',
            pairingId: '',
          );
        }
      }
    } catch (_) {
      // ignore
    }
    return null;
  }

  Future<void> savePairedDevice(PairedDevice? device) async {
    try {
      if (device == null) {
        await _storage.delete(_pairedKey);
      } else {
        await _storage.write(_pairedKey, jsonEncode(device.toJson()));
      }
    } catch (_) {
      // ignore secure storage failures
    }
  }

  Future<void> clear() async {
    try {
      await _storage.delete(_pairedKey);
      await _storage.delete(_legacyPcKey);
    } catch (_) {
      // ignore
    }
  }
}
