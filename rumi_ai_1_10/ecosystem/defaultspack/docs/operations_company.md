# Operations Company

Operations Company は `defaultspack.operations_company` profile で動く常駐エージェント組織です。PR56 では固定ロールの bootstrap に加えて、Agent Factory / lifecycle / browser / computer / approval / API key resolver を接続します。

## 起動と標準 agent

`OperationsCompanyRuntime.bootstrap()` は既存の organization conversation と Client Manager conversation を維持しながら、次の 7 agent を `AgentStore` に保存します。

| agent_id | role |
|---|---|
| `client_manager` | ユーザー窓口と通知 |
| `project_manager` | タスク分解と進行 |
| `coding_engineer` | 実装 |
| `research_specialist` | 調査 |
| `reviewer` | レビュー |
| `operations_monitor` | heartbeat / incident |
| `scheduler` | schedule coordination |

標準 agent は role definition から `AgentDefinition` に変換されます。これにより固定 Operations Company と任意作成 agent が同じ runtime / policy / key resolver を使います。

## Heartbeat

Heartbeat は scheduler から直接 chat を呼ぶのではなく、`AgentRuntime.tick("operations_monitor")` に寄せます。tick は lifecycle guard を通して、budget / rate / stop condition / blocker を評価し、通常 tick は run history に保存します。

`normal_status_silent: true` の場合、変化のない tick は Client Manager へ通知しません。incident、blocked、approval required、completed は通知対象です。

## Routes

Operations panel から主に次の API を使います。

| method | path | purpose |
|---|---|---|
| `GET` | `/api/operations-company/status` | manifest / runtime status |
| `POST` | `/api/operations-company/bootstrap` | organization と標準 agent を作成 |
| `GET` | `/api/agents` | agent 一覧 |
| `POST` | `/api/agents/{agent_id}/tick` | agent tick |
| `GET` | `/api/approvals` | pending approvals |

## Safety

Browser / computer / external send / key mutation は central approval と policy resolver を通ります。client body の `approved: true` は信頼せず、server-side approval store の decision だけを使います。
