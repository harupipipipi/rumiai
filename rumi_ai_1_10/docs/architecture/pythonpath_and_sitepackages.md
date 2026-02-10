# PYTHONPATH と site-packages マウント仕様

Pack コード実行時に pip 依存を `import` 可能にする仕組みの説明です。

---

## 前提

Pack のコード実行は3種類あります:

| 実行種別 | ファイル | コンテナ内ワークスペース |
|----------|----------|--------------------------|
| `python_file_call` | `python_file_executor.py` | `/workspace` |
| `component_phase` | `secure_executor.py` | `/component` |
| `lib` | `secure_executor.py` | `/lib` |

いずれも `--network=none` の Docker コンテナで実行されます。

---

## site-packages の配置

ビルダーコンテナが生成した site-packages は以下に配置されます:

```
user_data/packs/<pack_id>/python/site-packages/
```

---

## コンテナへのマウント

実行コンテナ起動時に、site-packages ディレクトリが存在する場合のみ追加マウントされます:

```
-v <host_site_packages>:/pip-packages:ro
```

マウントポイントは `/pip-packages` で、**読み取り専用** です。

---

## PYTHONPATH

`-e PYTHONPATH=...` 環境変数で `/pip-packages` を追加します。

| 実行種別 | PYTHONPATH |
|----------|-----------|
| `python_file_call` | `/:/pip-packages` |
| `component_phase` | `/component:/pip-packages` |
| `lib` | `/lib:/pip-packages` |

site-packages が存在しない場合は `/pip-packages` は追加されません。

---

## Pack コードからの利用

Pack のブロックコードでは通常通り `import` するだけです:

```python
# blocks/my_block.py
import requests  # pip で導入された依存

def run(input_data, context=None):
    resp = requests.get("https://api.example.com/data")
    return {"data": resp.json()}
```

PYTHONPATH に `/pip-packages` が含まれているため、Python のインポート機構が自動的に解決します。

---

## permissive モード

Docker が利用できない permissive モードでは、site-packages のマウントは行われません。ホスト Python の標準パスのみが使われます。開発時にホスト環境に直接 `pip install` している場合は動作しますが、本番環境では Docker が必須です。

---

## セキュリティ

- site-packages は **読み取り専用** でマウントされるため、Pack コードが依存ライブラリを改ざんすることはできません
- マウントは Pack 単位で分離されており、Pack A の依存が Pack B から見えることはありません
- ビルダーコンテナと実行コンテナは完全に分離されています
