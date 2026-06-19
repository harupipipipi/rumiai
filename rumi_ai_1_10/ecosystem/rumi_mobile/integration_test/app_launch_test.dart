import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

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

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('app launches and shows chat empty state', (tester) async {
    SharedPreferences.setMockInitialValues({});
    final storage = _FakeSecureStorage();
    final store = ChatStore();
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

    expect(find.text('Rumiへようこそ'), findsOneWidget);
    expect(find.byType(ComposerBar), findsOneWidget);
  });

  testWidgets('settings screen opens and shows sections', (tester) async {
    SharedPreferences.setMockInitialValues({});
    final storage = _FakeSecureStorage();
    final store = ChatStore();
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

    await tester.tap(find.byTooltip('設定'));
    await tester.pumpAndSettle();

    expect(find.text('AI API (ローカル動作)'), findsOneWidget);
    expect(find.text('PC接続'), findsOneWidget);
  });

  testWidgets('drawer shows space selector with local space', (tester) async {
    SharedPreferences.setMockInitialValues({});
    final storage = _FakeSecureStorage();
    final store = ChatStore();
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
