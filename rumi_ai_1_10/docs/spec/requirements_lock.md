# requirements.lock 規約

Pack が PyPI 依存を宣言するためのファイル仕様です。

---

## 置き場所

pack_subdir 基準で以下の順に探索し、最初に見つかったものを使います:

1. `<pack_subdir>/requirements.lock`
2. `<pack_subdir>/backend/requirements.lock`（互換）

pack_subdir は `core_runtime/paths.py` の `discover_pack_locations()` で決定されます。

---

## フォーマット

標準の pip requirements 形式です。バージョンをピン留めすることを強く推奨します。

### 推奨（ピン留め）

```
requests==2.31.0
flask==3.0.0
Jinja2==3.1.3
```

### 許容（範囲指定）

```
requests>=2.28,<3.0
flask~=3.0
```

### 非推奨（バージョンなし）

```
requests
flask
```

バージョンなしは再現性が低下するため非推奨です。

---

## sdist 例外

デフォルトでは wheel のみ許可です（`--only-binary=:all:`）。

wheel が存在しないパッケージを含む場合、`pip download` が失敗し、ステータスは `failed` になります。

ユーザーが approve 時に `allow_sdist: true` を指定すると、sdist からのビルドが許可されます。これは別扱いの承認として監査ログに記録されます。

---

## ファイル名について

ファイル名は `requirements.lock` 固定です。`requirements.txt` は検出対象外です。これは意図的で、ロックファイルであることを明示するためです。

---

## ハッシュ

candidate_key の一部として requirements.lock の SHA-256 ハッシュが使われます。ファイル内容が変わると新しい candidate_key になり、再承認が必要です。
