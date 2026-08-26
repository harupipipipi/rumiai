# Rumi Remote Mobile

Rumi Remote Mobile is the Flutter client for managing a PC-hosted Rumi
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
| PC conversation summaries | `GET` | `/api/mobile/v1/conversations` |
| Module list | `GET` | `/api/defaultspack/modules` |
| Module detail | `GET` | `/api/defaultspack/modules/{id}` |
| Enable module | `POST` | `/api/defaultspack/modules/{id}/enable` |
| Disable module | `POST` | `/api/defaultspack/modules/{id}/disable` |
| Reload module | `POST` | `/api/defaultspack/modules/{id}/reload` |
| Roll back module | `POST` | `/api/defaultspack/modules/{id}/rollback` |
| Migration status | `GET` | `/api/defaultspack/migration/status` |
| Pack requests | `GET` | `/api/defaultspack/pack-requests` |

## PC conversation drawer

The Tobkiri mobile drawer presents PC-owned conversations as a read-only
navigation list. It uses only the scoped mobile conversation route above; it
does not retry through the legacy chat or UI routes. Rename, pin, and delete
remain PC actions and the drawer explains that limitation instead of showing
controls that cannot be completed safely.

Latest-message previews are a bounded display projection, not full message
content. The PC facade selects ordinary user or assistant text only, excludes
system, tool, hidden, private, and sensitive records, redacts common credential
forms, normalizes non-printing characters and whitespace, and caps the result
at 160 characters. The Flutter client renders the result as inert plain text.
Cached rows are kept only in memory during a transient outage, are visibly
marked stale/offline, and are cleared whenever the server URL or bearer-token
authority changes.

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
