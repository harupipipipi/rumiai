# Flow Graph Editor TODO

この TODO は `rumi_start` / port contracts / basepack bootstrap の導入後に残る発展課題を整理したものです。

## Next

- `rumi_graph` から実ランタイム用 `steps` へのコンパイル精度を上げる
- `depends_on` と graph branching の対応関係を整理する
- port contracts を Pack manifest から自動供給できるようにする
- `basepack` を bootstrap profile から独立 runtime pack へ育てるか再検討する
- graph editor の UI snapshot / visual regression テストを追加する

## Notes

- いまの `basepack` は安全のため `defaultspack` を target にした bootstrap profile
- いまの execution は viewer 内シミュレーションで、`rumi_start` から到達可能な step を順に流す
- 既存ランタイム互換を保つため、YAML には `steps` と `rumi_graph` を併記している
