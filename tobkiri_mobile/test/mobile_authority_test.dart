import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:rumi_remote_app/src/mobile_authority.dart';

class _MemorySecrets implements AuthoritySecretStore {
  final values = <String, String>{};
  bool corruptWrites = false;

  @override
  Future<void> delete(String key) async => values.remove(key);

  @override
  Future<String?> read(String key) async => values[key];

  @override
  Future<void> write(String key, String value) async {
    values[key] = corruptWrites ? 'corrupt' : value;
  }
}

class _Signer implements AuthorityPayloadSigner {
  String? payloadHash;

  @override
  Future<String> signPayloadHash(String payloadHash) async {
    this.payloadHash = payloadHash;
    return 'device-signature';
  }
}

MobileAuthorityConnection _connection({Set<String>? scopes}) =>
    MobileAuthorityConnection(
      baseUrl: 'https://pc.example.test/root',
      deviceId: 'device-1',
      approvalToken: 'approval-token',
      approvalScopes: scopes ?? mobileAuthorityScopes,
    );

AuthorityRequestItem _pending({String expiresAt = ''}) => AuthorityRequestItem(
      requestId: 'req-1',
      status: 'pending',
      principalId: 'agent-1',
      permissionId: 'terminal.execute',
      reason: 'Run reviewed command',
      riskLevel: 'high',
      resource: const {'command': 'pwd'},
      expiresAt: expiresAt,
    );

http.Response _ok(Map<String, Object?> data) => http.Response(
      jsonEncode({'success': true, 'data': data}),
      200,
      headers: {'content-type': 'application/json'},
    );

void main() {
  test('connection storage is read-back verified and exact-scope only',
      () async {
    final secrets = _MemorySecrets();
    final store = MobileAuthorityConnectionStore(storage: secrets);
    await store.saveVerified(_connection());
    expect((await store.load())!.approvalToken, 'approval-token');

    expect(
      _connection(scopes: {'authority.request.list'}).isValid,
      isFalse,
    );
    expect(
      _connection(scopes: {...mobileAuthorityScopes, 'chat.read'}).isValid,
      isFalse,
    );
    expect(
      MobileAuthorityConnection(
        baseUrl: 'https://pc.example.test',
        deviceId: 'device-1',
        approvalToken: 'normal-session-token',
        approvalScopes: const {'chat.read'},
      ).isValid,
      isFalse,
    );

    secrets.corruptWrites = true;
    await expectLater(
      store.saveVerified(_connection()),
      throwsA(isA<StateError>()),
    );
    expect(secrets.values, isEmpty);
  });

  test('list uses only approval token and filters non-pending records',
      () async {
    late http.Request captured;
    final client = MobileAuthorityClient(
      connection: _connection(),
      signer: _Signer(),
      client: MockClient((request) async {
        captured = request;
        return _ok({
          'requests': [
            {
              'request_id': 'req-1',
              'status': 'pending',
              'permission_id': 'terminal.execute',
            },
            {'request_id': 'req-2', 'status': 'approved'},
          ],
        });
      }),
    );

    final result = await client.listPending();
    expect(result.map((item) => item.requestId), ['req-1']);
    expect(captured.url.path, '/root/api/authority/requests');
    expect(captured.url.queryParameters, {'status': 'pending'});
    expect(captured.headers['Authorization'], 'Bearer approval-token');
  });

  for (final decision in ['approve', 'deny']) {
    test('$decision refreshes, signs challenge, and submits once', () async {
      final requests = <http.Request>[];
      final signer = _Signer();
      final hash = 'ab' * 32;
      final client = MobileAuthorityClient(
        connection: _connection(),
        signer: signer,
        client: MockClient((request) async {
          requests.add(request);
          if (request.method == 'GET') {
            return _ok({
              'request_id': 'req-1',
              'status': 'pending',
              'permission_id': 'terminal.execute',
            });
          }
          if (request.url.path.endsWith('/challenge')) {
            return _ok({
              'payload_hash': hash,
              'challenge': {'challenge_id': 'challenge-1'},
            });
          }
          return _ok({'status': decision == 'approve' ? 'approved' : 'denied'});
        }),
      );

      if (decision == 'approve') {
        await client.approve(_pending());
      } else {
        await client.deny(_pending(), reason: 'Not expected');
      }

      expect(requests, hasLength(3));
      expect(signer.payloadHash, hash);
      final challengeBody =
          jsonDecode(requests[1].body) as Map<String, dynamic>;
      expect(challengeBody, {'decision': decision, 'scope': 'once'});
      final settleBody = jsonDecode(requests[2].body) as Map<String, dynamic>;
      expect(settleBody['approved'], isNull);
      if (decision == 'approve') expect(settleBody['scope'], 'once');
      expect(settleBody['attestation'], {
        'challenge_id': 'challenge-1',
        'payload_hash': hash,
        'signature': 'device-signature',
        'signature_algorithm': 'ed25519',
      });
    });
  }

  test('rejects non-pending and expired requests before network use', () async {
    var calls = 0;
    final client = MobileAuthorityClient(
      connection: _connection(),
      signer: _Signer(),
      client: MockClient((request) async {
        calls++;
        return _ok({});
      }),
    );
    final denied = AuthorityRequestItem(
      requestId: 'req-1',
      status: 'denied',
      principalId: '',
      permissionId: '',
      reason: '',
      riskLevel: 'low',
      resource: const {},
    );
    await expectLater(client.approve(denied), throwsA(isA<StateError>()));
    await expectLater(
      client.approve(_pending(expiresAt: '2000-01-01T00:00:00Z')),
      throwsA(isA<StateError>()),
    );
    expect(calls, 0);
  });

  test('server error does not expose response body or token', () async {
    final client = MobileAuthorityClient(
      connection: _connection(),
      signer: _Signer(),
      client: MockClient((request) async => http.Response(
            jsonEncode({'error': 'secret-body-value'}),
            403,
          )),
    );
    await expectLater(
      client.listPending(),
      throwsA(
        isA<StateError>()
            .having((error) => error.toString(), 'message', contains('(403)'))
            .having(
              (error) => error.toString(),
              'redacted body',
              isNot(contains('secret-body-value')),
            )
            .having(
              (error) => error.toString(),
              'redacted token',
              isNot(contains('approval-token')),
            ),
      ),
    );
  });
}
