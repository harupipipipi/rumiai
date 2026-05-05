# Browser v2

Browser v2 は browser 専用の安定操作レイヤーです。OS 画面操作を担当する `computer_use` とは分け、profile / tab / snapshot / ref / CDP 操作を `domain/browser/` に集約します。

## Domain

| module | responsibility |
|---|---|
| `domain/browser/profiles.py` | managed / existing / remote CDP profile metadata |
| `domain/browser/sessions.py` | session lifecycle, tabs, navigation, screenshots |
| `domain/browser/cdp.py` | lightweight CDP client and fallback shapes |
| `domain/browser/snapshots.py` | snapshot refs and stale ref recovery |
| `domain/browser/actions.py` | tool action dispatcher |
| `domain/browser/policy.py` | browser action risk classification |

Default profile data is stored under shared user data, while downloads and screenshots are profile-scoped artifacts.

## Ref Model

Snapshots assign compact refs to interactive elements:

```json
{
  "snapshot_id": "snap_xxx",
  "generation": 3,
  "refs": [
    {
      "ref": "e1",
      "role": "button",
      "name": "Sign in",
      "text": "Sign in",
      "bounds": {"x": 100, "y": 120, "width": 80, "height": 32},
      "clickable": true,
      "editable": false
    }
  ]
}
```

`click_ref`, `type_ref`, `select_ref`, `hover_ref`, and `focus_ref` first resolve the ref from the current store. If a ref is stale, Browser v2 refreshes the snapshot and tries to match by role / name / text before returning a `computer_use` fallback contract.

## Tool Actions

`browser_use` keeps its existing actions and adds:

| group | actions |
|---|---|
| profiles | `profiles.list`, `profiles.create`, `profiles.set_active`, `profiles.delete` |
| tabs | `tabs.list`, `tabs.open`, `tabs.focus`, `tabs.close`, `tabs.reload`, `tabs.back`, `tabs.forward` |
| navigation | `navigate`, `wait_for`, `press` |
| snapshot | `snapshot`, `snapshot_full`, `find_ref` |
| ref interaction | `click_ref`, `type_ref`, `select_ref`, `hover_ref`, `focus_ref` |
| artifacts | `screenshot`, `screenshot_full_page`, `screenshot_ref`, `downloads.list`, `downloads.wait`, `pdf`, `upload_file` |

## Routes

| method | path |
|---|---|
| `GET/POST` | `/api/browser/profiles` |
| `GET/PUT/DELETE` | `/api/browser/profiles/{profile_id}` |
| `POST` | `/api/browser/profiles/{profile_id}/start` |
| `POST` | `/api/browser/profiles/{profile_id}/stop` |
| `POST` | `/api/browser/profiles/{profile_id}/restart` |
| `GET` | `/api/browser/profiles/{profile_id}/health` |
| `GET/POST` | `/api/browser/profiles/{profile_id}/tabs` |
| `POST` | `/api/browser/profiles/{profile_id}/tabs/{tab_id}/focus` |
| `DELETE` | `/api/browser/profiles/{profile_id}/tabs/{tab_id}` |
| `POST` | `/api/browser/profiles/{profile_id}/snapshot` |
| `POST` | `/api/browser/profiles/{profile_id}/screenshot` |

The `browser_computer` wrapper can call these browser actions while preserving the older browser/computer contract.
