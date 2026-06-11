<!-- docs-i18n-links:start -->
[EN](../../node_spec.md) | [JP](./node_spec.md) | [KR](../ko/node_spec.md) | [CN](../zh-cn/node_spec.md)
<!-- docs-i18n-links:end -->

# ノード定義仕様

ノード定義は、エコシステム パックによって公開される静的機能ノードを記述します。

バージョン: `rumi.node.v1`

## 発見

コアは、エコシステム ノードの検出前に組み込みノードを登録します。フェーズ 1 には、コア所有の組み込みノードが 1 つだけあります。

```json
{
  "node_id": "rumi.start",
  "kind": "core.builtin",
  "display_name": {
    "en": "Start",
    "ja": "開始"
  },
  "ports": [
    {
      "id": "out",
      "direction": "output",
      "standards": ["rumi.flow.start"],
      "multiple": true,
      "required": false
    }
  ],
  "metadata": {
    "owner": "core"
  }
}
```

`rumi.start` はパックをスキャンする前にグローバル ノード レジストリに登録されるため、グラフはエコシステム パックを必要とせずにそれを参照できます。エコシステム パックは、コアが所有する組み込みノード ID をオーバーライドしてはなりません。

フェーズ 1 検出パス:

1. `ecosystem/<pack_id>/nodes/*.node.json`
2. `ecosystem/<pack_id>/components/*/node.json`

再帰的な `**/node.json` 検出は意図的に延期されます。

パックが提供するノード定義ファイルは、既存のパックの承認およびハッシュ検証フローを通過したパックからのみロードされます。これは、パックが提供するフロー読み込みを反映しています。ユーザー共有ファイルは、将来のローダーでサポートされる場合でも、スキーマの検証と診断が必要ですが、パックで承認されたコンテンツとしては扱われません。

## ファイルの形状

ファイルは 1 つ以上のノードを定義できます。

```json
{
  "version": "rumi.node.v1",
  "nodes": [
    {
      "node_id": "defaultspack.agent",
      "kind": "ecosystem.component",
      "display_name": {
        "en": "Agent",
        "ja": "エージェント"
      },
      "description": {
        "en": "Runtime node that combines AI, tools, memory, and prompts.",
        "ja": "AI・ツール・メモリ・プロンプトを束ねて実行するノード。"
      },
      "ports": [
        {
          "id": "start",
          "direction": "input",
          "display_name": {
            "en": "Start",
            "ja": "開始"
          },
          "standards": ["rumi.flow.start"],
          "aliases": ["start", "entry"],
          "multiple": false,
          "required": true
        },
        {
          "id": "tools",
          "direction": "input",
          "display_name": {
            "en": "Tools",
            "ja": "ツール"
          },
          "standards": [
            "rumi.tool.bundle",
            "defaultspack.tool.bundle.v1",
            "openai.function_tools.compat"
          ],
          "aliases": ["tools", "tool_bundle", "functions"],
          "multiple": true,
          "required": false
        },
        {
          "id": "result",
          "direction": "output",
          "display_name": {
            "en": "Result",
            "ja": "結果"
          },
          "standards": ["rumi.agent.result"],
          "aliases": ["result", "output"],
          "multiple": true,
          "required": false
        }
      ],
      "bindings": {
        "compile": "defaultspack.agent.compile_node",
        "on_input": {
          "tools": "defaultspack.agent.bind_tools"
        }
      },
      "requirements": {
        "configured_by": ["defaultspack.agent.configured"]
      },
      "metadata": {
        "pack_id": "defaultspack",
        "component": "agent",
        "icon": "bot",
        "category": "runtime"
      }
    }
  ]
}
```

## 必須フィールド

ノード:

- `node_id`
- `kind`
- `display_name`
- `ports`

ポート:

- `id`
- `direction`
- `standards`

## ポートの方向

許可される値:

- `input`
- `output`
- `bidirectional`

フェーズ 1 では、`input` および `output` のサポートが必要です。 `bidirectional` はスキーマによって予約されており、実装されるまでバリデーターによって拒否される可能性があります。

## 標準

`standards` は正規の互換性フィールドです。これは常に文字列のリストです。

ポートは次の場合に接続可能です。

```text
source.direction == "output"
target.direction == "input"
source.standards intersect target.standards is not empty
```

コアは標準文字列を比較しますが、ドメインの意味は解釈しません。

## Surface 起動メタデータ

サーフェス ノードは、起動時に開くデスクトップ アプリをアドバタイズできます。
ケイパビリティ グラフは、それをアクティブなフロントエンド サーフェスとして選択します。ノードはまだ
互換性のある出力ポートを公開します。起動メタデータはハンドオフのみを記述します
グラフコンパイル後のペイロード。

```json
{
  "node_id": "frontendpack.web_surface",
  "kind": "ecosystem.surface",
  "ports": [
    {
      "id": "surface",
      "direction": "output",
      "standards": ["rumi.surface"],
      "multiple": true
    }
  ],
  "metadata": {
    "pack_id": "frontendpack",
    "component_type": "frontend",
    "component_id": "web",
    "launch": {
      "kind": "desktop_app",
      "pack_id": "frontendpack",
      "surface": "browser",
      "default": true,
      "env": {
        "FRONTENDPACK_SURFACE": "web"
      }
    }
  }
}
```

安全のため、`metadata.launch.pack_id` はノード自身のパック ID と一致する必要があります。ノード
あるパックから別のパックで起動起動を指定することはできません。

## レガシー入力の互換性

レガシー ファイルでは以下が使用される場合があります。

```json
{
  "node_id": "defaultspack.agent",
  "name": "Agent",
  "ports": [
    {
      "id": "tools",
      "direction": "input",
      "contract": "rumi.tool.bundle"
    }
  ]
}
```

ローダーはこれを v1 モデルに正規化します。

- `display_name`が存在しない場合、`name`は`display_name.en`になります。
- `standards`が存在しない場合、`contract`は`standards: [contract]`になります。

内部モデルでは、`display_name` と `standards` のみを使用する必要があります。

## 表示名のフォールバック

表示テキストの解像度:

1. `display_name[user_locale]`
2. `display_name.en`
3. レガシー`name`
4. `node_id` またはポート `id`

## バインディング

バインディングはパックが所有するハンドラーに名前を付けます。コアはハンドラー ID を保存および解決しますが、それらにドメインの意味を割り当てません。

共通のバインディング スロット:

- `compile`
- `on_input.<port_id>`

バインディング ハンドラーは、承認されたレジストリまたはカーネル ハンドラー インフラストラクチャを通じて解決される必要があります。直接任意のインポートは許可されていません。
