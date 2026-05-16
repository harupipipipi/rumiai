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

Read the active API token from `rumi_ai_1_10/user_data/hmac_keys.json` or run:

```powershell
cd rumi_ai_1_10
python -c "from core_runtime.hmac_key_manager import HMACKeyManager; print(HMACKeyManager().get_active_key())"
```

In the app, set the server URL to `http://<pc-lan-ip>:8765` and paste the token.
Keep the PC firewall limited to your private network. Do not expose this port
directly to the public internet.

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

## Development

```powershell
cd rumi_mobile
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
