

# kernel.py Mixin分割 PR

## 概要

`core_runtime/kernel.py`（2863行）をMixin方式で3ファイル＋薄いkernel.pyに分割し、保守性を改善する。機能追加なし、挙動維持が最優先。

## 変更理由

- kernel.pyが2863行に肥大化し、レビュー・保守が困難になっていた
- ハンドラの追加/修正時に無関係なコードを大量にスクロールする必要があった
- ドメインごとの責務分離ができていなかった

## 分割方式

Mixin（多重継承）方式を採用。Kernelのメソッドを「コード移動のみ」で別ファイルへ移し、ロジック変更は行わない。

```
Kernel(KernelSystemHandlersMixin, KernelRuntimeHandlersMixin, KernelCore)
```

## ファイル構成

| ファイル | クラス | 行数(概算) | 役割 |
|---------|--------|-----------|------|
| `kernel_core.py` | `KernelCore` | ~580行 | エンジン本体（`__init__`、Flow実行、ctx構築、shutdown、変数解決） |
| `kernel_handlers_system.py` | `KernelSystemHandlersMixin` | ~370行 | 起動/システム系 `_h_*` ハンドラ（29キー） |
| `kernel_handlers_runtime.py` | `KernelRuntimeHandlersMixin` | ~680行 | 運用/実行系 `_h_*` ハンドラ（37キー） |
| `kernel.py` | `Kernel` | ~130行 | Mixin組み立て、ハンドラ登録、re-export |

合計 ≈ 1760行（元の2863行から圧縮。コメント/docstring整理による自然減）。

## 設計判断

### なぜMixin方式か

- **コード移動のみ**で済む（ロジック変更なし → バグリスク最小）
- `self.diagnostics` 等の属性アクセスがそのまま動く
- 外部からの `from core_runtime.kernel import Kernel` が変わらない

### なぜ関数切り出し方式ではないか

- ハンドラが `self.diagnostics`, `self.interface_registry` 等に密結合しており、引数の追加が大量に必要になる
- 差分が大きくバグが出やすい

### 行数の偏りについて

計画では「概ね1000/1000/1000」を目標としたが、実際のハンドラ行数は不均等（system系は短いif-try-except が多い）。ロジックを変更してまで行数を揃える必要はないと判断した。

## ハンドラ振り分け一覧

### kernel_core.py（KernelCore）— エンジン本体

| メソッド | 説明 |
|---------|------|
| `__init__` | コンストラクタ |
| `_now_ts` | UTCタイムスタンプ |
| `_get_uds_proxy_manager` | UDS Proxy遅延初期化 |
| `_get_capability_proxy` | Capability Proxy遅延初期化 |
| `_resolve_handler` | ハンドラ名→callable解決 |
| `load_flow` | Flow読み込みエントリポイント |
| `_log_fallback_warning` | 旧flow警告 |
| `_load_legacy_flow` | 旧形式flow読み込み |
| `_convert_new_flow_to_pipelines` | 新flow→pipelines変換 |
| `_merge_flow` | Flow定義マージ |
| `_load_single_flow` | 単一flowファイル読み込み |
| `_minimal_fallback_flow` | フォールバックflow |
| `_parse_flow_text` | YAML/JSONパース |
| `run_startup` | 起動パイプライン実行 |
| `run_pipeline` | 名前指定パイプライン実行 |
| `execute_flow` | async Flow実行 |
| `execute_flow_sync` | sync Flow実行 |
| `_execute_flow_internal` | Flow実行内部 |
| `_execute_steps_async` | ステップ群async実行 |
| `_execute_handler_step_async` | ハンドラステップasync実行 |
| `_execute_sub_flow_step` | サブFlow実行 |
| `_eval_condition` | 条件式評価 |
| `save_flow_to_file` | Flow保存 |
| `load_user_flows` | ユーザーFlow読み込み |
| `on_shutdown` | shutdownハンドラ登録 |
| `shutdown` | シャットダウン |
| `_build_kernel_context` | コンテキスト構築 |
| `_execute_flow_step` | 同期ステップ実行 |
| `_resolve_value` | 変数解決 |
| `_resolve_args` | 引数解決 |

### kernel_handlers_system.py（KernelSystemHandlersMixin）— 起動/システム系（29キー）

| ハンドラキー | メソッド |
|-------------|---------|
| `kernel:mounts.init` | `_h_mounts_init` |
| `kernel:registry.load` | `_h_registry_load` |
| `kernel:active_ecosystem.load` | `_h_active_ecosystem_load` |
| `kernel:interfaces.publish` | `_h_interfaces_publish` |
| `kernel:ir.get` | `_h_ir_get` |
| `kernel:ir.call` | `_h_ir_call` |
| `kernel:ir.register` | `_h_ir_register` |
| `kernel:exec_python` | `_h_exec_python` |
| `kernel:ctx.set` | `_h_ctx_set` |
| `kernel:ctx.get` | `_h_ctx_get` |
| `kernel:ctx.copy` | `_h_ctx_copy` |
| `kernel:execute_flow` | `_h_execute_flow` |
| `kernel:save_flow` | `_h_save_flow` |
| `kernel:load_flows` | `_h_load_flows` |
| `kernel:flow.compose` | `_h_flow_compose` |
| `kernel:security.init` | `_h_security_init` |
| `kernel:docker.check` | `_h_docker_check` |
| `kernel:approval.init` | `_h_approval_init` |
| `kernel:approval.scan` | `_h_approval_scan` |
| `kernel:container.init` | `_h_container_init` |
| `kernel:privilege.init` | `_h_privilege_init` |
| `kernel:api.init` | `_h_api_init` |
| `kernel:container.start_approved` | `_h_container_start_approved` |
| `kernel:component.discover` | `_h_component_discover` |
| `kernel:component.load` | `_h_component_load` |
| `kernel:emit` | `_h_emit` |
| `kernel:startup.failed` | `_h_startup_failed` |
| `kernel:vocab.load` | `_h_vocab_load` |
| `kernel:noop` | `_h_noop` |

### kernel_handlers_runtime.py（KernelRuntimeHandlersMixin）— 運用/実行系（37キー）

| ハンドラキー | メソッド |
|-------------|---------|
| `kernel:flow.load_all` | `_h_flow_load_all` |
| `kernel:flow.execute_by_id` | `_h_flow_execute_by_id` |
| `kernel:python_file_call` | `_h_python_file_call` |
| `kernel:modifier.load_all` | `_h_modifier_load_all` |
| `kernel:modifier.apply` | `_h_modifier_apply` |
| `kernel:network.grant` | `_h_network_grant` |
| `kernel:network.revoke` | `_h_network_revoke` |
| `kernel:network.check` | `_h_network_check` |
| `kernel:network.list` | `_h_network_list` |
| `kernel:egress_proxy.start` | `_h_egress_proxy_start` |
| `kernel:egress_proxy.stop` | `_h_egress_proxy_stop` |
| `kernel:egress_proxy.status` | `_h_egress_proxy_status` |
| `kernel:lib.process_all` | `_h_lib_process_all` |
| `kernel:lib.check` | `_h_lib_check` |
| `kernel:lib.execute` | `_h_lib_execute` |
| `kernel:lib.clear_record` | `_h_lib_clear_record` |
| `kernel:lib.list_records` | `_h_lib_list_records` |
| `kernel:audit.query` | `_h_audit_query` |
| `kernel:audit.summary` | `_h_audit_summary` |
| `kernel:audit.flush` | `_h_audit_flush` |
| `kernel:vocab.list_groups` | `_h_vocab_list_groups` |
| `kernel:vocab.list_converters` | `_h_vocab_list_converters` |
| `kernel:vocab.summary` | `_h_vocab_summary` |
| `kernel:vocab.convert` | `_h_vocab_convert` |
| `kernel:shared_dict.resolve` | `_h_shared_dict_resolve` |
| `kernel:shared_dict.propose` | `_h_shared_dict_propose` |
| `kernel:shared_dict.explain` | `_h_shared_dict_explain` |
| `kernel:shared_dict.list` | `_h_shared_dict_list` |
| `kernel:shared_dict.remove` | `_h_shared_dict_remove` |
| `kernel:uds_proxy.init` | `_h_uds_proxy_init` |
| `kernel:uds_proxy.ensure_socket` | `_h_uds_proxy_ensure_socket` |
| `kernel:uds_proxy.stop` | `_h_uds_proxy_stop` |
| `kernel:uds_proxy.stop_all` | `_h_uds_proxy_stop_all` |
| `kernel:uds_proxy.status` | `_h_uds_proxy_status` |
| `kernel:capability_proxy.init` | `_h_capability_proxy_init` |
| `kernel:capability_proxy.status` | `_h_capability_proxy_status` |
| `kernel:capability_proxy.stop_all` | `_h_capability_proxy_stop_all` |

runtime内ヘルパー:

| メソッド/関数 | 説明 |
|-------------|------|
| `_record_skipped_flows_to_diagnostics` | スキップFlow記録（B4） |
| `_record_skipped_modifiers_to_diagnostics` | スキップmodifier記録（B4） |
| `_convert_new_flow_to_legacy` | FlowDefinition→legacy形式変換 |
| `_is_diagnostics_verbose()` | モジュールレベル関数（verbose判定） |

## import互換

### 維持される import

```python
from core_runtime.kernel import Kernel          # ✓ 動く
from core_runtime.kernel import KernelConfig    # ✓ re-export済み
from core_runtime.kernel import _is_diagnostics_verbose  # ✓ 互換関数あり
```

### 循環import防止ルール

- `kernel_core.py` は `kernel_handlers_*` を import しない
- `kernel_handlers_*` は `KernelCore` や `Kernel` を import しない
- `kernel.py` だけが3つを import して合成する

## ハンドラ登録漏れ検知

`kernel.py` に `_EXPECTED_HANDLER_KEYS`（全66キーの frozenset）を定義し、`_init_kernel_handlers` 実行後に差分チェックを行う。漏れがあった場合は diagnostics に warning を記録する（起動は止めない）。

## 手動テスト手順

```bash
# 1. import確認
python -c "from core_runtime.kernel import Kernel, KernelConfig; print('OK')"

# 2. インスタンス生成 + ハンドラ数確認
python -c "
from core_runtime.kernel import Kernel
k = Kernel()
print(f'handlers={len(k._kernel_handlers)}')
assert len(k._kernel_handlers) == 66
"

# 3. 主要ハンドラ解決確認
python -c "
from core_runtime.kernel import Kernel
k = Kernel()
for key in ['kernel:flow.load_all', 'kernel:python_file_call',
            'kernel:uds_proxy.status', 'kernel:capability_proxy.status',
            'kernel:audit.summary']:
    assert k._kernel_handlers.get(key) is not None, f'FAIL: {key}'
print('OK')
"

# 4. run_startup実行確認
python -c "
from core_runtime.kernel import Kernel
k = Kernel()
result = k.run_startup()
print(f'events={result.get(\"event_count\", \"?\")}')
"
```

## Done条件チェックリスト

- [ ] `from core_runtime.kernel import Kernel, KernelConfig` が動く
- [ ] `Kernel().run_startup()` が動く
- [ ] 全66ハンドラキーが登録される
- [ ] `kernel:flow.load_all` が呼べる
- [ ] `kernel:python_file_call` が呼べる
- [ ] `kernel:uds_proxy.status` が呼べる
- [ ] `kernel:capability_proxy.status` が呼べる
- [ ] `kernel:audit.summary` が呼べる
- [ ] kernel.py の行数が大幅に減っている（2863→~130）