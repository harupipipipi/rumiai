# Tobkiri Mobile

Tobkiri Mobile is the Flutter client for managing a PC-hosted Tobkiri
`defaultspack` from iOS and Android devices on a trusted network.

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

## Conversation navigation

The Conversations tab connects with paired-device tokens restricted to exactly
`chat.read` and `chat.write`. Connection details are kept in platform secure
storage and requests use only the canonical `/api/mobile/v1/conversations`
routes.

Navigation adapts to the available window instead of the physical device type:

- compact widths use a bounded temporary drawer and one app-bar New
  conversation action;
- medium widths keep spaces and conversations in a persistent navigation pane;
- expanded widths show spaces beside the conversation list and reserve a gap
  for a separating foldable hinge.

Space choices are standard radio controls with explicit selected and
online/offline semantics, keyboard focus, hover behavior, and scrollable
vertical layout. This keeps space switching next to the conversation list and
avoids hidden horizontal overflow at large text sizes or in split-screen.

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
