# Rumi Mobile

Rumi Mobile is the Flutter client for Rumi. It ships a ChatGPT-style chat UI
that runs **on-device** against any OpenAI-compatible endpoint, plus QR-based
import for API/model config and PC connection.

The app lives under the defaultspack ecosystem folder so it sits next to the
canonical control panel at `rumi_ai_1_10/ecosystem/defaultspack/`.

## Features

- Rich ChatGPT-like chat UI: new chat, conversation list, pin/rename/delete,
  markdown rendering, streaming responses, typing indicator.
- Smartphone-local: conversations and API config are stored on-device
  (`shared_preferences` for history, `flutter_secure_storage` for keys).
  No server is required to chat.
- OpenAI-compatible streaming client (`/chat/completions` SSE).
- QR import:
  - **API/モデル取り込み**: scan a `rumi_api` QR to fill API URL/key/model.
  - **PC接続**: scan a `rumi_pc` QR to fill the Kernel API URL + bearer token.
- PC pairing from the defaultspack control panel: open **Settings → アプリ** on
  the Mac to display the PC接続QR, Cloudflare Pages QR, and API/モデル import QR.

## QR payload format

The PC side (defaultspack webapp **Settings → アプリ**) emits JSON QR codes:

```jsonc
// PC接続QR (kind=rumi_pc)
{ "kind": "rumi_pc", "baseUrl": "http://192.168.1.10:8765", "token": "<hmac key>" }

// API/モデルインポートQR (kind=rumi_api)
{ "kind": "rumi_api", "baseUrl": "https://api.openai.com/v1", "apiKey": "sk-...", "model": "gpt-4o-mini", "label": "main" }
```

The mobile parser also accepts `api_key` as an alias for `apiKey`, and falls
back to `QrUrl` for plain `http(s)://` links (e.g. Cloudflare Pages URLs).

## PC setup (Kernel API for remote control)

Start Rumi with the Kernel API bound to the trusted LAN:

```powershell
$env:RUMI_API_BIND_ADDRESS="0.0.0.0"
python -m rumi_ai
```

Read the active API token from `rumi_ai_1_10/user_data/hmac_keys.json` or:

```powershell
cd rumi_ai_1_10
python -c "from core_runtime.hmac_key_manager import HMACKeyManager; print(HMACKeyManager().get_active_key())"
```

Then on the Mac, open the defaultspack control panel → **Settings → アプリ** and
paste the token into the PC接続QR panel. Scan the displayed QR with the mobile
app's **PC接続QRをスキャン**.

## Distribution status

TestFlight and App Store builds are **coming soon**. The **Settings → アプリ**
panel in the defaultspack control panel reflects this state.

## Development

```bash
cd rumi_ai_1_10/ecosystem/rumi_mobile
flutter pub get
flutter analyze
flutter test
```

Android debug builds require a Flutter/Android SDK environment:

```bash
flutter build apk --debug
```

iOS builds require macOS and Xcode:

```bash
flutter build ios --no-codesign
```

Camera permission is requested for QR scanning (`NSCameraUsageDescription` on
iOS, `android.permission.CAMERA` on Android).
