import 'dart:convert';

import 'package:http/http.dart' as http;

import 'credential_transfer.dart';
import 'pairing_payload.dart';

class PairedCredentialDevice {
  const PairedCredentialDevice({
    required this.deviceId,
    required this.baseUrl,
    required this.deviceToken,
  });
  final String deviceId;
  final String baseUrl;
  final String deviceToken;

  Map<String, Object> toJson() => {
        'device_id': deviceId,
        'base_url': baseUrl,
        'device_token': deviceToken,
        'scopes': const [credentialTransferScope],
      };
}

class PairedCredentialDeviceStore {
  PairedCredentialDeviceStore({SecretStorage? storage})
      : _storage = storage ?? FlutterSecretStorage();
  static const _key = 'rumi.mobile.credential_device.v1';
  final SecretStorage _storage;

  Future<void> saveVerified(PairedCredentialDevice device) async {
    final encoded = jsonEncode(device.toJson());
    await _storage.write(_key, encoded);
    if (await _storage.read(_key) != encoded) {
      await _storage.delete(_key);
      throw StateError('paired device persistence could not be verified');
    }
  }

  Future<PairedCredentialDevice?> load() async {
    final raw = await _storage.read(_key);
    if (raw == null || raw.isEmpty) return null;
    final decoded = jsonDecode(raw);
    if (decoded is! Map ||
        !(decoded['scopes'] as List? ?? const [])
            .contains(credentialTransferScope)) {
      throw StateError('stored paired device is invalid');
    }
    final device = PairedCredentialDevice(
      deviceId: decoded['device_id'] as String? ?? '',
      baseUrl: decoded['base_url'] as String? ?? '',
      deviceToken: decoded['device_token'] as String? ?? '',
    );
    if (device.deviceId.isEmpty ||
        device.deviceToken.isEmpty ||
        Uri.tryParse(device.baseUrl)?.host.isEmpty != false) {
      throw StateError('stored paired device is invalid');
    }
    return device;
  }
}

class CredentialPairingClient {
  CredentialPairingClient({
    required this.identityStore,
    required this.deviceStore,
    http.Client? client,
  }) : _client = client ?? http.Client();

  final MobileCredentialIdentityStore identityStore;
  final PairedCredentialDeviceStore deviceStore;
  final http.Client _client;

  Future<void> claim(MobilePairingPayload pairing) async {
    if (pairing.isExpired) throw StateError('pairing request is expired');
    final identity = await identityStore.loadOrCreate();
    await _request(
      pairing.baseUrl,
      '/api/mobile/v1/pairings/${Uri.encodeComponent(pairing.pairingId)}/claim',
      body: {
        'code': pairing.code,
        'device_id': identity.deviceId,
        'device_label': 'Rumi Mobile',
        'public_key': identity.signingPublicKey,
        'device_encryption_public_key': identity.encryptionPublicKey,
        'requested_capabilities': const [credentialTransferScope],
      },
    );
  }

  Future<bool> pickupApproved(MobilePairingPayload pairing) async {
    final identity = await identityStore.loadOrCreate();
    final data = await _request(
      pairing.baseUrl,
      '/api/mobile/v1/pairings/${Uri.encodeComponent(pairing.pairingId)}/token/pickup',
      body: {
        'pickup_secret': pairing.pickupSecret,
        'device_id': identity.deviceId,
      },
    );
    final envelope = data['token_delivery_envelope'];
    if (envelope is! Map) return false;
    final delivery = await identityStore.decryptPairingTokenEnvelope(
      Map<String, dynamic>.from(envelope),
      pairingId: pairing.pairingId,
      deviceId: identity.deviceId,
    );
    final scopes = (delivery['scopes'] as List? ?? const [])
        .map((value) => value.toString())
        .toSet();
    if (scopes.length != 1 || !scopes.contains(credentialTransferScope)) {
      throw StateError('pairing granted unexpected capabilities');
    }
    final token = delivery['device_token'] as String? ?? '';
    final deliveryId = envelope['delivery_id'] as String? ?? '';
    if (token.isEmpty || deliveryId.isEmpty) {
      throw StateError('pairing token delivery is incomplete');
    }
    await deviceStore.saveVerified(PairedCredentialDevice(
      deviceId: identity.deviceId,
      baseUrl: pairing.baseUrl,
      deviceToken: token,
    ));
    await _request(
      pairing.baseUrl,
      '/api/mobile/v1/pairings/${Uri.encodeComponent(pairing.pairingId)}/token/ack',
      body: {
        'pickup_secret': pairing.pickupSecret,
        'device_id': identity.deviceId,
        'delivery_id': deliveryId,
      },
    );
    delivery.clear();
    return true;
  }

  Future<Map<String, dynamic>> _request(
    String baseUrl,
    String path, {
    required Map<String, dynamic> body,
  }) async {
    final base = Uri.parse(baseUrl);
    final uri = base.replace(
      path:
          '${base.path.endsWith('/') ? base.path.substring(0, base.path.length - 1) : base.path}$path',
      query: null,
      fragment: null,
    );
    final response = await _client.post(
      uri,
      headers: const {
        'Accept': 'application/json',
        'Content-Type': 'application/json',
        'X-Rumi-Client': 'rumi-mobile',
      },
      body: jsonEncode(body),
    );
    if (response.statusCode < 200 || response.statusCode >= 300) {
      throw StateError('pairing request failed (${response.statusCode})');
    }
    final decoded = jsonDecode(response.body);
    if (decoded is! Map || decoded['status'] != 'ok') {
      throw StateError('pairing response is invalid');
    }
    final data = decoded['data'];
    return data is Map ? Map<String, dynamic>.from(data) : <String, dynamic>{};
  }

  void close() => _client.close();
}
