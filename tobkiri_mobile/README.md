# Tobkiri Mobile

Tobkiri Mobile is the Flutter client for accessible chat and management of a
PC-hosted Tobkiri `defaultspack` from iOS and Android devices on a trusted
network.

The app targets the Kernel Pack API on port `8765`, not the standalone
defaultspack chat transport on port `8766`. The Kernel API requires a bearer
token and is the safer surface for LAN access.

## PC Setup

Start Rumi with the Kernel API bound to the trusted LAN:

```powershell
$env:RUMI_API_BIND_ADDRESS="0.0.0.0"
python -m rumi_ai
```

Read the active API token from `tobkiri_runtime/user_data/hmac_keys.json` or run:

```powershell
cd tobkiri_runtime
python -c "from core_runtime.hmac_key_manager import HMACKeyManager; print(HMACKeyManager().get_active_key())"
```

In the app, set the server URL to `http://<pc-lan-ip>:8765` and paste the token.
Keep the PC firewall limited to your private network. Do not expose this port
directly to the public internet.

When using the Tauri desktop Viewer, closing the Viewer window sends it to the
background and keeps the Kernel API available for remote clients. Use the tray
menu's `Quit` item when you want to stop the Kernel and exit Rumi completely.

Android debug/profile builds allow cleartext HTTP for trusted-LAN development.
Android release builds do not globally allow cleartext traffic; use HTTPS or an
explicit release network policy if distributing a LAN-only build.

## API Coverage

| Purpose | Method | Path |
| --- | --- | --- |
| Health check | `GET` | `/health` |
| Module list | `GET` | `/api/defaultspack/modules` |
| Module detail | `GET` | `/api/defaultspack/modules/{id}` |
| Enable module | `POST` | `/api/defaultspack/modules/{id}/enable` |
| Disable module | `POST` | `/api/defaultspack/modules/{id}/disable` |
| Reload module | `POST` | `/api/defaultspack/modules/{id}/reload` |
| Roll back module | `POST` | `/api/defaultspack/modules/{id}/rollback` |
| Migration status | `GET` | `/api/defaultspack/migration/status` |
| Pack requests | `GET` | `/api/defaultspack/pack-requests` |

Chat uses only the canonical scoped mobile routes under
`/api/mobile/v1/conversations`. The app fails closed until an exact
`chat.read`/`chat.write` device connection has been securely provisioned. It
does not run tools on the phone or fall back to legacy host execution routes.

## Accessibility

- Message announcements identify the author, processing/error state, and
  content once. Empty pending and failed messages remain meaningful.
- Composer actions use stable Japanese and English labels and a 48 logical
  pixel minimum target in add, field, send, and stop order.
- Copy controls stay hidden until long-press or keyboard focus, while a screen
  reader copy action remains available on non-empty messages.
- HTTP(S) links have separate localized 48 logical pixel actions. Activating a
  link first shows its visible text, destination host, and full URL with Open,
  Copy link, and Cancel actions. Internationalized/lookalike hosts receive an
  additional warning.
- `file:`, active-content, custom/app-launching, malformed, credential-bearing,
  and unsupported destinations fail closed with an in-place explanation.
  Launcher failures are also reported without leaving or scrolling the chat.

For release validation, enable TalkBack and VoiceOver on real app builds. Check
user, assistant, pending, error, and empty announcements; traverse add, field,
and send/stop in order; then exercise copy, link, keyboard send, and stop.
For link validation, also check a normal HTTPS URL, a visible-text mismatch, an
IDN/punycode lookalike, a redirect-looking URL, `file:`, a custom scheme, and a
simulated launch failure. Confirm the destination is disclosed before Open and
that returning from the external app preserves the conversation position.

## Development

```powershell
cd tobkiri_mobile
flutter pub get
flutter analyze
flutter test
```

Android debug builds require a Flutter/Android SDK environment:

```powershell
flutter build apk --debug
```

iOS builds require macOS and Xcode:

```bash
flutter build ios --no-codesign
```
