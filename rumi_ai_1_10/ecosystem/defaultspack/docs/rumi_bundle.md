# rumi_bundle

`rumi_bundle` は `defaultspack` に同梱する standalone frontend bundle の予約スロットです。

今回の段階では起動処理までは持たず、後続の desktop-app launch 実装が参照できる metadata を `defaultspack` 内に置きます。

## 置き場所

- `extensions/ui/rumi_bundle/manifest.json`
- `frontend/ui/rumi_bundle/module.json`

## いま持っている情報

- `bundle_id`: `rumi_bundle`
- `pack_id`: `defaultspack`
- `launch_mode`: `desktop_app`
- `entry_url`: `http://127.0.0.1:${RUMI_DEFAULTSPACK_PORT}`
- `port_source.default`: `8766`

## この PR でやらないこと

- Tauri app 自体の build / launch wiring
- startup profile の `Launch` からの起動
- nested helper app 化

つまり、この PR は「bundle を repo と bundle tree に正しく載せる」までを担当します。
