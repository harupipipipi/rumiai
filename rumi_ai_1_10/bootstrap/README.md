# Bootstrap Directory

このディレクトリに配置した `*.py` ファイルは、Kernel起動前に実行されます。

## 用途

- 環境変数の検証
- Credential（API Key等）の復号
- 外部サービスへの接続チェック
- マイグレーションの実行

## 規約

各ファイルは `run(context)` 関数を持つことができます：

```python
def run(context):
    diagnostics = context["diagnostics"]
    interface_registry = context["interface_registry"]
    
    # 初期化処理
    pass
```

ファイルはアルファベット順に実行されます。
