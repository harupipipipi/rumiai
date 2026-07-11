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
