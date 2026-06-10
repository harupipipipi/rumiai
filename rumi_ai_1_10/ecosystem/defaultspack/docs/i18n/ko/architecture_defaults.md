<!-- docs-i18n-links:start -->
[EN](../../architecture_defaults.md) | [JP](../ja/architecture_defaults.md) | [KR](./architecture_defaults.md) | [CN](../zh-cn/architecture_defaults.md)
<!-- docs-i18n-links:end -->

# 기본 아키텍처 설계 문서

## 1. 기본값은 무엇인가요?

defaults는 루미아이 설치시 자동으로 설치되는 베이스팩입니다. rumiai 자체는 도메인 지식이 없는 범용 커널이지만 기본값은 AI 서비스에 필요한 모든 "메커니즘"을 제공합니다.

기본값은 메커니즘만 제공합니다. 메커니즘은 채팅할 수 있는 위치, 에이전트가 이동하는 위치, 도구가 실행되는 위치, 프롬프트가 렌더링되는 위치, UI가 그려지는 위치를 의미합니다. user_data는 이러한 위치에 무엇이 배치되는지 결정합니다.

defaults 자체에는 채팅 화면이 없습니다. 에이전트 정의가 없습니다. 도구로서의 실체가 없습니다. 프롬프트 템플릿이 없습니다. UI 구성 요소가 없습니다. 기본값에는 이를 실행하기 위한 처리기, 권한, 흐름, 도메인 코드 및 통신 계층이 있습니다.

## 2. 디자인 원칙

### 메커니즘만 제공하고 모든 내용은 user_data입니다.

기본값은 무엇을 하는지가 아니라 무엇을 할 수 있는지를 정의합니다.

handler는 도메인 작업을 위한 실행 플랫폼입니다. `defaults.chat.send`은 "메시지 전송 메커니즘"을 제공합니다. 호출자(도구, 흐름, 팩)는 어떤 대화에 무엇을 보낼지 결정합니다.

권한 카탈로그는 작업을 위한 권한 시스템입니다. `chat.message.send`에서는 '메시지 전송이 허용될 수 있음'을 정의합니다. 허가는 누가 허가를 받을지 결정합니다.

흐름은 처리 파이프라인의 실행 기반입니다. `simple_chat` Flow는 "사용자 입력 → 컨텍스트 구성 → LLM 호출 → 응답 저장"의 프레임워크를 제공합니다. Flow의 config 및 user_data 설정은 사용할 모델과 적용할 프롬프트를 결정합니다.

프런트 엔드는 그리기 위한 프레임을 제공합니다. shell.html은 슬롯(메인, 사이드바, 패널 등)을 정의하는 빈 상자입니다. 어떤 슬롯에 무엇을 그릴지는 Asset으로 등록된 내용에 따라 결정됩니다.

### 배터리가 포함되어 있지만 모든 배터리는 분리 가능합니다.

기본값을 포함하면 AI 서비스에 필요한 모든 메커니즘이 작동합니다. 그러나 모든 메커니즘은 다른 팩으로 교체할 수 있습니다. 핸들러를 동일한 이름으로 덮어쓸 수 있습니다. 흐름은 교체로 대체될 수 있습니다. 권한은 확장 가능합니다. 프런트엔드 자산은 동일한 ID로 덮어쓸 수 있습니다.

### 기본값은 한계가 아닌 표준을 정의합니다

기본적으로 정의된 권한, 핸들러, 도메인 모델, 위젯 유형, 자산 형식은 루미아이 생태계의 표준 어휘가 됩니다. 다른 팩에서는 이 용어를 사용합니다. 그러나 이 어휘는 확장 가능하며 다른 팩은 기본값이 모르는 권한 도메인, 모르는 핸들러 카테고리 및 모르는 위젯 유형을 추가할 수 있습니다.

### 모든 것을 알고 아무것도 가정하지 마세요

기본값은 AI 서비스(채팅, 에이전트, 도구, 프롬프트, AI 클라이언트, 코딩, 메모리, 미디어)에 필요한 모든 도메인 지식을 알고 있습니다. 그러나 사용자의 환경, 사용 사례 또는 선호도에 대해 어떠한 가정도 하지 않습니다. 모든 것을 구성할 수 있으며 모든 것을 덮어쓸 수 있습니다.

### 신뢰가 아닌 능력에 의한 보안

기본값 자체는 rumiai의 승인 프로세스를 따릅니다. 기본 코드는 SHA-256 해시 검증을 통해 승인되며 부여된 권한 범위 내에서만 작동합니다. 기본값은 특별히 취급되지 않습니다.

### 전문화 금지

기본값은 특정 사용 사례에 특화된 메커니즘을 생성하지 않습니다. 멀티 에이전트 전용 API, 지식 검색 전용 API, 스케줄러 전용 API를 생성하지 마세요. 범용 프리미티브(핸들러 호출, 이벤트 발행, 데이터 읽기/쓰기, 흐름 실행)를 제공하고 이들의 조합으로 인해 모든 사용 사례가 실현될 수 있습니다.

## 3. 아키텍처

```
rumiai (コンパイル済みバイナリ)
│   カーネル: Flow 実行, 承認ゲート, Docker 隔離, Trust + Grant, 監査ログ
│
├── ecosystem/defaults/          ← 仕組みを提供
│     ├── handlers/              ← handler（ドメイン操作の実行基盤）
│     ├── flows/                 ← Flow（処理パイプラインの骨格）
│     ├── domain/                ← ドメインコード（chat, agent, tool 等の内部ロジック）
│     ├── transport/             ← 通信レイヤー（http, stdio, uds）
│     ├── bridge/                ← カーネル context ラッパー
│     ├── ui/
│     │     └── shell.html       ← フロントエンドの空の枠（スロット + Widget レンダラー）
│     ├── lib/
│     │     └── rumi_widgets/    ← Widget Python ヘルパー
│     └── docs/                  ← 設計ドキュメント
│
└── user_data/                   ← 中身を提供
      ├── shared/
      │     ├── tools/           ← ツール定義（handler.py + schema.json + ...）
      │     ├── agents/          ← エージェント定義（agent.json）
      │     ├── prompts/         ← プロンプト定義
      │     ├── ai_models/       ← AI モデルプロファイル
      │     └── flows/           ← ユーザー定義 Flow
      ├── packs/                 ← インストールされたパック
      │     └── {pack_id}/
      │           ├── tools/
      │           ├── agents/
      │           ├── prompts/
      │           ├── assets/    ← UI Asset（*.asset.yaml + HTML/JS）
      │           └── flows/
      ├── chat/                  ← 会話データ
      ├── memory/                ← ユーザーメモリ
      ├── config.json            ← 全体設定
      ├── layout/                ← レイアウト設定
      └── themes/                ← テーマ
```

### 기본값은 무엇입니까?

핸들러(58개). 카테고리: 채팅, 에이전트, 도구, 프롬프트, AI, 코딩, 메모리, 미디어, 프론트엔드. 모든 핸들러는 범용 작업 플랫폼이며 해당 내용에 대한 구체적인 지식이 없습니다.

흐름(3개). simple_chat, 에이전트_채팅, 계획_에이전트. 처리 파이프라인의 뼈대만 정의하고 특정 모델 선택과 프롬프트 적용을 Flow 구성 및 user_data에 위임합니다.

권리 카탈로그(20개 도메인). 채팅, 에이전트, 도구, 프롬프트, AI, 파일, 터미널, Git, 메모리, 미디어, 흐름, 구성, 넷, 프런트엔드, 이벤트, 감사, 팩, 비밀, 커널. 모든 팩에 사용되는 표준 어휘입니다.

도메인 코드. 채팅 저장소, 에이전트 루프, 도구 실행기, 프롬프트 렌더러, ai_client, 컨텍스트 빌더 등과 같은 내부 논리. 이들은 핸들러에서 호출되며 외부 세계에 직접 노출되지 않습니다.

프런트 엔드 프레임. shell.html(슬롯 정의 + 자산 로더 + 위젯 렌더러 + 메시지 디스패치). 특정 UI 구성 요소가 없습니다.

통신층. 세 가지 전송: http, stdio 및 uds. 설정에서 사용할 것을 선택하세요.

위젯 도우미 라이브러리. 루미_위젯. 위젯 JSON을 구성하기 위한 백엔드 핸들러 및 도구를 위한 Python 도우미입니다. 사용법은 선택 사항이며 dict를 직접 반환하는 것과 동일합니다.

### 기본값에 없는 것

특정 UI 구성요소(채팅 화면, 에이전트 패널, 코드 편집기 등) 이는 user_data 팩에서 자산으로 제공됩니다.

특정 도구 정의(file_read, bash, web_search 등). 이는 user_data/shared/tools/에 있습니다.

특정 에이전트 정의(coding_assistant, Research_agent 등). 이는 user_data/shared/agents/에 있습니다.

특정 프롬프트 템플릿. 이는 user_data/shared/prompts/에 있습니다.

특정 AI 모델 프로필. 이는 user_data/shared/ai_models/에 있습니다.

테마 정의. 이는 user_data/themes/에 위치합니다.

레이아웃 정의. 이는 user_data/layout/에 위치합니다.

## 4. 도구 컨텍스트 API

도구는 기본적으로 제공되는 메커니즘의 가장 중요한 소비자입니다. 도구의 handler.py에 주입된 컨텍스트 API는 범용 프리미티브로만 구성됩니다. 도메인별 API는 없습니다.

### 항상 주입됨(선언 필요 없음)

`context["call_handler"](§RUMI§0§)`은 모든 핸들러를 호출합니다. Grant가 부여한 권한 범위 내에서만 실행할 수 있습니다. 호출자에게 호출된 핸들러가 요청한 권한이 없으면 PermissionError와 함께 거부됩니다. 이를 통해 도구는 동일한 기본 요소를 사용하여 채팅 작업, 에이전트 시작, 프롬프트 렌더링, 메모리 읽기 및 쓰기를 모두 수행할 수 있습니다.

`context["emit_event"](§RUMI§0§)`에서 이벤트를 게시합니다. 다른 핸들러, Flow 이벤트 트리거 및 프런트엔드 자산이 이 이벤트를 수신할 수 있습니다. 발급자는 수신자를 알지 못합니다.

`context["wait_event"](§RUMI§0§)`은 이벤트를 기다립니다. 지정된 이벤트 유형이 실행될 때까지 차단됩니다. 시간 초과를 지정할 수 있습니다. 필터를 사용하여 조건의 범위를 좁힐 수 있습니다. Emit_event와 결합하여 프런트 엔드에 팝업 표시 → 사용자 응답 대기, 도구 간 비동기 통신, Flow 트리거 Hooking 등이 모두 구현됩니다.

`context["emit_widget"](§RUMI§0§)`은 위젯 JSON을 UI로 보냅니다. 프런트엔드 위젯 렌더러에 의해 그려집니다.

`context["cancel_check"]()`은 취소 확인입니다. 사용자가 취소하면 CancelledError가 발생합니다.

`context["handler_config"]`은 Conditions.json의 Behavior_variants에서 주입된 설정입니다.

`context["session"]`은 세션 정보(session_id, 작업 공간 등)입니다.

### 이를 기능으로 선언하여 주입되는 내용

`data_read`은 user_data 아래의 파일을 읽습니다. `context["data_read"](§RUMI§0§)`를 통해 액세스합니다. 경로는 user_data/를 기준으로 합니다.

`data_write`은 user_data 아래에 파일을 씁니다. `context["data_write"](§RUMI§0§)`를 통해 액세스합니다.

`execute_flow`이 Flow를 시작합니다. `context["execute_flow"](§RUMI§0§)`를 통해 액세스합니다. Flow Engine을 통해 실행됩니다.

`shell_exec`은 쉘 명령을 실행합니다. `context["capability"](§RUMI§0§)`를 통해 액세스합니다.

`browser_control`은 브라우저 작업입니다. `context["capability"](§RUMI§0§)`를 통해 액세스합니다.

`container_exec`은 Docker 컨테이너를 시작, 작동 및 파괴합니다. `context["capability"](§RUMI§0§)`를 통해 액세스합니다. GUI 환경(Xvfb + VNC)은 디스플레이 옵션으로 시작되며, 스크린샷 및 입력(클릭, 타이핑, 키, 스크롤)으로 좌표 기반의 화면 조작이 가능합니다.

`app_control`은 호스트 애플리케이션 작업입니다. `context["capability"](§RUMI§0§)`를 통해 액세스합니다.

`http_request`은 외부 HTTP 통신입니다. `context["capability"](§RUMI§0§)`를 통해 액세스합니다.

`llm_call`은 도구 내 LLM 통화입니다. `context["capability"](§RUMI§0§)`를 통해 액세스합니다.

`session_state`은 세션 상태 읽기/쓰기입니다. `context["capability"](§RUMI§0§)`를 통해 액세스합니다.

### 특화된 API를 만들어보면 어떨까요?

`context["chat"]` 또는 `context["agent"]`과 같은 도메인별 API를 생성하는 경우 새 도메인이 추가될 때마다 컨텍스트 API를 확장해야 합니다. 이는 "전문화 없음"이라는 기본 디자인 원칙을 위반합니다.

대신 `call_handler`이라는 단일 범용 게이트웨이를 제공합니다. 채팅 작업은 `call_handler("defaults.chat.send", {...})`을 사용하여 수행됩니다. 에이전트는 `call_handler("defaults.agent.execute", {...})`를 사용하여 시작됩니다. 새 팩이 새 처리기를 정의하는 경우 도구는 동일한 `call_handler`을 사용하여 이를 호출할 수 있습니다. 컨텍스트 API를 변경할 필요가 없습니다.

마찬가지로 프런트 엔드에 대한 알림, 사용자에게 확인, 주기적 실행 등록은 모두 `emit_event` / `wait_event` / `execute_flow`의 범용 프리미티브를 사용하여 구현됩니다. 이러한 기본 요소 자체는 거의 변경되지 않으며 그 위에 있는 핸들러와 흐름은 확장됩니다.

## 5. 프런트엔드 작동 방식

### 기본값이 제공하는 것

shell.html만 가능합니다. shell.html은 다음 기능을 포함하는 빈 상자입니다.

슬롯 정의. header, sidebar.left, main, panel.bottom, sidebar.right, statusbar 및 Floating의 7개 슬롯을 정의합니다. 슬롯은 자산이 배치되는 곳입니다. 슬롯 자체는 아무것도 그리지 않습니다.

자산 로더. `asset.register` 메시지가 수신되면 iframe을 사용하여 자산의 HTML 파일을 로드하고 지정된 슬롯에 배치합니다. Asset이 무엇인지 모르겠습니다(채팅 화면, 파일 트리, 대시보드).

위젯 렌더러. 백엔드에서 전송된 Widget JSON을 받아 테마에 맞게 HTML로 변환합니다. 각 위젯 유형(Text, CodeBlock, Image 등)에는 렌더링 로직이 있습니다. 테마는 위젯의 모양을 결정합니다.

메시지 발송. `asset_id`을 사용하여 백엔드에서 메시지를 정렬하고 해당 iframe으로 전달합니다. iframe에서 백엔드로 메시지를 전달합니다. 데이터의 내용은 해석되지 않습니다.

### 제공되지 않는 기본값

채팅 화면용 HTML/JS/CSS. 에이전트 패널의 HTML/JS/CSS. 코드 편집기 HTML/JS/CSS. 설정 화면용 HTML/JS/CSS. 이들 모두는 user_data 팩에서 자산으로 제공됩니다.

### 자산 등록 형식

자산은 UI에 배치되는 블록 단위입니다. 자산은 Asset.yaml(메타데이터), HTML/JS 파일(WebView에서 그린 UI) 및 핸들러(백엔드에서 메시지를 처리하는 Python)로 구성됩니다.

```yaml
asset_id: "my_pack.chat.messages"
name: "Chat Messages"
entry: "ui/chat/messages.html"
handler: "components/chat_messages.py"
permissions:
  - chat.message.send
  - chat.message.read
  - ai.model.list
placement:
  slot: "main"
  priority: 100
category: "chat"
tags: ["chat", "messages"]
extensions: {}
```

자산은 user_data/packs/{pack_id}/assets/에 배치됩니다. 팩이 승인되면 자산이 자동으로 프런트 엔드에 등록됩니다. 기본값에 대한 코드 변경은 없습니다.

동일한 자산 ID로 등록하면 덮어쓰게 됩니다. 이를 통해 다른 팩이 기본 팩(또는 다른 팩)의 자산을 대체할 수 있습니다.

### 위젯

위젯은 백엔드가 "이 데이터를 표시하는 방법은 다음과 같습니다."라고 선언할 수 있는 통합 기본 요소입니다. 도구, 프롬프트, ai_client, 채팅, 에이전트는 모두 동일한 위젯 시스템을 사용합니다. 위젯은 순수 데이터(JSON)이며 UI 라이브러리가 아닙니다. 프런트엔드의 shell.html에 있는 위젯 렌더러는 이 JSON을 수신하고 실제로 테마에 따라 그립니다.

위젯 유형은 표시 유형(14가지: Text, CodeBlock, Diff, Image, Screenshot, Progress, Terminal, Table, Chart, FileTree, Markdown, Audio, Video, Map), 컨트롤 유형(Input, Button, Select, Toggle, Slider, Checkbox)이 있습니다. 총 29가지 유형: 레이아웃 유형(6가지 유형: 컨테이너, 행, 열, 탭, 축소 가능, 카드), 스트리밍 유형(2가지 유형: 스트림, 표시기), 사용자 정의(1가지 유형: 사용자 정의).

위젯의 자세한 사양은 docs/widget.md에 정의되어 있습니다.

## 6. user_data로 모든 것을 구현하는 예시

다음은 모두 user_data의 도구, 에이전트, 흐름 및 자산으로 구현됩니다. 기본값은 메커니즘만 제공하며 특정 구현 코드는 없습니다.

### 지식 검색

user_data/shared/tools/knowledge_search/에 벡터 검색 도구를 배치하세요. user_data/shared/flows/에 Flow Modifier를 배치하고 user_input이 도착할 때 이 도구를 자동으로 실행하는 단계를 삽입합니다. 도구 handler.py는 `context["capability"](§RUMI§0§)`에 임베딩을 생성하고 `context["data_read"]`의 인덱스를 읽고 결과를 반환합니다. 기본값은 0으로 변경됩니다.

### 다중 에이전트

user_data/shared/tools/agent_delegate/에 에이전트 위임 도구를 배치하세요. 도구 handler.py는 `context["call_handler"](§RUMI§0§)`에서 새 대화를 생성하고, `context["call_handler"](§RUMI§1§)`에서 에이전트를 시작하고, 결과를 수신하고 반환합니다. 조직 구조가 필요한 경우 user_data/shared/agents/에 여러 개의 agent.json 파일을 배치하면 위임 도구가 적절한 에이전트를 선택합니다. 기본값은 0으로 변경됩니다.

### AI로 대화 내용 자체 편집

user_data/shared/tools/history_prune/에 기록 편집 도구를 배치합니다. 도구 handler.py는 `context["call_handler"](§RUMI§0§)`에서 메시지를 검색하고 `context["data_write"]`에서 대화 파일을 업데이트합니다. Agent.json의 tools.enabled에 이 도구를 추가하면 에이전트가 자신의 기록을 자율적으로 구성할 수 있습니다. 기본값은 0으로 변경됩니다.

### Linux 환경에서 GUI 동작

user_data/shared/tools/linux_env/에 환경 조작 도구를 배치합니다. 도구 handler.py는 `context["capability"](§RUMI§0§)`으로 컨테이너를 시작하고 스크린샷 및 입력 작업으로 화면을 작동합니다. Agent.json의 모델 설정을 이용하여 동작할 모델을 선택합니다. 기본값은 0으로 변경됩니다.

### 동의 팝업

user_data/shared/tools/consent_check/에 동의 확인 도구를 배치하세요. 도구 handler.py는 `context["emit_event"](§RUMI§0§)`에 팝업을 표시하고 `context["wait_event"](§RUMI§1§)`에서 사용자의 응답을 기다립니다. 이를 Agent.json의 tools.enabled에 추가하고 에이전트의 시스템 프롬프트에 "투자 조언에 적용 가능한 경우 이 도구를 사용하십시오."라고 지시합니다. 기본값은 변경되지 않습니다.

### 정규 실행

user_data/shared/flows/에 일정 트리거가 있는 흐름을 배치합니다. Flow의 Trigger.type을 "schedule"로 설정하고 Trigger.config.cron을 "*/30 * * * *"로 설정합니다. Flow의 handler.py는 `ctx.call_block("agent.run", {...})`으로 에이전트를 시작합니다. 기본값은 0으로 변경됩니다.

### 청구/신용 관리

user_data/shared/tools/billing_check/에 사용량 확인 도구를 배치하세요. 도구 handler.py는 `context["call_handler"](§RUMI§0§)`에서 사용량을 가져오고, `context["data_read"](§RUMI§1§)`에서 계획 정의를 읽고 남은 크레딧을 계산하여 반환합니다. UI 표시가 필요한 경우 user_data/packs/에 청구 자산이 포함된 팩을 배치하세요. 기본값은 0으로 변경됩니다.

## 7. 기본 파일 구조

```
ecosystem/defaults/
├── README.md                      # 権限カタログ + handler 体系
├── handlers/
│     └── frontend.py              # 通信ブリッジ handler（ホスト実行）
├── flows/
│     ├── simple_chat/
│     │     ├── flow.yaml
│     │     └── handler.py
│     ├── agent_chat/
│     │     ├── flow.yaml
│     │     └── handler.py
│     └── planning_agent/
│           ├── flow.yaml
│           └── handler.py
├── domain/
│     ├── chat/                    # 会話データの永続化・変換
│     ├── agent/                   # エージェントループ・コンテキスト管理
│     ├── tool/                    # ツール実行・権限検証・MCP
│     ├── prompt/                  # テンプレートレンダリング
│     ├── ai_client/               # LLM 通信・プロバイダ抽象化
│     ├── coding/                  # ファイル操作・ターミナル・Git
│     ├── memory/                  # メモリ管理・ベクトルストア
│     └── media/                   # マルチモーダル処理
├── transport/
│     ├── http/                    # HTTP 通信
│     ├── stdio/                   # 標準入出力通信
│     └── uds/                     # Unix ドメインソケット通信
├── bridge/                        # カーネル context ラッパー
├── ui/
│     └── shell.html               # 空の枠（スロット + Asset ローダー + Widget レンダラー）
├── lib/
│     └── rumi_widgets/            # Widget Python ヘルパー
│           ├── __init__.py
│           ├── display.py
│           ├── controls.py
│           ├── layout.py
│           ├── stream.py
│           └── custom.py
└── docs/
      ├── architecture_defaults.md
      ├── agent.md
      ├── ai_client.md
      ├── chat.md
      ├── flow.md
      ├── prompt.md
      ├── tool.md
      ├── frontend.md
      ├── widget.md
      ├── theme.md
      ├── api.md
      ├── profiles_and_models.md
      ├── conflict_resolution.md
      ├── ui_and_layout.md
      └── capability/
            └── dependency-resolution.md
```

## 8. 기본적으로 제공되는 핸들러 목록

핸들러 58명. 모든 핸들러는 범용 작업 기지이며 `call_handler` 도구에서 호출할 수 있습니다. 자세한 내용은 README.md에 정의되어 있습니다.

프론트엔드(3개): 시작, 중지, 방출.

채팅(8): 전송, 스트림, create_conversation, list_conversations, 분기, 검색, 중지, 재생성.

에이전트(6개) : 실행, 승인, 거부, 취소, 상태, 계획.

코딩(12개): file_read, file_write, file_create, file_delete, file_search, file_list, 터미널_exec, 터미널_스트림, git_status, git_diff, git_commit, git_push.

ai(9개): 완료, 스트림, 모델, 공급자, 삽입, image_gen, image_analyze, Transcribe, tts.

도구(5개): 호출, 목록, 스키마, mcp_connect, mcp_list.

프롬프트 (4): 렌더링, 목록, 생성, 시스템.

메모리(5개): 저장, 회수, 프로젝트_컨텍스트, 벡터_저장, 벡터_쿼리.

미디어(6개): image_read, image_transform, doc_parse, 클립보드_read, 클립보드_쓰기, 스크린샷.

## 9. 다른 문서와의 관계

이 문서는 기본값의 전체 그림을 정의합니다. 각 도메인의 세부 설계는 다음 문서에 설명되어 있습니다.

Agent.md는 에이전트 루프, Agent.json 사양, 컨텍스트 관리, 하위 에이전트 및 계획 세부 정보를 정의합니다.

ai_client.md는 LLM 통신, 공급자 추상화, 이중 장벽 변환 및 StandardMessage/StandardResponse 사양을 정의합니다.

chat.md는 대화 데이터 형식, RumiMessage 스키마, 대화 분기 및 저장 API를 정의합니다.

flow.md는 Flow Engine, handler.py 사양, 노드 그래프, 트리거 시스템 및 블록 계약을 정의합니다.

프롬프트.md는 프롬프트 템플릿, 변수 확장 및 Python 확장을 정의합니다.

tool.md는 도구 정의 형식, 컨텍스트 API, 점진적 공개, MCP 지원 및 팩 조정을 정의합니다.

frontend.md는 프런트엔드 아키텍처, 자산 형식, 통신 프로토콜 및 슬롯 모델을 정의합니다.

widget.md는 위젯 유형 목록, JSON 형식 및 테마 조정을 정의합니다.

theme.md는 테마 구조, 토큰, 애니메이션 및 위젯 그리기 스타일을 정의합니다.
