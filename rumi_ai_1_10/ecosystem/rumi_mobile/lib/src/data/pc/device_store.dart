import 'dart:convert';

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
    this.approvalToken = '',
    required this.label,
    required this.scopes,
    this.approvalScopes = const [],
    required this.pcBaseUrl,
    required this.pcLabel,
    required this.pairingId,
  });

  final String deviceId;
  final String deviceToken;
  final String approvalToken;
  final String label;
  final List<String> scopes;
  final List<String> approvalScopes;
  final String pcBaseUrl;
  final String pcLabel;
  final String pairingId;

  bool get canReadPcConversations => scopes.contains('chat.read');
  bool get canWritePcConversations => scopes.contains('chat.write');
  bool get canObservePcTools => scopes.contains('tools.observe');
  bool get canApprovePcTools =>
      approvalToken.trim().isNotEmpty &&
      approvalScopes.contains('tools.approve');
  bool get canRequestCredentialCopy => scopes.contains('credentials.request');
  bool get isConfigured =>
      deviceToken.trim().isNotEmpty && pcBaseUrl.trim().isNotEmpty;
  String get displayPcLabel => friendlyPcLabel(pcLabel, pcBaseUrl);

  PcConnection toPcConnection() => PcConnection(
        baseUrl: pcBaseUrl,
        token: deviceToken,
        approvalToken: approvalToken,
      );

  Map<String, dynamic> toJson() => {
        'deviceId': deviceId,
        'deviceToken': deviceToken,
        'approvalToken': approvalToken,
        'label': label,
        'scopes': scopes,
        'approvalScopes': approvalScopes,
        'pcBaseUrl': pcBaseUrl,
        'pcLabel': pcLabel,
        'pairingId': pairingId,
      };

  factory PairedDevice.fromJson(Map<String, dynamic> json) {
    return PairedDevice(
      deviceId: json['deviceId'] as String? ?? '',
      deviceToken: json['deviceToken'] as String? ?? '',
      approvalToken: json['approvalToken'] as String? ?? '',
      label: json['label'] as String? ?? '',
      scopes: (json['scopes'] as List? ?? []).map((e) => e.toString()).toList(),
      approvalScopes: (json['approvalScopes'] as List? ?? [])
          .map((e) => e.toString())
          .toList(),
      pcBaseUrl: json['pcBaseUrl'] as String? ?? '',
      pcLabel: json['pcLabel'] as String? ?? '',
      pairingId: json['pairingId'] as String? ?? '',
    );
  }
}

String friendlyPcLabel(String? label, String baseUrl) {
  final trimmed = (label ?? '').trim();
  if (trimmed.isNotEmpty && !_looksLikeUrl(trimmed)) return trimmed;

  final host = _hostFromBaseUrl(baseUrl);
  if (host.isEmpty || _looksLikeIpAddress(host)) return 'PC';
  final withoutLocal = host
      .replaceFirst(RegExp(r'\.local$', caseSensitive: false), '')
      .replaceFirst(RegExp(r'\.lan$', caseSensitive: false), '');
  return withoutLocal.isEmpty ? 'PC' : withoutLocal;
}

String preferredPairingBaseUrl(List<String> baseUrls) {
  var selected = '';
  var selectedScore = -1;
  for (final rawUrl in baseUrls) {
    final url = rawUrl.trim();
    if (url.isEmpty) continue;
    final score = _pairingBaseUrlScore(url);
    if (score > selectedScore) {
      selected = url;
      selectedScore = score;
    }
  }
  return selected;
}

int _pairingBaseUrlScore(String url) {
  final host = _hostFromBaseUrl(url).toLowerCase();
  if (host.isEmpty) return 0;
  if (host == 'localhost' || host == '127.0.0.1' || host == '::1') return 10;
  if (host.startsWith('169.254.') || host.startsWith('fe80:')) return 20;
  if (host.startsWith('192.168.')) return 100;
  if (host.startsWith('10.')) return 95;
  if (_isPrivate172Address(host)) return 95;
  if (!_looksLikeIpAddress(host)) return 90;
  return 50;
}

bool _isPrivate172Address(String host) {
  final match = RegExp(r'^172\.(\d{1,3})\.').firstMatch(host);
  if (match == null) return false;
  final secondOctet = int.tryParse(match.group(1) ?? '');
  return secondOctet != null && secondOctet >= 16 && secondOctet <= 31;
}

bool _looksLikeUrl(String value) {
  final lower = value.toLowerCase();
  return lower.startsWith('http://') || lower.startsWith('https://');
}

String _hostFromBaseUrl(String baseUrl) {
  final trimmed = baseUrl.trim();
  if (trimmed.isEmpty) return '';
  final normalized = trimmed.contains('://') ? trimmed : 'http://$trimmed';
  return Uri.tryParse(normalized)?.host ?? '';
}

bool _looksLikeIpAddress(String value) {
  return RegExp(r'^\d{1,3}(\.\d{1,3}){3}$').hasMatch(value) ||
      value.contains(':');
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

class MobileDeviceStore {
  MobileDeviceStore({SecureKeyValueStorage? storage})
      : _storage = storage ?? PlatformSecureStorage();

  static const _identityKey = 'rumi.device.identity.v1';
  static const _pairedKey = 'rumi.paired_device.v1';
  static const _pairedListKey = 'rumi.paired_devices.v1';
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
        final device = PairedDevice.fromJson(
          jsonDecode(raw) as Map<String, dynamic>,
        );
        if (device.isConfigured) return device;
      }
    } catch (_) {
      // ignore malformed paired device state
    }
    return null;
  }

  Future<void> savePairedDevice(PairedDevice? device) async {
    try {
      if (device == null) {
        await _storage.delete(_pairedKey);
      } else if (!device.isConfigured) {
        await _storage.delete(_pairedKey);
      } else {
        await _storage.write(_pairedKey, jsonEncode(device.toJson()));
        await addPairedDevice(device);
      }
    } catch (_) {
      // ignore secure storage failures
    }
  }

  Future<List<PairedDevice>> loadPairedDevices() async {
    try {
      final raw = await _storage.read(_pairedListKey);
      if (raw != null && raw.trim().isNotEmpty) {
        final list = jsonDecode(raw) as List;
        return list
            .map((e) => PairedDevice.fromJson(e as Map<String, dynamic>))
            .where((device) => device.isConfigured)
            .toList();
      }
    } catch (_) {
      // fall through
    }
    final devices = <PairedDevice>[];
    final single = await loadPairedDevice();
    if (single != null) {
      devices.add(single);
      await savePairedDevices(devices);
    }
    return devices;
  }

  Future<void> savePairedDevices(List<PairedDevice> devices) async {
    try {
      final configured = devices.where((device) => device.isConfigured);
      await _storage.write(
        _pairedListKey,
        jsonEncode(configured.map((d) => d.toJson()).toList()),
      );
    } catch (_) {
      // ignore
    }
  }

  Future<void> addPairedDevice(PairedDevice device) async {
    if (!device.isConfigured) return;
    final devices = await loadPairedDevices();
    devices.removeWhere((d) => d.deviceId == device.deviceId);
    devices.add(device);
    await savePairedDevices(devices);
  }

  Future<void> removePairedDevice(String deviceId) async {
    final devices = await loadPairedDevices();
    devices.removeWhere((d) => d.deviceId == deviceId);
    await savePairedDevices(devices);
    final single = await loadPairedDevice();
    if (single != null && single.deviceId == deviceId) {
      await _storage.delete(_pairedKey);
    }
  }

  Future<void> clear() async {
    try {
      await _storage.delete(_pairedKey);
      await _storage.delete(_pairedListKey);
      await _storage.delete(_legacyPcKey);
    } catch (_) {
      // ignore
    }
  }
}
