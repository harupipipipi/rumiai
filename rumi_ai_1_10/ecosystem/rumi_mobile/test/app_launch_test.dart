import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:rumi_remote_app/src/app_theme.dart' as theme;
import 'package:rumi_remote_app/src/chat/chat_screen.dart';
import 'package:rumi_remote_app/src/chat/chat_store.dart';
import 'package:rumi_remote_app/src/chat/composer_bar.dart';
import 'package:rumi_remote_app/src/data/pc/device_store.dart';
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
  Future<void> delete(String key) async => _values.remove(key);
}

class _FakeChatStorage implements ChatKeyValueStorage {
  final Map<String, String> _values = {};

  @override
  Future<String?> read(String key) async => _values[key];

  @override
  Future<void> write(String key, String value) async {
    _values[key] = value;
  }

  @override
  Future<void> delete(String key) async {
    _values.remove(key);
  }
}

ChatStore _testStore() => ChatStore(storage: _FakeChatStorage());

void main() {
  testWidgets('app launches and shows chat empty state', (tester) async {
    final storage = _FakeSecureStorage();
    final store = _testStore();
    final configStore = ApiConfigStore(storage: storage);
    final deviceStore = MobileDeviceStore(storage: storage);

    await tester.pumpWidget(MaterialApp(
      theme: theme.buildRumiTheme(),
      home: ChatScreen(
        store: store,
        configStore: configStore,
        deviceStore: deviceStore,
      ),
    ));
    await tester.pumpAndSettle(const Duration(seconds: 3));

    expect(find.text('ようこそ'), findsOneWidget);
    expect(find.text('Rumiへようこそ'), findsNothing);
    expect(find.byType(ComposerBar), findsOneWidget);
  });

  testWidgets('settings screen opens and shows sections', (tester) async {
    final storage = _FakeSecureStorage();
    final store = _testStore();
    final configStore = ApiConfigStore(storage: storage);
    final deviceStore = MobileDeviceStore(storage: storage);

    await tester.pumpWidget(MaterialApp(
      theme: theme.buildRumiTheme(),
      home: ChatScreen(
        store: store,
        configStore: configStore,
        deviceStore: deviceStore,
      ),
    ));
    await tester.pumpAndSettle(const Duration(seconds: 3));

    await tester.tap(find.byTooltip('チャット一覧'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('設定'));
    await tester.pumpAndSettle();

    expect(find.text('このスマホのAI API'), findsOneWidget);
    expect(find.text('Anthropic'), findsWidgets);
    await tester.dragUntilVisible(
      find.text('OpenAI'),
      find.byType(ListView).last,
      const Offset(0, -350),
      maxIteration: 12,
    );
    expect(find.text('OpenAI'), findsWidgets);
    await tester.dragUntilVisible(
      find.text('PC接続'),
      find.byType(ListView).last,
      const Offset(0, -500),
      maxIteration: 20,
    );
    expect(find.text('PC接続'), findsWidgets);
  });

  testWidgets('drawer shows space selector with local space', (tester) async {
    final storage = _FakeSecureStorage();
    final store = _testStore();
    final configStore = ApiConfigStore(storage: storage);
    final deviceStore = MobileDeviceStore(storage: storage);

    await tester.pumpWidget(MaterialApp(
      theme: theme.buildRumiTheme(),
      home: ChatScreen(
        store: store,
        configStore: configStore,
        deviceStore: deviceStore,
      ),
    ));
    await tester.pumpAndSettle(const Duration(seconds: 3));

    await tester.tap(find.byTooltip('チャット一覧'));
    await tester.pumpAndSettle();

    expect(find.text('このスマホ'), findsWidgets);
    expect(find.text('新規チャット'), findsWidgets);
  });
}
