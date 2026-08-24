import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

/// Tobkiri-specific semantic colors that complement the active color scheme.
@immutable
class RumiColors extends ThemeExtension<RumiColors> {
  const RumiColors({
    required this.success,
    required this.successContainer,
    required this.warning,
    required this.warningContainer,
    required this.info,
    required this.infoContainer,
    required this.bubbleUser,
    required this.bubbleAssistant,
    required this.bubbleUserText,
    required this.bubbleAssistantText,
    required this.codeBackground,
    required this.codeForeground,
  });

  final Color success;
  final Color successContainer;
  final Color warning;
  final Color warningContainer;
  final Color info;
  final Color infoContainer;
  final Color bubbleUser;
  final Color bubbleAssistant;
  final Color bubbleUserText;
  final Color bubbleAssistantText;
  final Color codeBackground;
  final Color codeForeground;

  static const light = RumiColors(
    success: Color(0xFF176B3A),
    successContainer: Color(0xFFDFF3E8),
    warning: Color(0xFF765900),
    warningContainer: Color(0xFFFFE9A8),
    info: Color(0xFF185D8C),
    infoContainer: Color(0xFFD7EEFF),
    bubbleUser: Color(0xFFD5F2E8),
    bubbleAssistant: Color(0xFFFFFFFF),
    bubbleUserText: Color(0xFF103F34),
    bubbleAssistantText: Color(0xFF182027),
    codeBackground: Color(0xFFF1F3F5),
    codeForeground: Color(0xFF182027),
  );

  static const dark = RumiColors(
    success: Color(0xFF87D9A8),
    successContainer: Color(0xFF124D2D),
    warning: Color(0xFFF2CF67),
    warningContainer: Color(0xFF574500),
    info: Color(0xFF9ACBFF),
    infoContainer: Color(0xFF164B72),
    bubbleUser: Color(0xFF075042),
    bubbleAssistant: Color(0xFF252A2E),
    bubbleUserText: Color(0xFFD9F9EC),
    bubbleAssistantText: Color(0xFFE1E3E5),
    codeBackground: Color(0xFF151A1E),
    codeForeground: Color(0xFFE1E3E5),
  );

  static const highContrastLight = RumiColors(
    success: Color(0xFF004F24),
    successContainer: Color(0xFFBFF5CF),
    warning: Color(0xFF4D3900),
    warningContainer: Color(0xFFFFE08A),
    info: Color(0xFF003D66),
    infoContainer: Color(0xFFC2E7FF),
    bubbleUser: Color(0xFF006A57),
    bubbleAssistant: Color(0xFFFFFFFF),
    bubbleUserText: Color(0xFFFFFFFF),
    bubbleAssistantText: Color(0xFF000000),
    codeBackground: Color(0xFF000000),
    codeForeground: Color(0xFFFFFFFF),
  );

  static const highContrastDark = RumiColors(
    success: Color(0xFF9BFFBE),
    successContainer: Color(0xFF003518),
    warning: Color(0xFFFFDE70),
    warningContainer: Color(0xFF493800),
    info: Color(0xFF9DD5FF),
    infoContainer: Color(0xFF003A61),
    bubbleUser: Color(0xFFB6F7E4),
    bubbleAssistant: Color(0xFF000000),
    bubbleUserText: Color(0xFF000000),
    bubbleAssistantText: Color(0xFFFFFFFF),
    codeBackground: Color(0xFF000000),
    codeForeground: Color(0xFFFFFFFF),
  );

  @override
  RumiColors copyWith({
    Color? success,
    Color? successContainer,
    Color? warning,
    Color? warningContainer,
    Color? info,
    Color? infoContainer,
    Color? bubbleUser,
    Color? bubbleAssistant,
    Color? bubbleUserText,
    Color? bubbleAssistantText,
    Color? codeBackground,
    Color? codeForeground,
  }) =>
      RumiColors(
        success: success ?? this.success,
        successContainer: successContainer ?? this.successContainer,
        warning: warning ?? this.warning,
        warningContainer: warningContainer ?? this.warningContainer,
        info: info ?? this.info,
        infoContainer: infoContainer ?? this.infoContainer,
        bubbleUser: bubbleUser ?? this.bubbleUser,
        bubbleAssistant: bubbleAssistant ?? this.bubbleAssistant,
        bubbleUserText: bubbleUserText ?? this.bubbleUserText,
        bubbleAssistantText: bubbleAssistantText ?? this.bubbleAssistantText,
        codeBackground: codeBackground ?? this.codeBackground,
        codeForeground: codeForeground ?? this.codeForeground,
      );

  @override
  RumiColors lerp(covariant RumiColors? other, double t) {
    if (other is! RumiColors) {
      return this;
    }
    return RumiColors(
      success: Color.lerp(success, other.success, t)!,
      successContainer:
          Color.lerp(successContainer, other.successContainer, t)!,
      warning: Color.lerp(warning, other.warning, t)!,
      warningContainer:
          Color.lerp(warningContainer, other.warningContainer, t)!,
      info: Color.lerp(info, other.info, t)!,
      infoContainer: Color.lerp(infoContainer, other.infoContainer, t)!,
      bubbleUser: Color.lerp(bubbleUser, other.bubbleUser, t)!,
      bubbleAssistant: Color.lerp(bubbleAssistant, other.bubbleAssistant, t)!,
      bubbleUserText: Color.lerp(bubbleUserText, other.bubbleUserText, t)!,
      bubbleAssistantText:
          Color.lerp(bubbleAssistantText, other.bubbleAssistantText, t)!,
      codeBackground: Color.lerp(codeBackground, other.codeBackground, t)!,
      codeForeground: Color.lerp(codeForeground, other.codeForeground, t)!,
    );
  }
}

/// Builds the Tobkiri Material theme for a brightness and contrast preference.
ThemeData buildRumiTheme({
  Brightness brightness = Brightness.light,
  bool highContrast = false,
}) {
  const seed = Color(0xFF2F7D6B);
  final scheme = ColorScheme.fromSeed(
    seedColor: seed,
    brightness: brightness,
    contrastLevel: highContrast ? 1 : 0,
  );
  final isDark = brightness == Brightness.dark;
  final colors = switch ((isDark, highContrast)) {
    (false, false) => RumiColors.light,
    (true, false) => RumiColors.dark,
    (false, true) => RumiColors.highContrastLight,
    (true, true) => RumiColors.highContrastDark,
  };
  final overlayStyle = SystemUiOverlayStyle(
    statusBarColor: Colors.transparent,
    statusBarIconBrightness: isDark ? Brightness.light : Brightness.dark,
    statusBarBrightness: isDark ? Brightness.dark : Brightness.light,
    systemNavigationBarColor: scheme.surface,
    systemNavigationBarIconBrightness:
        isDark ? Brightness.light : Brightness.dark,
    systemNavigationBarDividerColor: scheme.outlineVariant,
  );

  return ThemeData(
    useMaterial3: true,
    colorScheme: scheme,
    brightness: brightness,
    scaffoldBackgroundColor: isDark ? scheme.surface : const Color(0xFFF6F8FA),
    cupertinoOverrideTheme: CupertinoThemeData(brightness: brightness),
    extensions: [colors],
    appBarTheme: AppBarTheme(
      centerTitle: false,
      elevation: 0,
      backgroundColor: scheme.surface,
      foregroundColor: scheme.onSurface,
      systemOverlayStyle: overlayStyle,
    ),
    cardTheme: CardThemeData(
      elevation: 0,
      color: scheme.surface,
      margin: EdgeInsets.zero,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(8),
        side: BorderSide(color: scheme.outlineVariant),
      ),
    ),
    inputDecorationTheme: InputDecorationTheme(
      border: OutlineInputBorder(borderRadius: BorderRadius.circular(8)),
      filled: true,
      fillColor: scheme.surface,
    ),
    navigationBarTheme: NavigationBarThemeData(
      backgroundColor: scheme.surface,
      indicatorColor: scheme.secondaryContainer,
    ),
    textSelectionTheme: TextSelectionThemeData(
      cursorColor: scheme.primary,
      selectionColor: scheme.primary.withValues(alpha: 0.32),
      selectionHandleColor: scheme.primary,
    ),
    dividerTheme: DividerThemeData(
      color: scheme.outlineVariant,
      thickness: highContrast ? 2 : 1,
    ),
  );
}

/// The standard light Tobkiri theme.
ThemeData buildRumiLightTheme() => buildRumiTheme();

/// The standard dark Tobkiri theme.
ThemeData buildRumiDarkTheme() => buildRumiTheme(brightness: Brightness.dark);

/// The accessible high-contrast light Tobkiri theme.
ThemeData buildRumiHighContrastLightTheme() =>
    buildRumiTheme(highContrast: true);

/// The accessible high-contrast dark Tobkiri theme.
ThemeData buildRumiHighContrastDarkTheme() =>
    buildRumiTheme(brightness: Brightness.dark, highContrast: true);
