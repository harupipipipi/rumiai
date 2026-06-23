import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:rumi_remote_app/src/app_theme.dart';
import 'package:rumi_remote_app/src/chat/chat_drawer.dart';
import 'package:rumi_remote_app/src/chat/chat_models.dart';
import 'package:rumi_remote_app/src/chat/chat_screen.dart';
import 'package:rumi_remote_app/src/chat/chat_store.dart';
import 'package:rumi_remote_app/src/chat/composer_bar.dart';
import 'package:rumi_remote_app/src/chat/message_view.dart';
import 'package:rumi_remote_app/src/data/pc/device_store.dart';
import 'package:rumi_remote_app/src/domain/space.dart';
import 'package:rumi_remote_app/src/settings/api_config_store.dart';

class _FakeSecureStorage implements SecureKeyValueStorage {
  final Map<String, String> _values = {};

  @override
  Future<String?> read(String key) async => _values[key];

  @override
  Future<void> write(String key, String? value) async {
    if (value == null) {
      _values.remove(key);
    } else {
      _values[key] = value;
    }
  }

  @override
  Future<void> delete(String key) async {
    _values.remove(key);
  }
}

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
  });

  Widget wrap(Widget child) => MaterialApp(
        theme: buildRumiTheme(dark: true),
        home: child,
      );

  testWidgets('chat screen renders empty state with suggestions and composer',
      (tester) async {
    await tester.binding.setSurfaceSize(const Size(393, 852));
    final store = ChatStore();
    final fakeStorage = _FakeSecureStorage();
    final configStore = ApiConfigStore(storage: fakeStorage);
    final deviceStore = MobileDeviceStore(storage: fakeStorage);
    await tester.pumpWidget(wrap(ChatScreen(
      store: store,
      configStore: configStore,
      deviceStore: deviceStore,
    )));
    await tester
        .runAsync(() => Future<void>.delayed(const Duration(milliseconds: 30)));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 30));

    expect(find.text('Rumiへようこそ'), findsOneWidget);
    expect(find.byType(ActionChip), findsNWidgets(4));
    expect(find.byType(ComposerBar), findsOneWidget);
    expect(find.byIcon(Icons.add_comment_outlined), findsOneWidget);
    expect(find.byIcon(Icons.settings_outlined), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('chat drawer shows new chat button and sections', (tester) async {
    await tester.binding.setSurfaceSize(const Size(393, 852));
    final store = ChatStore();
    await store.load();
    final convo = await store.createAndPersist();
    await store.addMessage(
      convo.id,
      ChatMessage(
        id: 'm1',
        role: ChatRole.user,
        content: 'こんにちは',
        createdAt: DateTime.now(),
      ),
    );

    await tester.pumpWidget(wrap(Scaffold(
      body: ChatDrawer(
        spaces: const [Space.local],
        activeSpaceId: Space.local.id,
        conversations: store.conversations,
        activeId: store.active?.id,
        onNewChat: () {},
        onSelectSpace: (_) {},
        onSelect: (_) {},
        onDelete: (_) {},
        onRename: (_) {},
        onPin: (_) {},
        onReconnectSpace: () {},
        onContinueOffline: () {},
        onOpenSettings: () {},
      ),
    )));
    await tester.pumpAndSettle();

    expect(find.text('Rumi'), findsOneWidget);
    expect(find.text('新規チャット'), findsWidgets);
    expect(find.text('チャット'), findsOneWidget);
    expect(find.textContaining('こんにちは'), findsNWidgets(2));
    expect(tester.takeException(), isNull);
  });

  testWidgets('user and assistant messages render without overflow',
      (tester) async {
    await tester.binding.setSurfaceSize(const Size(393, 852));
    final longText = List<String>.generate(60, (i) => 'メッセージ$i').join(' ');
    await tester.pumpWidget(wrap(Scaffold(
      body: ListView(
        children: [
          MessageView(
            message: ChatMessage(
              id: 'u',
              role: ChatRole.user,
              content: longText,
              createdAt: DateTime.now(),
            ),
          ),
          MessageView(
            message: ChatMessage(
              id: 'a',
              role: ChatRole.assistant,
              content: '# 見出し\n\n本文です。\n\n```dart\nvoid main() {}\n```',
              createdAt: DateTime.now(),
            ),
          ),
        ],
      ),
    )));
    await tester.pumpAndSettle();

    expect(find.textContaining('メッセージ0'), findsOneWidget);
    expect(find.text('見出し'), findsOneWidget);
    expect(find.text('void main() {}'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('pending assistant message shows typing indicator',
      (tester) async {
    await tester.binding.setSurfaceSize(const Size(393, 852));
    await tester.pumpWidget(wrap(Scaffold(
      body: MessageView(
        message: ChatMessage(
          id: 'p',
          role: ChatRole.assistant,
          content: '',
          createdAt: DateTime.now(),
          pending: true,
        ),
      ),
    )));
    await tester.pump();
    expect(find.byIcon(Icons.auto_awesome), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('composer bar enables send only with text', (tester) async {
    await tester.binding.setSurfaceSize(const Size(393, 852));
    var sent = '';
    await tester.pumpWidget(wrap(Scaffold(
      body: ComposerBar(
        onSend: (t) => sent = t,
        onStop: () {},
        busy: false,
      ),
    )));
    await tester.pumpAndSettle();

    final sendIcon = find.byIcon(Icons.arrow_upward_rounded);
    final sendBtn =
        find.ancestor(of: sendIcon, matching: find.bySubtype<IconButton>());
    final textField = find.byType(TextField);

    expect(tester.widget<IconButton>(sendBtn).onPressed, isNull);

    await tester.enterText(textField, 'テスト入力');
    await tester.pump();
    expect(tester.widget<IconButton>(sendBtn).onPressed, isNotNull);

    await tester.tap(sendBtn);
    await tester.pump();
    expect(sent, 'テスト入力');
    expect(tester.takeException(), isNull);
  });

  testWidgets('composer shows stop button when busy', (tester) async {
    await tester.binding.setSurfaceSize(const Size(393, 852));
    var stopped = false;
    await tester.pumpWidget(wrap(Scaffold(
      body: ComposerBar(
        onSend: (_) {},
        onStop: () => stopped = true,
        busy: true,
      ),
    )));
    await tester.pumpAndSettle();

    final stop = find.byIcon(Icons.stop_rounded);
    expect(stop, findsOneWidget);
    await tester.tap(stop);
    await tester.pump();
    expect(stopped, isTrue);
    expect(tester.takeException(), isNull);
  });
}
