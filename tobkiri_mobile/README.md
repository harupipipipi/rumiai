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
| Module list | `GET` | `/api/defaultspack/modules` |
| Module detail | `GET` | `/api/defaultspack/modules/{id}` |
| Enable module | `POST` | `/api/defaultspack/modules/{id}/enable` |
| Disable module | `POST` | `/api/defaultspack/modules/{id}/disable` |
| Reload module | `POST` | `/api/defaultspack/modules/{id}/reload` |
| Roll back module | `POST` | `/api/defaultspack/modules/{id}/rollback` |
| Migration status | `GET` | `/api/defaultspack/migration/status` |
| Pack requests | `GET` | `/api/defaultspack/pack-requests` |

## Authority approval review

The Authority approvals screen is a decision surface, not an authority source.
It presents the backend's structured consequence, exact target, affected
resource, reason, risk, one-shot scope, non-persistence, requester, Profile,
reviewing device, expiry, and audit statement before enabling a decision.
Raw request identifiers and resource payloads are available only in an
expandable technical section with recursive secret and credential redaction.

Mobile approval remains restricted to one execution. High-impact requests
require a separate review step, and requests marked for typed confirmation
remain disabled until the backend-provided phrase matches exactly. Approvals
use a fresh device-signed challenge; denial accepts an optional reason. The
screen keeps approved, denied, expired, stale, offline, incomplete-response,
and retry states visible in place instead of treating a missing or ambiguous
response as success.

The client does not grant capabilities, trust a client-supplied approval flag,
or restore an unavailable legacy Authority route. Request status, Profile
binding, resource constraints, challenge validity, settlement, and audit remain
owned by the Authority Kernel. If the active v4 runtime does not project a
mobile approval route, the screen fails closed.

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
