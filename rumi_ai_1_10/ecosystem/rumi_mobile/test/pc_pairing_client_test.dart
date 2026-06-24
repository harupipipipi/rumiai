import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:rumi_remote_app/src/data/pc/device_store.dart';
import 'package:rumi_remote_app/src/data/pc/pc_pairing_client.dart';
import 'package:rumi_remote_app/src/settings/api_config_store.dart';

const _pc = PcConnection(baseUrl: 'http://192.168.1.10:8765', token: 'tok');

http.Response _ok(Map<String, dynamic> data) {
  return http.Response(jsonEncode({'status': 'ok', 'data': data}), 200,
      headers: {'content-type': 'application/json'});
}

const _identity = DeviceIdentity(
  deviceId: 'mobile-abc123',
  deviceLabel: 'Rumi Mobile',
  publicKey: 'pk-test',
);

void main() {
  group('friendlyPcLabel', () {
    test('does not display raw http URL labels', () {
      expect(
        friendlyPcLabel(
            'http://192.168.11.25:8765', 'http://192.168.11.25:8765'),
        'PC',
      );
      expect(
        friendlyPcLabel('', 'http://haru-macbook.local:8765'),
        'haru-macbook',
      );
      expect(
        friendlyPcLabel('Haru MacBook', 'http://192.168.11.25:8765'),
        'Haru MacBook',
      );
    });
  });

  group('PairingClaimResponse', () {
    test('parses from json', () {
      final resp = PairingClaimResponse.fromJson({
        'pairing': {'pairing_id': 'p1', 'status': 'pending'},
      });
      expect(resp.pairingId, 'p1');
      expect(resp.status, 'pending');
    });
  });

  group('PairingStatusResponse', () {
    test('isAccepted when status is accepted', () {
      final resp = PairingStatusResponse.fromJson({
        'pairing': {
          'pairing_id': 'p1',
          'status': 'accepted',
          'device_token': 'dt-xxx',
          'scopes': ['chat.read', 'chat.write'],
          'pc_label': 'MacBook',
        },
      });
      expect(resp.isAccepted, isTrue);
      expect(resp.isReady, isTrue);
      expect(resp.deviceToken, 'dt-xxx');
      expect(resp.scopes, ['chat.read', 'chat.write']);
      expect(resp.pcLabel, 'MacBook');
    });

    test('isAccepted false for pending', () {
      final resp = PairingStatusResponse.fromJson({
        'pairing': {'pairing_id': 'p1', 'status': 'pending'},
      });
      expect(resp.isAccepted, isFalse);
      expect(resp.isReady, isFalse);
      expect(resp.deviceToken, isNull);
    });

    test('accepted status is not ready without a device token', () {
      final resp = PairingStatusResponse.fromJson({
        'pairing': {'pairing_id': 'p1', 'status': 'approved'},
      });

      expect(resp.isAccepted, isTrue);
      expect(resp.hasDeviceToken, isFalse);
      expect(resp.isReady, isFalse);
    });

    test('parses top-level pc label and token from status response', () {
      final resp = PairingStatusResponse.fromJson({
        'pairing': {'pairing_id': 'p1', 'status': 'approved'},
        'device_token': 'dtk-123',
        'scopes': ['chat.read'],
        'pc_label': 'Haru MacBook',
      });

      expect(resp.isAccepted, isTrue);
      expect(resp.isReady, isTrue);
      expect(resp.deviceToken, 'dtk-123');
      expect(resp.pcLabel, 'Haru MacBook');
      expect(resp.scopes, ['chat.read']);
    });
  });

  group('PcPairingClient', () {
    test('claim sends POST to /api/mobile/v1/pairings/{id}/claim', () async {
      String? authHeader;
      String? requestBody;
      final client = MockClient((request) async {
        authHeader = request.headers['Authorization'];
        requestBody = request.body;
        return _ok({
          'pairing': {'pairing_id': 'p1', 'status': 'pending'},
        });
      });

      final pairingClient = PcPairingClient(client: client);
      final resp = await pairingClient.claim(
        _pc,
        pairingId: 'p1',
        code: 'abc123',
        device: _identity,
        requestedCapabilities: const ['chat.read', 'chat.write'],
      );
      pairingClient.close();

      expect(authHeader, 'Bearer tok');
      expect(resp.pairingId, 'p1');
      expect(resp.status, 'pending');

      final body = jsonDecode(requestBody!) as Map<String, dynamic>;
      expect(body['code'], 'abc123');
      expect(body['device_id'], 'mobile-abc123');
      expect(body['requested_capabilities'], ['chat.read', 'chat.write']);
    });

    test('pollStatus sends GET to /api/mobile/v1/pairings/{id}/status',
        () async {
      String? requestedPath;
      final client = MockClient((request) async {
        requestedPath = request.url.path;
        return _ok({
          'pairing': {
            'pairing_id': 'p1',
            'status': 'accepted',
            'device_token': 'dt-123',
            'scopes': ['chat.read'],
          },
        });
      });

      final pairingClient = PcPairingClient(client: client);
      final resp = await pairingClient.pollStatus(_pc, pairingId: 'p1');
      pairingClient.close();

      expect(requestedPath, '/api/mobile/v1/pairings/p1/status');
      expect(resp.isAccepted, isTrue);
      expect(resp.deviceToken, 'dt-123');
    });

    test('throws PcPairingException on non-ok response', () async {
      final client = MockClient((request) async {
        return http.Response(
            jsonEncode({
              'status': 'error',
              'error': {'message': 'not found'}
            }),
            404);
      });

      final pairingClient = PcPairingClient(client: client);
      expect(
        () => pairingClient.pollStatus(_pc, pairingId: 'p1'),
        throwsA(isA<PcPairingException>()),
      );
      pairingClient.close();
    });

    test('throws when pc not configured', () async {
      final client = MockClient((request) async => _ok({}));
      final pairingClient = PcPairingClient(client: client);
      expect(
        () => pairingClient.claim(
          const PcConnection(baseUrl: '', token: ''),
          pairingId: 'p1',
          code: 'abc',
          device: _identity,
          requestedCapabilities: const [],
        ),
        throwsA(isA<PcPairingException>()),
      );
      pairingClient.close();
    });
  });
}
