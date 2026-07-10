import 'dart:convert';
import 'dart:typed_data';

import 'package:cryptography/cryptography.dart';
import 'package:uuid/uuid.dart';

import '../../settings/api_config_store.dart';
import 'device_store.dart';

enum DeviceIdentityFailureCode {
  storageReadFailed,
  storageWriteFailed,
  storageVerificationFailed,
  corruptRecord,
  incompleteRecord,
  invalidKeyMaterial,
}

class DeviceIdentityStorageException implements Exception {
  const DeviceIdentityStorageException(this.code, this.message, [this.cause]);

  final DeviceIdentityFailureCode code;
  final String message;
  final Object? cause;

  @override
  String toString() => 'DeviceIdentityStorageException(${code.name}): $message';
}

/// A fail-closed identity store for approval signing and pairing decryption.
///
/// A new principal is generated only when the secure store authoritatively
/// reports that no record exists. Read, decode, validation, migration, write,
/// and read-back failures never fall through to identity creation and never
/// return ephemeral key material to callers.
class DurableMobileDeviceStore extends MobileDeviceStore {
  factory DurableMobileDeviceStore({
    SecureKeyValueStorage? storage,
    SecureKeyValueStorage? legacyStorage,
  }) {
    final resolvedStorage = storage ?? PlatformSecureStorage();
    final resolvedLegacyStorage = legacyStorage ??
        (storage == null ? LegacyFlutterSecureStorage() : null);
    return DurableMobileDeviceStore._(
      resolvedStorage,
      resolvedLegacyStorage,
    );
  }

  DurableMobileDeviceStore._(
    SecureKeyValueStorage storage,
    SecureKeyValueStorage? legacyStorage,
  )   : _identityStorage = storage,
        super(storage: storage, legacyStorage: legacyStorage);

  static const _identityKey = 'rumi.device.identity.v1';

  final SecureKeyValueStorage _identityStorage;
  final _uuid = const Uuid();

  DeviceIdentity? _pinnedIdentity;
  Future<DeviceIdentity>? _identityLoad;

  @override
  Future<DeviceIdentity> loadOrCreateIdentity() {
    final pinned = _pinnedIdentity;
    if (pinned != null) return Future<DeviceIdentity>.value(pinned);

    final inFlight = _identityLoad;
    if (inFlight != null) return inFlight;

    late final Future<DeviceIdentity> tracked;
    tracked = _loadOrCreateDurably().then((identity) {
      _pinnedIdentity = identity;
      return identity;
    }).whenComplete(() {
      if (identical(_identityLoad, tracked)) {
        _identityLoad = null;
      }
    });
    _identityLoad = tracked;
    return tracked;
  }

  Future<DeviceIdentity> _loadOrCreateDurably() async {
    final String? raw;
    try {
      raw = await _identityStorage.read(_identityKey);
    } catch (error) {
      throw DeviceIdentityStorageException(
        DeviceIdentityFailureCode.storageReadFailed,
        'The device identity could not be read. Unlock secure storage and retry.',
        error,
      );
    }

    if (raw == null) {
      final created = await _createIdentity();
      return _persistAndVerify(created);
    }
    if (raw.trim().isEmpty) {
      throw const DeviceIdentityStorageException(
        DeviceIdentityFailureCode.corruptRecord,
        'The stored device identity is empty and requires recovery.',
      );
    }

    final loaded = _parseAndValidateIdentity(
      raw,
      allowMissingEncryptionPair: true,
    );
    if (loaded.canDecryptTokenDelivery) return loaded;

    // Legacy signing-only records can be upgraded, but the upgraded identity is
    // not usable until the exact record is durably written and read back.
    final encryption = await _createEncryptionKeyPair();
    final upgraded = loaded.copyWith(
      encryptionPublicKey: encryption.publicKey,
      encryptionPrivateKey: encryption.privateKey,
    );
    return _persistAndVerify(upgraded);
  }

  Future<DeviceIdentity> _persistAndVerify(DeviceIdentity identity) async {
    final serialized = jsonEncode(identity.toJson());
    try {
      await _identityStorage.write(_identityKey, serialized);
    } catch (error) {
      throw DeviceIdentityStorageException(
        DeviceIdentityFailureCode.storageWriteFailed,
        'The device identity could not be saved. Signing and pairing remain blocked.',
        error,
      );
    }

    final String? stored;
    try {
      stored = await _identityStorage.read(_identityKey);
    } catch (error) {
      throw DeviceIdentityStorageException(
        DeviceIdentityFailureCode.storageVerificationFailed,
        'The saved device identity could not be verified.',
        error,
      );
    }
    if (stored == null || stored.trim().isEmpty) {
      throw const DeviceIdentityStorageException(
        DeviceIdentityFailureCode.storageVerificationFailed,
        'Secure storage did not return the saved device identity.',
      );
    }

    final DeviceIdentity verified;
    try {
      verified = _parseAndValidateIdentity(
        stored,
        allowMissingEncryptionPair: false,
      );
    } on DeviceIdentityStorageException catch (error) {
      throw DeviceIdentityStorageException(
        DeviceIdentityFailureCode.storageVerificationFailed,
        'The saved device identity failed integrity verification.',
        error,
      );
    }
    if (!_sameIdentity(identity, verified)) {
      throw const DeviceIdentityStorageException(
        DeviceIdentityFailureCode.storageVerificationFailed,
        'Secure storage returned a different device identity revision.',
      );
    }
    return verified;
  }

  DeviceIdentity _parseAndValidateIdentity(
    String raw, {
    required bool allowMissingEncryptionPair,
  }) {
    final dynamic decoded;
    try {
      decoded = jsonDecode(raw);
    } catch (error) {
      throw DeviceIdentityStorageException(
        DeviceIdentityFailureCode.corruptRecord,
        'The stored device identity is not valid JSON.',
        error,
      );
    }
    if (decoded is! Map) {
      throw const DeviceIdentityStorageException(
        DeviceIdentityFailureCode.corruptRecord,
        'The stored device identity has an invalid structure.',
      );
    }

    final DeviceIdentity identity;
    try {
      identity = DeviceIdentity.fromJson(
        Map<String, dynamic>.from(decoded),
      );
    } catch (error) {
      throw DeviceIdentityStorageException(
        DeviceIdentityFailureCode.corruptRecord,
        'The stored device identity cannot be decoded.',
        error,
      );
    }

    if (identity.deviceId.trim().isEmpty ||
        identity.deviceLabel.trim().isEmpty ||
        identity.keyType != 'ed25519' ||
        identity.publicKey.trim().isEmpty ||
        identity.privateKey.trim().isEmpty) {
      throw const DeviceIdentityStorageException(
        DeviceIdentityFailureCode.incompleteRecord,
        'The stored signing identity is incomplete.',
      );
    }

    _validatePrefixedKey(
      identity.publicKey,
      prefix: 'ed25519:',
      expectedLength: 32,
      label: 'signing public key',
    );
    _validateRawKey(
      identity.privateKey,
      expectedLength: 32,
      label: 'signing private key',
    );

    final encryptionPublic = identity.encryptionPublicKey.trim();
    final encryptionPrivate = identity.encryptionPrivateKey.trim();
    final bothMissing = encryptionPublic.isEmpty && encryptionPrivate.isEmpty;
    if (bothMissing) {
      if (allowMissingEncryptionPair) return identity;
      throw const DeviceIdentityStorageException(
        DeviceIdentityFailureCode.incompleteRecord,
        'The stored encryption identity is missing.',
      );
    }
    if (encryptionPublic.isEmpty || encryptionPrivate.isEmpty) {
      throw const DeviceIdentityStorageException(
        DeviceIdentityFailureCode.incompleteRecord,
        'The stored encryption identity is only partially present.',
      );
    }

    _validatePrefixedKey(
      encryptionPublic,
      prefix: 'x25519:',
      expectedLength: 32,
      label: 'encryption public key',
    );
    _validateRawKey(
      encryptionPrivate,
      expectedLength: 32,
      label: 'encryption private key',
    );
    return identity;
  }

  void _validatePrefixedKey(
    String value, {
    required String prefix,
    required int expectedLength,
    required String label,
  }) {
    final trimmed = value.trim();
    if (!trimmed.startsWith(prefix)) {
      throw DeviceIdentityStorageException(
        DeviceIdentityFailureCode.invalidKeyMaterial,
        'The stored $label has an unsupported format.',
      );
    }
    _validateRawKey(
      trimmed.substring(prefix.length),
      expectedLength: expectedLength,
      label: label,
    );
  }

  void _validateRawKey(
    String value, {
    required int expectedLength,
    required String label,
  }) {
    try {
      final decoded = _decodeBase64Url(value);
      if (decoded.length != expectedLength) {
        throw const FormatException('unexpected key length');
      }
    } catch (error) {
      throw DeviceIdentityStorageException(
        DeviceIdentityFailureCode.invalidKeyMaterial,
        'The stored $label is invalid.',
        error,
      );
    }
  }

  Future<DeviceIdentity> _createIdentity() async {
    final signingKeyPair = await Ed25519().newKeyPair();
    final signingKeyPairData = await signingKeyPair.extract();
    final signingPublicKey = await signingKeyPair.extractPublicKey();
    final encryption = await _createEncryptionKeyPair();
    return DeviceIdentity(
      deviceId: 'mobile-${_uuid.v4().substring(0, 12)}',
      deviceLabel: 'Rumi Mobile',
      publicKey: 'ed25519:${_encodeBase64Url(signingPublicKey.bytes)}',
      encryptionPublicKey: encryption.publicKey,
      encryptionPrivateKey: encryption.privateKey,
      privateKey: _encodeBase64Url(signingKeyPairData.bytes),
      keyType: 'ed25519',
    );
  }

  Future<_DurableEncryptionKeyPair> _createEncryptionKeyPair() async {
    final keyPair = await X25519().newKeyPair();
    final keyPairData = await keyPair.extract();
    final publicKey = await keyPair.extractPublicKey();
    return _DurableEncryptionKeyPair(
      publicKey: 'x25519:${_encodeBase64Url(publicKey.bytes)}',
      privateKey: _encodeBase64Url(keyPairData.bytes),
    );
  }

  bool _sameIdentity(DeviceIdentity left, DeviceIdentity right) {
    return left.deviceId == right.deviceId &&
        left.deviceLabel == right.deviceLabel &&
        left.publicKey == right.publicKey &&
        left.privateKey == right.privateKey &&
        left.encryptionPublicKey == right.encryptionPublicKey &&
        left.encryptionPrivateKey == right.encryptionPrivateKey &&
        left.keyType == right.keyType;
  }
}

class _DurableEncryptionKeyPair {
  const _DurableEncryptionKeyPair({
    required this.publicKey,
    required this.privateKey,
  });

  final String publicKey;
  final String privateKey;
}

String _encodeBase64Url(List<int> bytes) =>
    base64Url.encode(bytes).replaceAll('=', '');

Uint8List _decodeBase64Url(String value) {
  final text = value.trim();
  if (text.isEmpty) throw const FormatException('empty key');
  return base64Url.decode(
    text.padRight(text.length + ((4 - text.length % 4) % 4), '='),
  );
}
