<!-- docs-i18n-links:start -->
[EN](../../goal-command.md) | [JP](./goal-command.md) | [KR](../ko/goal-command.md) | [CN](../zh-cn/goal-command.md)
<!-- docs-i18n-links:end -->

# /ゴールスラッシュコマンド

`/goal <description>` は、ツールを直接実行せずに、defaultspack コンソールで目標追求ループを実行します。

1. **ワーカー** エージェントは、目標に向けて次の具体的な貢献を行います。
2. 各ワーカーのターン後に、独立したサードパーティ **評価者** エージェントが
   目標が達成されたかどうかを確認します。
3. 目標がまだ達成されていない場合、評価者は新しい結果を返します。
   `next_instruction` とワーカーに再度プロンプトが表示されます。
4. ループは、評価者が目標を達成したとマークしたとき、または目標が達成されたときに停止します。
   `max_iterations` キャップがヒットします (デフォルトは `5`、ハードキャップ `20`)。

## 引数

|名前 |タイプ |必須 |デフォルト |説明 |
|------------------|---------|----------|---------|-----------------------------------------------------------------------------|
| `goal` |文字列 |はい | — |労働者が追求すべき目標に関する自由形式の説明。                 |
| `max_iterations` |文字列 |いいえ | `5` |ワーカーと評価者の最大ラウンドトリップ数。 1 ～ 20 に固定されます。                      |
| `model` |文字列 |いいえ |アクティブ |オプションのモデル ヒントは、作業者ターンと評価者のターンの両方に渡されます。              |

スラッシュコマンドが登録されているのは、
[`commands/manifests/goal.json`](../commands/manifests/goal.json)と
動作は[`blocks/goal/run.py`](../blocks/goal/run.py)にあります。

## 結果エンベロープ

成功すると、コマンドは次を返します。

```json
{
  "status": "ok",
  "data": {
    "command": { "...": "manifest fields" },
    "executed": true,
    "result": {
      "goal": "Write a haiku about programming",
      "achieved": true,
      "reason": "Three-line haiku produced as requested.",
      "iterations": [
        {
          "iteration": 1,
          "worker_output": "...",
          "verdict": { "achieved": true, "reason": "...", "next_instruction": "" }
        }
      ],
      "iteration_count": 1,
      "final_output": "...",
      "max_iterations": 5,
      "stopped_reason": "achieved"
    }
  }
}
```

ループが目標を達成せずに`max_iterations`に到達すると、`achieved`
`false` になり、`stopped_reason` は `"max_iterations_reached"` になります。とき
Worker または Evaluator モデルの呼び出しが失敗し、コマンドが返される
`status: "error"` と `code: "WORKER_FAILED"` または `code: "EVALUATOR_FAILED"`
部分的な進行状況を記録する `iterations` 配列。

## 拡張性に関する注意: `pack_block` 実行タイプ

`pack_block` フックが配置された後、ファイルの追加によって `/goal` 自体が実装されます。

* `commands/manifests/goal.json`はスラッシュコマンドを宣言します。
* `blocks/goal/run.py` は目標追求ループを実装します。

この機能は、`pack_block` 実行タイプを介して接続されています。
`SlashCommandRegistry`。これにより、マニフェストが以下の Python ブロックにディスパッチされます。
`blocks/<dotted.path>`が`run(input, context) -> dict`を暴露します。

このブロックはツールを直接実行しません。のモデル呼び出しのみを行います。
作業者と評価者が交代します。
`pack_block` は、`default` および `pack` のマニフェスト原点に対してのみ許可されます (決して許可されません)
`user_data/shared/commands/` にあるユーザー マニフェストの場合)、信頼できないコマンド
マニフェストは任意のモジュールをロードできません。

バックエンド動作を必要とする今後のスラッシュ コマンドは、次の方法で追加できるようになりました。

1. `commands/manifests/<command>.json` にマニフェストをドロップします。
2. `blocks/<area>/<file>.py` にブロックをドロップし、`run` 呼び出し可能オブジェクトを公開します。

これらの追加のために既存のファイルを変更する必要はありません。
