import 'package:flutter/widgets.dart';

class TobkiriChatAccessibilityLabels {
  const TobkiriChatAccessibilityLabels._(this.japanese);

  final bool japanese;

  static TobkiriChatAccessibilityLabels of(BuildContext context) =>
      TobkiriChatAccessibilityLabels._(
        Localizations.localeOf(context).languageCode == 'ja',
      );

  String get user => japanese ? 'あなたのメッセージ' : 'Your message';
  String get assistant => japanese ? 'Tobkiriの応答' : 'Tobkiri response';
  String get processing => japanese ? '処理中' : 'Processing';
  String get failed => japanese ? '送信に失敗しました' : 'Message failed';
  String get noContent => japanese ? '内容なし' : 'No content';
  String get content => japanese ? '内容' : 'Content';
  String get composer => japanese ? 'メッセージ入力欄' : 'Message field';
  String get composerHint =>
      japanese ? '複数行のメッセージを入力します' : 'Enter a multiline message';
  String get add => japanese ? 'オプションを追加' : 'Add options';
  String get addHint => japanese ? 'チャットのオプションを開きます' : 'Open chat options';
  String get send => japanese ? 'メッセージを送信' : 'Send message';
  String get sendHint =>
      japanese ? '入力したメッセージを送信します' : 'Send the entered message';
  String get sendDisabledHint =>
      japanese ? '送信するテキストを入力してください' : 'Enter text to send';
  String get stop => japanese ? '応答を停止' : 'Stop response';
  String get stopHint =>
      japanese ? '進行中の応答生成を停止します' : 'Stop the current response';
  String get copy => japanese ? 'メッセージをコピー' : 'Copy message';
  String get copyHint =>
      japanese ? 'メッセージの内容をコピーします' : 'Copy the message content';
  String get copied => japanese ? 'コピーしました' : 'Copied';
  String get reviewLinkHint =>
      japanese ? '開く前に宛先を確認します' : 'Review the destination before opening';
  String link(String label, String target) => japanese
      ? 'リンク: $label。宛先: $target'
      : 'Link: $label. Destination: $target';
  String get reviewDestination => japanese ? 'リンク先を確認' : 'Review destination';
  String get visibleText => japanese ? '表示テキスト' : 'Visible text';
  String get destinationHost => japanese ? '宛先ホスト' : 'Destination host';
  String get fullDestination => japanese ? '完全な URL' : 'Full URL';
  String get targetMismatch => japanese
      ? '表示テキストと実際の宛先が異なります。'
      : 'The visible text differs from the actual destination.';
  String get identityWarning => japanese
      ? '国際化ドメインです。見た目が似た文字に注意してください。'
      : 'This internationalized domain may contain lookalike characters.';
  String get open => japanese ? '開く' : 'Open';
  String get copyLink => japanese ? 'リンクをコピー' : 'Copy link';
  String get cancel => japanese ? 'キャンセル' : 'Cancel';
  String get linkCopied => japanese ? 'リンクをコピーしました' : 'Link copied';
  String get linkCopyFailed =>
      japanese ? 'リンクをコピーできませんでした。' : 'The link could not be copied.';
  String get malformedLink => japanese
      ? 'リンクの形式が正しくないため開けません。'
      : 'This link is malformed and cannot be opened.';
  String get blockedLink => japanese
      ? '安全でないスキームのためこのリンクはブロックされました。'
      : 'This link was blocked because its scheme is unsafe.';
  String get unsupportedLink => japanese
      ? 'このリンクのスキームはサポートされていません。'
      : 'This link scheme is not supported.';
  String get credentialLink => japanese
      ? '認証情報を含む誤解を招く URL のためブロックされました。'
      : 'This deceptive URL was blocked because it contains credentials.';
  String get launchFailed => japanese
      ? '外部アプリでリンクを開けませんでした。'
      : 'The link could not be opened in an external app.';
}
