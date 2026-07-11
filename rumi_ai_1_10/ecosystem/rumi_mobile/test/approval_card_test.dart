import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:rumi_remote_app/src/domain/chat_event.dart';
import 'package:rumi_remote_app/src/domain/conversation_locator.dart';
import 'package:rumi_remote_app/src/features/tools/approval_card.dart';

void main() {
  test('uses enforcement fields and recursively redacts secrets', () {
    final event = _event({
      'capability': 'credential',
      'target': 'vault://account',
      'token': 'secret',
      'nested': {'api_key': 'secret'}
    });
    expect(event.field('target'), 'vault://account');
    expect('${event.enforcementMetadata}', isNot(contains('secret')));
    expect(event.isHighImpact, isTrue);
  });

  testWidgets('renders the structured contract and single-submits approval',
      (tester) async {
    var calls = 0;
    await tester.pumpWidget(MaterialApp(
        home: Scaffold(
            body: ApprovalCard(
      event: _event({
        'capability': 'read',
        'consequence': 'Read a file',
        'target': '/safe/file',
        'affected_data': 'document',
        'reason': 'answer',
        'risk_explanation': 'exposure',
        'scope': 'once',
        'persistence': 'none',
        'requester': 'profile',
        'expires_at': '2099-01-01',
        'audit_text': 'recorded'
      }),
      onApprove: () async {
        calls++;
        await Future<void>.delayed(const Duration(seconds: 1));
      },
      onDeny: (_) {},
    ))));
    expect(find.text('対象: /safe/file'), findsOneWidget);
    expect(find.text('リスク: exposure'), findsOneWidget);
    await tester.tap(find.text('許可'));
    await tester.tap(find.text('許可'));
    expect(calls, 1);
    await tester.pump(const Duration(seconds: 1));
  });

  testWidgets('high impact approval requires confirmation', (tester) async {
    var approved = false;
    await tester.pumpWidget(MaterialApp(
        home: Scaffold(
            body: ApprovalCard(
      event: _event({
        'capability': 'shell',
        'consequence': 'Run command',
        'target': 'rm-safe-temp'
      }),
      onApprove: () => approved = true,
      onDeny: (_) {},
    ))));
    await tester.tap(find.text('許可'));
    await tester.pumpAndSettle();
    expect(find.text('影響の大きい操作を確認'), findsOneWidget);
    expect(approved, isFalse);
    await tester.tap(find.text('確認して許可'));
    await tester.pumpAndSettle();
    expect(approved, isTrue);
  });
}

ApprovalEvent _event(Map<String, dynamic> metadata) => ApprovalEvent(
      locator: ConversationLocator.local('test'),
      runId: 'run',
      approvalId: 'approval',
      toolName: 'tool',
      prompt: 'untrusted prompt',
      enforcementMetadata: metadata,
    );
