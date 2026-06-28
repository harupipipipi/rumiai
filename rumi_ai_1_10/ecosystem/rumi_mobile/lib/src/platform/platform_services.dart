import 'package:flutter/services.dart';

class PlatformPreferences {
  PlatformPreferences({MethodChannel? channel})
      : _channel = channel ?? const MethodChannel('ai.rumi.remote/preferences');

  final MethodChannel _channel;

  Future<String?> read(String key) {
    return _channel.invokeMethod<String>('read', {'key': key});
  }

  Future<void> write(String key, String value) async {
    await _channel.invokeMethod<void>('write', {'key': key, 'value': value});
  }

  Future<void> delete(String key) async {
    await _channel.invokeMethod<void>('delete', {'key': key});
  }
}

class PlatformUrlLauncher {
  const PlatformUrlLauncher();

  static const _channel = MethodChannel('ai.rumi.remote/url_launcher');

  Future<bool> open(Uri uri) async {
    final ok =
        await _channel.invokeMethod<bool>('open', {'url': uri.toString()});
    return ok ?? false;
  }
}

class PlatformClipboard {
  const PlatformClipboard();

  Future<String?> readText() async {
    final data = await Clipboard.getData(Clipboard.kTextPlain);
    return data?.text;
  }

  Future<void> writeText(String text) {
    return Clipboard.setData(ClipboardData(text: text));
  }
}

class PlatformPickedMediaFile {
  const PlatformPickedMediaFile({
    required this.name,
    required this.mimeType,
    required this.size,
    required this.base64Data,
  });

  final String name;
  final String mimeType;
  final int size;
  final String base64Data;
}

class PlatformMediaPicker {
  const PlatformMediaPicker();

  static const _channel = MethodChannel('ai.rumi.remote/media_picker');

  Future<PlatformPickedMediaFile?> pick({
    required String kind,
    required int maxBytes,
  }) async {
    final raw = await _channel.invokeMapMethod<String, dynamic>('pick', {
      'kind': kind,
      'max_bytes': maxBytes,
    });
    if (raw == null) return null;
    final errorCode = '${raw['error_code'] ?? ''}'.trim();
    if (errorCode.isNotEmpty) {
      throw PlatformException(
        code: errorCode,
        message: '${raw['message'] ?? 'Media picker failed'}',
      );
    }
    return PlatformPickedMediaFile(
      name: '${raw['name'] ?? 'selected-file'}',
      mimeType: '${raw['mime_type'] ?? 'application/octet-stream'}',
      size: raw['size'] is num ? (raw['size'] as num).toInt() : 0,
      base64Data: '${raw['base64'] ?? ''}',
    );
  }
}

class PlatformNotifications {
  const PlatformNotifications();

  static const _channel = MethodChannel('ai.rumi.remote/notifications');

  Future<bool> requestAuthorization() async {
    try {
      final ok = await _channel.invokeMethod<bool>('requestAuthorization');
      return ok ?? false;
    } catch (_) {
      return false;
    }
  }

  Future<bool> showPcTaskFinished({
    required String title,
    required String body,
  }) async {
    try {
      final ok = await _channel.invokeMethod<bool>('showPcTaskFinished', {
        'title': title,
        'body': body,
      });
      return ok ?? false;
    } catch (_) {
      return false;
    }
  }
}
