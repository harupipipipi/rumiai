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
  - **スマホをペアリング**: scan a `rumi_pair_v2` QR to claim a PC pairing
    session and receive a scoped mobile device token after PC approval.
  - **API/モデル取り込み**: scan a `rumi_api` QR to fill API URL/key/model.
  - **PC接続 (Legacy)**: scan a `rumi_pc` QR to fill the Kernel API URL and
    bearer token for compatibility testing.
- PC pairing from the defaultspack control panel: open **Settings → アプリ** on
  the Mac to start **スマホをペアリング** or display the legacy PC接続QR,
  Cloudflare Pages QR, and API/モデル import QR.

## PC chat controls

When the phone is connected to a paired PC space, the chat header shows the
active PC model next to the selected space. The composer has a left-side **+**
menu for PC controls:

- choose any selectable PC model/profile reported by the PC capabilities
  endpoint;
- toggle PC turn options such as DeepThink/thinking levels when the selected
  model supports them;
- run PC slash commands from the menu instead of typing them manually.

The PC command list is not hard-coded in the mobile app. Mobile reads the
paired PC's capabilities/catalog response, including command manifest entries,
and posts selected commands to `/api/mobile/v1/commands/execute`. New public PC
slash commands should therefore appear in the **+** menu after the PC exposes
them through its command manifest and capabilities response.

Typing slash commands still works. For discoverability, `/` commands should
also be reachable from the **+** menu. Local on-device chat has its own model
selection from the same menu, backed by the stored API/model config.

## QR payload format

The PC side (defaultspack webapp **Settings → アプリ**) emits JSON QR codes:

```jsonc
// Recommended PC pairing QR (kind=rumi_pair_v2)
{
  "kind": "rumi_pair_v2",
  "version": 2,
  "pairingId": "pair-...",
  "code": "ABCD-2345",
  "baseUrls": ["http://192.168.1.10:8765"],
  "serverPublicKey": "",
  "expiresAt": 1781830000000
}

// PC接続QR (kind=rumi_pc)
{ "kind": "rumi_pc", "baseUrl": "http://192.168.1.10:8765", "token": "<redacted bearer token>" }

// API/モデルインポートQR (kind=rumi_api)
{ "kind": "rumi_api", "baseUrl": "https://api.example.test/v1", "apiKey": "<redacted provider key>", "model": "model-id", "label": "main" }
```

The mobile parser also accepts `api_key` as an alias for `apiKey`, and falls
back to `QrUrl` for plain `http(s)://` links (e.g. Cloudflare Pages URLs).

## PC pairing developer/tester checklist

1. Start Rumi with the Kernel API bound to a trusted LAN address. Use this only
   on a private network that the test phone can reach:

   ```bash
   cd rumi_ai_1_10
   RUMI_API_BIND_ADDRESS=0.0.0.0 python app.py
   ```

2. On the Mac/PC control panel, open **Settings → アプリ** and use
   **スマホをペアリング**. If the QR panel says no LAN URL was detected, enter
   `http://<PC LAN IP>:8765`; `localhost`, `127.0.0.1`, and `0.0.0.0` are not
   reachable from a real phone.
3. Scan the `rumi_pair_v2` QR from the mobile app. The app claims
   `/api/mobile/v1/pairings/{id}/claim` with the QR code, the mobile
   `device_id`, label, public key, and requested scopes.
4. Approve the claimed device in the control panel. Mobile polls
   `/api/mobile/v1/pairings/{id}/status?code=...&device_id=...` and stores the
   returned `dtk_...` device token in secure storage.
5. Confirm the paired phone can load PC chat state, create/send a test message,
   and still cannot call non-mobile API routes with the `dtk_...` token.

The legacy **PC接続QR** flow is still useful for compatibility checks, but it
places a full bearer token in the QR payload. Prefer `rumi_pair_v2` for normal
pairing tests.

## Security contracts from PR #364

- `dtk_...` device tokens are mobile-only. The backend accepts them only on
  `/api/mobile/v1/...` routes, and only when the route declares a matching
  device scope such as `chat.read`, `chat.write`, `tools.observe`,
  `tools.approve`, or `credentials.request`.
- Pairing status is observable by the PC, but token pickup requires both the
  original pairing code and the claimed `device_id`. A status response without
  both values must not include `device_token`.
- Credential transfer is fail-closed. PC-created transfers must name a paired
  device and include encrypted `ciphertext` plus `nonce`; plaintext keys,
  `api_key` fallback fields, and `plaintext`/`base64-wrapper` algorithms are
  rejected. Mobile get/ack calls require the matching authenticated device.
- Do not paste real provider keys, bearer tokens, or device tokens into docs,
  screenshots, issues, or test fixtures. Use redacted placeholders.

## Real-device install and LAN HTTP caveats

- TestFlight and App Store builds are not published yet. For a real iPhone,
  install from macOS with Xcode/Flutter and a valid signing team. The
  `flutter build ios --no-codesign` command is for unsigned build verification;
  use Xcode signing to run on a physical device.
- iPhone and PC must be on the same reachable LAN. Disable guest Wi-Fi
  isolation/VPNs for the test, allow the iOS Local Network prompt, and allow the
  Rumi port through the host firewall.
- iOS declares `NSLocalNetworkUsageDescription` and `NSAllowsLocalNetworking`
  for private-network HTTP. This supports LAN origins such as
  `http://192.168.x.x:8765`; use HTTPS or a reverse proxy for non-LAN exposure.
- Android declares internet/network/camera permissions and a network security
  config that permits cleartext HTTP for LAN testing. Keep cleartext pairing on
  trusted private networks only.
- For off-LAN smoke tests, expose the local Kernel API with Cloudflare Tunnel:

  ```bash
  cloudflared tunnel --protocol http2 --url http://127.0.0.1:8765
  ```

  Use the printed `https://...trycloudflare.com` origin in the `rumi_pair_v2`
  QR. Cloudflare Pages can host docs/install pages, but it does not expose a
  local Mac/PC Kernel API by itself.

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
