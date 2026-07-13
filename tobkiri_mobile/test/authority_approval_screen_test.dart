import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:rumi_remote_app/src/authority_approval_screen.dart';
import 'package:rumi_remote_app/src/mobile_authority.dart';

class _MemorySecrets implements AuthoritySecretStore {
  final values = <String, String>{};

  @override
  Future<void> delete(String key) async => values.remove(key);

  @override
  Future<String?> read(String key) async => values[key];

  @override
  Future<void> write(String key, String value) async => values[key] = value;
}

MobileAuthorityConnection _connection() => MobileAuthorityConnection(
      baseUrl: 'https://pc.example.test',
      deviceId: 'device-1',
      approvalToken: 'approval-token',
      approvalScopes: mobileAuthorityScopes,
    );

Map<String, Object?> _request({String risk = 'high'}) => {
      'request_id': 'req-1',
      'status': 'pending',
      'principal_id': 'agent-1',
      'permission_id': 'terminal.execute',
      'reason': 'Run a reviewed command',
      'risk_level': risk,
      'resource': {
        'command': 'pwd',
        'approval_token': 'must-not-render',
      },
    };

http.Response _ok(Map<String, Object?> data) => http.Response(
      jsonEncode({'success': true, 'data': data}),
      200,
      headers: {'content-type': 'application/json'},
    );

Future<MobileAuthorityConnectionStore> _pairedStore() async {
  final store = MobileAuthorityConnectionStore(storage: _MemorySecrets());
  await store.saveVerified(_connection());
  return store;
}

Future<void> _pump(
  WidgetTester tester, {
  required MobileAuthorityConnectionStore store,
  MockClient? httpClient,
}) async {
  await tester.pumpWidget(
    MaterialApp(
      home: AuthorityApprovalScreen(
        connectionStore: store,
        clientFactory: (connection) => MobileAuthorityClient(
          connection: connection,
          signer: _TestSigner(),
          client: httpClient ?? MockClient((request) async => _ok({})),
        ),
      ),
    ),
  );
  await tester.pumpAndSettle();
}

class _TestSigner implements AuthorityPayloadSigner {
  @override
  Future<String> signPayloadHash(String payloadHash) async => 'signature';
}

void main() {
  testWidgets('fails closed when no paired approval connection exists',
      (tester) async {
    final store = MobileAuthorityConnectionStore(storage: _MemorySecrets());
    await _pump(tester, store: store);

    expect(find.text('Authority approvals'), findsOneWidget);
    expect(find.textContaining('Pair this device'), findsOneWidget);
    expect(find.text('Approve once'), findsNothing);
    expect(find.byType(TextField), findsNothing);
  });

  testWidgets('renders bounded pending card without secret-like resources',
      (tester) async {
    await _pump(
      tester,
      store: await _pairedStore(),
      httpClient: MockClient((request) async => _ok({
            'requests': [_request()],
          })),
    );

    expect(find.text('terminal.execute'), findsOneWidget);
    expect(find.text('Run a reviewed command'), findsOneWidget);
    expect(find.textContaining('command: pwd'), findsOneWidget);
    expect(find.textContaining('must-not-render'), findsNothing);
    expect(find.text('Approve once'), findsOneWidget);
    expect(find.text('Deny'), findsOneWidget);
  });

  testWidgets('high-impact approve requires confirmation and submits once',
      (tester) async {
    var settleCalls = 0;
    final hash = 'ab' * 32;
    final client = MockClient((request) async {
      if (request.method == 'GET' &&
          request.url.path == '/api/authority/requests') {
        return _ok({
          'requests': [_request()],
        });
      }
      if (request.method == 'GET') return _ok(_request());
      if (request.url.path.endsWith('/challenge')) {
        return _ok({
          'payload_hash': hash,
          'challenge': {'challenge_id': 'challenge-1'},
        });
      }
      settleCalls++;
      return _ok({'status': 'approved'});
    });
    await _pump(tester, store: await _pairedStore(), httpClient: client);

    await tester.tap(find.text('Approve once'));
    await tester.pumpAndSettle();
    expect(find.text('Confirm high-impact action'), findsOneWidget);
    expect(settleCalls, 0);

    await tester.tap(find.text('Confirm and approve'));
    await tester.pumpAndSettle();
    expect(settleCalls, 1);
    expect(find.text('terminal.execute'), findsNothing);
  });

  testWidgets('deny can cancel, then explicitly confirm', (tester) async {
    var denyCalls = 0;
    final hash = 'cd' * 32;
    final client = MockClient((request) async {
      if (request.method == 'GET' &&
          request.url.path == '/api/authority/requests') {
        return _ok({
          'requests': [_request(risk: 'low')],
        });
      }
      if (request.method == 'GET') return _ok(_request(risk: 'low'));
      if (request.url.path.endsWith('/challenge')) {
        return _ok({
          'payload_hash': hash,
          'challenge': {'challenge_id': 'challenge-1'},
        });
      }
      denyCalls++;
      return _ok({'status': 'denied'});
    });
    await _pump(tester, store: await _pairedStore(), httpClient: client);

    await tester.tap(find.text('Deny'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Cancel'));
    await tester.pumpAndSettle();
    expect(denyCalls, 0);

    await tester.tap(find.text('Deny'));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField), 'Unexpected request');
    await tester.tap(find.widgetWithText(FilledButton, 'Deny'));
    await tester.pumpAndSettle();
    expect(denyCalls, 1);
  });

  testWidgets('375px layout has no overflow', (tester) async {
    await tester.binding.setSurfaceSize(const Size(375, 667));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    await _pump(
      tester,
      store: await _pairedStore(),
      httpClient: MockClient((request) async => _ok({
            'requests': [_request()],
          })),
    );

    expect(tester.takeException(), isNull);
    expect(find.text('Approve once'), findsOneWidget);
  });
}
