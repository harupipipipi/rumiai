import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

import 'src/rumi_app.dart';

void main() => runZonedGuarded(() {
  // Flutter captures the binding's zone; initialize it where runApp executes.
  WidgetsFlutterBinding.ensureInitialized();
  FlutterError.onError = (details) {
    FlutterError.presentError(details);
    debugPrint('Rumi Flutter error: ${details.exceptionAsString()}');
  };
  PlatformDispatcher.instance.onError = (error, stack) {
    debugPrint('Rumi platform error: $error\n$stack');
    return true;
  };
  runApp(const RumiApp());
}, (error, stack) => debugPrint('Rumi uncaught error: $error\n$stack'));
