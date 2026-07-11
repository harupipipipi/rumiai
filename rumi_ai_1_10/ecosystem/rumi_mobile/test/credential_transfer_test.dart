import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'package:rumi_remote_app/src/data/pc/credential_transfer_client.dart';
import 'package:rumi_remote_app/src/settings/api_config_store.dart';

const _pc = PcConnection(baseUrl: 'http://192.0.2.10:8765', token: 'fake-token');

http.Response _ok(Map<String, dynamic> data) => http.Response(
      jsonEncode({'status': 'ok', 'data': data}),
      200,
      headers: {'content-type': 'application/json'},
    );

Map<String, dynamic> _pendingTransfer() => {
      'transfer_id': 'ctr_fake',
      'status': 'pending',
      'device_id': 'device-fake',
      'device_label': 'Test Phone',
      'profile_id': 'default',
      'provider_id': 'fake-provider',
      'provider_label': 'Fake Provider',
      'api_id': 'fake-account',
      'expires_at': DateTime.now().millisecondsSinceEpoch + 60000,
      'redemption_challenge': 'rch_fake',
    };

void main() {
  test('parses only public transfer metadata', () {
    final transfer = CredentialTransfer.fromJson(_pendingTransfer());
    expect(transfer.transferId, 'ctr_fake');
    expect(transfer.deviceId, 'device-fake');
    expect(transfer.providerId, 'fake-provider');
    expect(transfer.apiId, 'fake-account');
    expect(transfer.isPending, isTrue);
    expect(jsonEncode(transfer.redemptionPayload()), isNot(contains('api_key')));
  });

  test('lists pending transfers without putting secrets in URL or request body', () async {
    Uri? requestedUri;
    String? requestedBody;
    final client = MockClient((request) async {
      requestedUri = request.url;
      requestedBody = request.body;
      return _ok({'transfers': [_pendingTransfer()]});
    });
    final transferClient = CredentialTransferClient(client: client);
    final transfers = await transferClient.listPending(_pc);
    transferClient.close();

    expect(requestedUri!.path, '/api/mobile/v1/credential-transfers');
    expect(requestedUri!.query, isEmpty);
    expect(requestedBody, isEmpty);
    expect(transfers, hasLength(1));
    expect(transfers.single.providerLabel, 'Fake Provider');
  });

  test('reject sends only transfer state metadata', () async {
    http.Request? captured;
    final client = MockClient((request) async {
      captured = request;
      return _ok({'transfer': {..._pendingTransfer(), 'status': 'rejected'}});
    });
    final transferClient = CredentialTransferClient(client: client);
    await transferClient.reject(
      _pc,
      CredentialTransfer.fromJson(_pendingTransfer()),
    );
    transferClient.close();

    expect(captured!.url.path, '/api/mobile/v1/credential-transfers/ctr_fake/reject');
    expect(captured!.url.query, isEmpty);
    expect(jsonDecode(captured!.body), {'reason': 'rejected by recipient'});
    expect(captured!.body, isNot(contains('api_key')));
  });

  test('does not include server diagnostics in parse errors', () async {
    final client = MockClient((request) async => http.Response(
          '{"status":"ok","data":{"secret":"fake-secret"',
          200,
        ));
    final transferClient = CredentialTransferClient(client: client);
    await expectLater(
      transferClient.listPending(_pc),
      throwsA(
        isA<CredentialTransferException>().having(
          (error) => error.message,
          'message',
          isNot(contains('fake-secret')),
        ),
      ),
    );
    transferClient.close();
  });
}
