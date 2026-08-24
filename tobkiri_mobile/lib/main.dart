import 'package:flutter/material.dart';

import 'src/appearance_settings.dart';
import 'src/rumi_remote_app.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  AppearanceSettingsStore store;
  try {
    store = await SharedPreferencesAppearanceSettingsStore.create();
  } catch (_) {
    store = InMemoryAppearanceSettingsStore();
  }
  final controller = await AppearanceSettingsController.load(store: store);
  runApp(RumiRemoteApp(appearanceController: controller));
}
