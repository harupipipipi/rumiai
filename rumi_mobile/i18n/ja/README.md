<!-- docs-i18n-links:start -->
[EN](../../README.md) | [JP](./README.md) | [KR](../ko/README.md) | [CN](../zh-cn/README.md)
<!-- docs-i18n-links:end -->

# ルーミリモートモバイル

Rumi Remote Mobile は、PC でホストされる Rumi を管理するための Flutter クライアントです。
信頼されたネットワーク上の iOS および Android デバイスからの `defaultspack`。

このアプリは、スタンドアロンではなく、ポート `8765` のカーネル パック API をターゲットとしています。
ポート `8766` 上のデフォルトパック チャット トランスポート。カーネル API にはベアラーが必要です
トークンであり、LAN アクセスのより安全な面です。

## PC セットアップ

信頼できる LAN にバインドされたカーネル API を使用して Rumi を起動します。

```powershell
$env:RUMI_API_BIND_ADDRESS="0.0.0.0"
python -m rumi_ai
```

`rumi_ai_1_10/user_data/hmac_keys.json` からアクティブな API トークンを読み取るか、次を実行します。

```powershell
cd rumi_ai_1_10
python -c "from core_runtime.hmac_key_manager import HMACKeyManager; print(HMACKeyManager().get_active_key())"
```

アプリで、サーバー URL を `http://<pc-lan-ip>:8765` に設定し、トークンを貼り付けます。
PC ファイアウォールをプライベート ネットワークに限定してください。このポートを公開しないでください
公共のインターネットに直接接続します。

Tauri デスクトップ ビューアを使用している場合、ビューア ウィンドウを閉じるとビューア ウィンドウが
バックグラウンドで使用し、リモート クライアントがカーネル API を使用できるようにします。トレイを使用する
カーネルを停止して Rumi を完全に終了したい場合は、メニューの `Quit` 項目を使用します。

Android デバッグ/プロファイル ビルドでは、トラステッド LAN 開発用のクリアテキスト HTTP が可能です。
Android リリース ビルドでは、クリアテキスト トラフィックがグローバルに許可されません。 HTTPS または
LAN のみのビルドを配布する場合は、ネットワーク ポリシーを明示的にリリースします。

## API の範囲

|目的 |方法 |パス |
| --- | --- | --- |
|健康診断 | `GET` | `/health` |
|モジュールリスト | `GET` | `/api/defaultspack/modules` |
|モジュールの詳細 | `GET` | `/api/defaultspack/modules/{id}` |
|モジュールを有効にする | `POST` | `/api/defaultspack/modules/{id}/enable` |
|モジュールを無効にする | `POST` | `/api/defaultspack/modules/{id}/disable` |
|モジュールをリロード | `POST` | `/api/defaultspack/modules/{id}/reload` |
|ロールバックモジュール | `POST` | `/api/defaultspack/modules/{id}/rollback` |
|移行ステータス | `GET` | `/api/defaultspack/migration/status` |
|パックリクエスト | `GET` | `/api/defaultspack/pack-requests` |

## 開発

```powershell
cd rumi_mobile
flutter pub get
flutter analyze
flutter test
```

Android デバッグ ビルドには Flutter/Android SDK 環境が必要です。

```powershell
flutter build apk --debug
```

iOS ビルドには macOS と Xcode が必要です。

```bash
flutter build ios --no-codesign
```
