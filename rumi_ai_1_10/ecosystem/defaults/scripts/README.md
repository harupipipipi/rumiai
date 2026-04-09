# rumiai defaults Pack — 起動手順

## 前提条件

- Python 3.10 以上
- rumiai カーネル (`rumi_ai_1_10/`) がローカルに存在すること
- OpenAI API キー（または使用する AI プロバイダのキー）

## 起動手順

### 1. 依存ライブラリのインストール

```bash
pip install pyyaml cryptography
```

### 2. defaults Pack を ecosystem/defaults/ に配置

カーネルの `ecosystem/` ディレクトリ直下に `defaults` としてクローンまたはコピーします。

```bash
cd /path/to/rumi_ai_1_10
git clone https://github.com/harupipipipi/rumiai_defaults.git ecosystem/defaults
```

配置後のディレクトリ構造:

```
rumi_ai_1_10/
  ecosystem/
    defaults/          ← defaults Pack
      ecosystem.json
      blocks/
      flows/
      ui/
      scripts/         ← このディレクトリ
        approve_defaults.py
        setup_active_ecosystem.py
        README.md
      ...
```

### 3. defaults Pack を承認

カーネルルートから実行してください。

```bash
cd /path/to/rumi_ai_1_10
python ecosystem/defaults/scripts/approve_defaults.py
```

成功すると `user_data/permissions/defaults.grants.json` が生成されます。

### 4. active_ecosystem.json を設定

カーネルルートから実行してください。

```bash
cd /path/to/rumi_ai_1_10
python ecosystem/defaults/scripts/setup_active_ecosystem.py
```

成功すると `user_data/active_ecosystem.json` が生成されます（HMAC 署名付き）。

### 5. 環境変数の設定

使用する AI プロバイダに応じて環境変数を設定します。

```bash
export OPENAI_API_KEY="sk-..."
```

必要に応じて以下も設定できます:

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
export GOOGLE_API_KEY="..."
export RUMI_LOG_LEVEL="INFO"
```

defaults Pack の HTTP サーバ設定（省略時はデフォルト値が使用されます）:

```bash
export DEFAULTS_HTTP_HOST="127.0.0.1"   # デフォルト: 127.0.0.1
export DEFAULTS_HTTP_PORT="8766"         # デフォルト: 8766
```

### 6. カーネルを起動

```bash
cd /path/to/rumi_ai_1_10
python app.py --permissive
```

`--permissive` は開発環境用のフラグです。Docker サンドボックスなしで Pack コードを実行します。
本番環境では使用しないでください。

### 7. ブラウザでアクセス

```
http://127.0.0.1:8766
```

## トラブルシューティング

### "Pack not found" エラー

- `ecosystem/defaults/ecosystem.json` が存在するか確認
- `ecosystem.json` 内の `pack_id` が `"defaults"` であるか確認
- カーネルルート (`rumi_ai_1_10/`) から実行しているか確認

### "カーネルモジュールの読み込みに失敗" エラー

- `pip install pyyaml cryptography` を実行
- カーネルルートから実行しているか確認（`core_runtime/paths.py` が存在すること）

### 承認後に "hash_mismatch" が出る

- defaults Pack のファイルが承認後に変更されています
- `approve_defaults.py` を再実行して再承認してください

### active_ecosystem.json の HMAC 検証失敗

- `setup_active_ecosystem.py` を再実行して再署名してください
- `user_data/permissions/.secret_key` が変更されていないか確認
