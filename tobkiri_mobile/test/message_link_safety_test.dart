import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:rumi_remote_app/src/chat/chat_link_policy.dart';
import 'package:rumi_remote_app/src/chat/chat_models.dart';
import 'package:rumi_remote_app/src/chat/message_view.dart';

Widget _app(MessageView view) {
  return MaterialApp(
    locale: const Locale('en'),
    supportedLocales: const [Locale('en'), Locale('ja')],
    localizationsDelegates: GlobalMaterialLocalizations.delegates,
    home: Scaffold(body: SingleChildScrollView(child: view)),
  );
}

MessageView _message(
  String content, {
  Future<bool> Function(Uri uri)? openLink,
}) {
  return MessageView(
    message: ChatMessage(
      id: content.hashCode.toString(),
      role: ChatRole.assistant,
      content: content,
    ),
    openLink: openLink,
  );
}

Future<void> _tapLink(WidgetTester tester, String target) async {
  await tester.tap(find.byKey(ValueKey('message-link:$target')));
  await tester.pumpAndSettle();
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  test('classifies external link targets fail closed', () {
    expect(
      ChatLinkReview.evaluate('https://example.com/path').disposition,
      ChatLinkDisposition.allowedWeb,
    );
    expect(
      ChatLinkReview.evaluate('http://example.com').disposition,
      ChatLinkDisposition.allowedWeb,
    );
    expect(
      ChatLinkReview.evaluate('file:///etc/passwd').disposition,
      ChatLinkDisposition.blockedScheme,
    );
    expect(
      ChatLinkReview.evaluate('javascript:alert(1)').disposition,
      ChatLinkDisposition.blockedScheme,
    );
    expect(
      ChatLinkReview.evaluate('myapp://open').disposition,
      ChatLinkDisposition.unsupportedScheme,
    );
    expect(
      ChatLinkReview.evaluate('https://trusted.example@evil.example')
          .disposition,
      ChatLinkDisposition.blockedCredentials,
    );
    expect(
      ChatLinkReview.evaluate('not a url').disposition,
      ChatLinkDisposition.malformed,
    );
    expect(
      ChatLinkReview.evaluate('https://example.com\nattack').disposition,
      ChatLinkDisposition.malformed,
    );
  });

  test('flags unicode and punycode hosts for identity review', () {
    final unicode = ChatLinkReview.evaluate('https://раypal.com/login');
    expect(unicode.needsIdentityWarning, isTrue);
    expect(unicode.host, 'раypal.com');
    expect(
      ChatLinkReview.evaluate('https://xn--pypal-4ve.com/login')
          .needsIdentityWarning,
      isTrue,
    );
  });

  testWidgets('HTTPS requires review and discloses host and full URL', (
    tester,
  ) async {
    Uri? opened;
    const target =
        'https://trusted.example/path?next=https%3A%2F%2Fevil.example';
    await tester.pumpWidget(
      _app(
        _message(
          '[Open report]($target)',
          openLink: (uri) async {
            opened = uri;
            return true;
          },
        ),
      ),
    );

    final action = find.byKey(const ValueKey('message-link:$target'));
    expect(tester.getSize(action), const Size(48, 48));
    expect(tester.getSemantics(action).label, contains('Destination: $target'));
    await _tapLink(tester, target);

    expect(opened, isNull);
    expect(find.text('trusted.example'), findsOneWidget);
    expect(find.text(target), findsOneWidget);
    expect(
      find.text('The visible text differs from the actual destination.'),
      findsOneWidget,
    );
    await tester.tap(find.byKey(const ValueKey('link-review-cancel')));
    await tester.pumpAndSettle();
    expect(opened, isNull);

    await _tapLink(tester, target);
    await tester.tap(find.byKey(const ValueKey('link-review-open')));
    await tester.pumpAndSettle();
    expect(opened, Uri.parse(target));
  });

  testWidgets('lookalike IDN is visibly warned before opening', (tester) async {
    const target = 'https://раypal.com/login';
    await tester.pumpWidget(_app(_message('[PayPal]($target)')));
    await _tapLink(tester, target);

    expect(
      find.byKey(const ValueKey('link-review-identity-warning')),
      findsOneWidget,
    );
    expect(find.text(target), findsOneWidget);
  });

  testWidgets('multiple Markdown destinations each expose one review action', (
    tester,
  ) async {
    const content = '[One](https://one.example) and [Two](https://two.example)';
    await tester.pumpWidget(
      _app(
        _message(content),
      ),
    );

    expect(
      find.byKey(const ValueKey('message-link:https://one.example')),
      findsOneWidget,
    );
    expect(
      find.byKey(const ValueKey('message-link:https://two.example')),
      findsOneWidget,
    );
    final semanticLabel = tester
        .getSemantics(
          find.byKey(ValueKey('message-semantics:${content.hashCode}')),
        )
        .label;
    expect(semanticLabel, contains('Content: One and Two'));
    expect(semanticLabel, isNot(contains(r'$1')));
  });

  testWidgets('balanced parentheses preserve the exact rendered destination', (
    tester,
  ) async {
    Uri? opened;
    const target = 'https://example.com/build_(final)';
    await tester.pumpWidget(
      _app(
        _message(
          '[Release]($target)',
          openLink: (uri) async {
            opened = uri;
            return true;
          },
        ),
      ),
    );

    await _tapLink(tester, target);
    expect(find.text(target), findsOneWidget);
    await tester.tap(find.byKey(const ValueKey('link-review-open')));
    await tester.pumpAndSettle();
    expect(opened, Uri.parse(target));
  });

  testWidgets('Copy link copies exact destination without launching', (
    tester,
  ) async {
    String? copied;
    var launches = 0;
    tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(
      SystemChannels.platform,
      (call) async {
        if (call.method == 'Clipboard.setData') {
          copied = (call.arguments as Map)['text'] as String?;
        }
        return null;
      },
    );
    addTearDown(
      () => tester.binding.defaultBinaryMessenger.setMockMethodCallHandler(
        SystemChannels.platform,
        null,
      ),
    );
    const target = 'https://example.com/copy';
    await tester.pumpWidget(
      _app(
        _message(
          '[Copy me]($target)',
          openLink: (_) async {
            launches += 1;
            return true;
          },
        ),
      ),
    );
    await _tapLink(tester, target);
    await tester.tap(find.byKey(const ValueKey('link-review-copy')));
    await tester.pumpAndSettle();

    expect(copied, target);
    expect(launches, 0);
    expect(find.text('Link copied'), findsOneWidget);
  });

  testWidgets('blocked unsupported malformed and deceptive links explain why', (
    tester,
  ) async {
    final cases = <String, String>{
      'file:///etc/passwd':
          'This link was blocked because its scheme is unsafe.',
      'myapp://open': 'This link scheme is not supported.',
      'not-a-url': 'This link is malformed and cannot be opened.',
      'https://trusted.example@evil.example':
          'This deceptive URL was blocked because it contains credentials.',
    };
    for (final entry in cases.entries) {
      final content = '[Target](${entry.key})';
      await tester.pumpWidget(_app(_message(content)));
      await _tapLink(tester, entry.key);
      expect(find.text(entry.value), findsOneWidget);
      expect(
        tester
            .getSemantics(
              find.byKey(
                ValueKey('message-link-status:${content.hashCode}'),
              ),
            )
            .label,
        entry.value,
      );
      expect(find.byKey(const ValueKey('link-review-open')), findsNothing);
    }
  });

  testWidgets('launcher false and exception produce in-place failure', (
    tester,
  ) async {
    const target = 'https://example.com/fail';
    for (final throws in [false, true]) {
      await tester.pumpWidget(
        _app(
          _message(
            '[Open]($target)',
            openLink: (_) async {
              if (throws) throw StateError('launcher unavailable');
              return false;
            },
          ),
        ),
      );
      await _tapLink(tester, target);
      await tester.tap(find.byKey(const ValueKey('link-review-open')));
      await tester.pumpAndSettle();
      expect(
        find.text('The link could not be opened in an external app.'),
        findsOneWidget,
      );
    }
  });

  testWidgets('external launch preserves the conversation scroll position', (
    tester,
  ) async {
    final controller = ScrollController();
    addTearDown(controller.dispose);
    const target = 'https://example.com/return';
    await tester.pumpWidget(
      MaterialApp(
        locale: const Locale('en'),
        supportedLocales: const [Locale('en'), Locale('ja')],
        localizationsDelegates: GlobalMaterialLocalizations.delegates,
        home: Scaffold(
          body: ListView(
            controller: controller,
            children: [
              const SizedBox(height: 500),
              _message('[Open]($target)', openLink: (_) async => true),
              const SizedBox(height: 500),
            ],
          ),
        ),
      ),
    );
    controller.jumpTo(420);
    await tester.pump();
    final before = controller.offset;

    await _tapLink(tester, target);
    await tester.tap(find.byKey(const ValueKey('link-review-open')));
    await tester.pumpAndSettle();

    expect(controller.offset, before);
  });
}
