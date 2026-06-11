<!-- docs-i18n-links:start -->
[EN](../../architecture.md) | [JP](../ja/architecture.md) | [KR](./architecture.md) | [CN](../zh-cn/architecture.md)
<!-- docs-i18n-links:end -->

# 건축

기본 팩 아키텍처를 설명합니다.

## 큰 그림: 커널 ⇔ 기본 팩 관계

rumiai 커널은 전체 생태계를 관리하는 핵심 런타임입니다. 기본 팩은 커널에 등록되어 채팅, 에이전트, 코딩, AI 클라이언트, 도구, 프롬프트, 메모리, 미디어, 프런트 엔드 및 개발 도구에 대한 기능을 제공하는 표준 애플리케이션 팩입니다.

커널은 Pack의 구조를 이해하기 위해 `ecosystem.json`을 읽고 각 핸들러를 확인하고 호출합니다. 기본 팩은 커널의 `KernelFacade`을 사용하여 인터페이스(`get_interface`), 이벤트 발생(`emit`) 및 다른 팩의 호출 핸들러를 가져옵니다.

```
┌──────────────────────────────────────────────────┐
│                  rumiai カーネル                    │
│                                                    │
│  KernelFacade                                      │
│    ├── io.http.server (HTTP サーバー起動)            │
│    ├── get_interface(name) → Interface              │
│    ├── emit(event_type, data)                       │
│    ├── call_handler(handler_name, params)            │
│    └── list_interfaces()                            │
│                                                    │
│  InterfaceRegistry ── EventBus                      │
│       ↑                    ↑                        │
└───────┼────────────────────┼────────────────────────┘
        │                    │
        ▼                    ▼
┌──────────────────────────────────────────────────┐
│              defaults Pack                         │
│                                                    │
│  transport/http.py  ←  HTTP リクエスト受信           │
│       │                                            │
│       ▼                                            │
│  blocks/  ←  handler（def run(input_data, context)） │
│       │                                            │
│       ▼                                            │
│  domain/  ←  ビジネスロジック                        │
│       │                                            │
│       ▼                                            │
│  外部 API（AI プロバイダー等）                       │
└──────────────────────────────────────────────────┘
```

## 레이어 구성

기본 팩은 4개의 레이어로 구성됩니다.

**전송 계층**(`transport/`)은 외부로부터의 요청을 받아들입니다. `transport/http.py`의 `DefaultsHttpServer` 클래스는 라우팅을 수행하고 URL 경로 및 HTTP 메서드를 기반으로 적절한 핸들러를 호출합니다. `transport/stdio.py` 및 `transport/uds.py`는 각각 표준 입력/출력 및 Unix 도메인 소켓 전송을 제공합니다.**블록 레이어**(`blocks/`)는 핸들러 모음입니다. 각 핸들러에는 `def run(input_data, context)` 서명이 있고, `input_data`(dict)에서 요청 매개변수를 받고, `context`(dict)에서 흐름 정보와 `call_handler` 기능을 받습니다. 핸들러는 도메인 레이어의 로직을 호출하고 `ok(data)` 또는 `error(message, code)` 형식으로 결과를 반환합니다.**도메인 레이어**(`domain/`)는 비즈니스 로직을 구현합니다. `domain/chat/store.py`(ChatStore), `domain/agent/engine.py`(AgentEngine), `domain/tool/registry.py`(ToolRegistry), `domain/prompt/manager.py`(PromptManager) 등이 포함됩니다. 핸들러는 도메인 레이어 클래스를 직접 가져와서 사용합니다.**외부 API 레이어**는 `domain/ai_client/`를 통해 AI 제공업체(OpenAI, Anthropic 등)와 통신합니다.

## 제공업체에 구애받지 않는 채팅 IR

defaultspack 채팅 스택은 Rumi Chat IR v2를 내부 표현으로 사용합니다.
공급자 중립 ChatStore 레코드와 공급자별 API 페이로드 사이.
ChatStore는 공급자별 요청 없이 Rumi 메시지를 계속 저장합니다.
상태. IR 계층은 메시지 ID, 상위/하위 링크, 시퀀스 번호,
메타데이터, 다중 모드 블록, 도구 호출/결과, 추론 블록 및 알 수 없음
블록.

공급자 실행은 작은 단계로 나뉩니다.

- `domain/chat/ir*.py`: Rumi Chat IR v2 데이터 클래스, 직렬화,
  검증 및 레거시 어댑터.
- `domain/ai_client/capabilities/`: 제공자 기능이 드러나고 특이합니다.
- `domain/ai_client/request_planner.py`: 성능 저하 계획, 경고,
  삭제된 기능, 브리지 작업 및 도구 이름 별칭.
- `domain/ai_client/provider_compiler/`: OpenAI 채팅, OpenAI 응답,
  OpenAI 호환, Google OpenAI, Google 네이티브, Anthropic Messages, Bedrock
  Converse 및 로컬 OpenAI 호환 페이로드 컴파일러/파서.
- `domain/tool/protocol.py`: 공급자 독립적인 도구 정의, 공급자
  별칭, 호출 및 결과.
- `domain/chat/attachments/`: 텍스트에 대한 첨부 기록 및 표현,
  인라인 데이터 URL, 이미지 페이지, PDF 텍스트, 스크립트 및 공급자 파일 ID.
- `domain/ai_client/provider_trace.py`: 디버깅을 위해 수정된 추적 아티팩트
  공급자 계획 및 페이로드.

레거시 StandardMessage 경로는 다음을 제외하고 기본 런타임 경로로 유지됩니다.
`RUMI_DEFAULTSPACK_PROVIDER_COMPILER_V2=1`이 설정되었습니다. 설정
`RUMI_DEFAULTSPACK_PROVIDER_LEGACY_MESSAGES=1`는 다음과 같은 경우에도 이전 경로를 강제합니다.
컴파일러 플래그가 활성화되었습니다.

## 데이터 흐름

일반적인 요청 처리 흐름은 다음과 같습니다.

HTTP 요청이 `transport/http.py`의 `_RequestHandler`에 도착하면 `_handle_request()` 메서드가 호출됩니다. URL 경로에 해당하는 핸들러 함수는 `_match_route()`에서 확인되고 요청 본문은 JSON으로 구문 분석됩니다. 핸들러 함수는 `_build_context()`에서 컨텍스트를 구성하고 `blocks/` 아래 핸들러의 `run()` 함수를 호출합니다. 핸들러는 도메인 계층 로직을 실행하고 필요에 따라 `call_handler`를 통해 다른 핸들러(예: `defaults.ai.complete`)를 호출합니다. 결과는 `{"status": "ok", "data": ...}` 또는 `{"status": "error", "error": {...}}` 형식의 HTTP 응답으로 반환됩니다.

```
HTTP POST /api/chat/conversations/{id}/messages
    │
    ▼
transport/http.py :: _handle_chat_send_message()
    │  request_data["conversation_id"] = path_params["id"]
    ▼
blocks/chat/send.py :: run(input_data, context)
    │  store = ChatStore()
    │  conv = store.get_conversation(conversation_id)
    │  user_msg = store.add_message(conversation_id, user_msg_dict)
    │  chain = store.get_message_chain(conversation_id, user_msg["id"])
    │  standard_messages = convert_to_standard(chain)
    ▼
context["call_handler"]("defaults.ai.complete", ai_params)
    │
    ▼
blocks/ai/complete.py :: run() → domain/ai_client/client.py
    │
    ▼
外部 AI API（OpenAI, Anthropic, etc.）
    │
    ▼
assistant_msg = store.add_message(conversation_id, assistant_msg_dict)
    │
    ▼
HTTP 200 {"status": "ok", "data": assistant_msg}
```

## 디렉토리 구조와 각 디렉토리의 역할

```
rumiai_defaults/
├── ecosystem.json          Pack 構造定義。カーネルが読み取る。
├── README.md               Pack の概要・設計思想・Grant 一覧
├── blocks/                 handler 群（transport から呼ばれる入口）
│   ├── _common.py          共通ユーティリティ（ok, error, gen_id, timestamp）
│   ├── chat/               チャット関連 handler（18 handler）
│   │   ├── create_conversation.py
│   │   ├── get_conversation.py
│   │   ├── list_conversations.py
│   │   ├── update_conversation.py
│   │   ├── delete_conversation.py
│   │   ├── export_conversation.py
│   │   ├── send.py              メッセージ送信 + AI 応答
│   │   ├── stream.py            ストリーミング送信
│   │   ├── add_message.py       AI なしのメッセージ追加
│   │   ├── get_message.py
│   │   ├── update_message.py
│   │   ├── delete_message.py
│   │   ├── branch.py            会話の分岐
│   │   ├── search.py            メッセージ検索
│   │   ├── stop.py              ストリーミング停止
│   │   ├── regenerate.py        AI 応答の再生成
│   │   ├── summarize_and_trim.py  指定範囲の要約・圧縮
│   │   └── auto_trim.py         AI による自動トリム提案
│   ├── agent/              エージェント関連 handler
│   │   ├── _state.py            実行中エンジンのインメモリ管理
│   │   ├── execute.py           タスク実行
│   │   ├── approve.py           ツール呼び出し承認
│   │   ├── reject.py            ツール呼び出し拒否
│   │   ├── cancel.py            実行キャンセル
│   │   ├── status.py            ステータス確認
│   │   ├── plan.py              計画のみ（実行なし）
│   │   ├── add_instruction.py   実行中の指示追加
│   │   ├── multi_execute.py     マルチエージェント実行
│   │   ├── multi_status.py      マルチエージェントステータス
│   │   └── multi_message.py     マルチエージェントへのメッセージ投入
│   ├── ai/                 AI クライアント handler
│   ├── coding/             コーディング handler（ファイル操作・ターミナル・Git）
│   ├── tool/               ツール handler（CRUD・エクスポート）
│   ├── prompt/             プロンプト handler（CRUD・レンダリング・変換）
│   ├── memory/             メモリ handler
│   ├── media/              メディア handler
│   ├── frontend/           フロントエンド handler（start, stop, emit）
│   └── dev/                開発ツール handler（inspect, replay 等）
├── domain/                 ビジネスロジック層
│   ├── chat/               ChatStore, message_converter, message_builder, exporter
│   ├── agent/              AgentEngine, AgentExecution, AgentDefinition, InstructionQueue
│   ├── company/            CompanySlackRuntime, runtime SQLite store, routing,
│   │                       dispatch, supervisor, summaries
│   ├── ai_client/          AIClient（プロバイダー抽象化）
│   ├── tool/               ToolRegistry, builder
│   ├── prompt/             PromptManager, PromptTemplate, renderer
│   ├── coding/             コーディングドメインロジック
│   ├── memory/             メモリドメインロジック
│   ├── media/              メディアドメインロジック
│   └── dev/                Inspector
├── transport/              トランスポート層
│   ├── http.py             HTTP サーバー（DefaultsHttpServer）
│   ├── stdio.py            標準入出力トランスポート
│   └── uds.py              Unix Domain Socket トランスポート
├── flows/                  Flow 定義
│   ├── simple_chat/        シンプルチャットフロー
│   │   ├── flow.yaml
│   │   └── handler.py
│   ├── agent_chat/         エージェントチャットフロー
│   │   ├── flow.yaml
│   │   └── handler.py
│   └── planning_agent/     計画エージェントフロー
│       ├── flow.yaml
│       └── handler.py
├── ui/                     フロントエンド
│   └── shell.html          メイン UI
├── static/                 静的ファイル配信ディレクトリ
├── lib/                    Widget ライブラリ
│   └── rumi_widgets/
├── bridge/                 context ブリッジ
├── user_data/              ユーザーデータ（永続化先）
│   ├── shared/
│   │   ├── tools/          動的ツール定義（.tool.json + .handler.py）
│   │   ├── agents/         エージェント定義
│   │   ├── prompts/        プロンプト定義（.json）
│   │   └── ai_models/      AI モデル設定
│   ├── assets/             Asset（chat, agent, coding 等）
│   ├── themes/             テーマ定義
│   ├── layouts/            レイアウト定義
│   ├── chat/               チャット永続化データ
│   ├── memory/             メモリ永続化データ
│   └── config.json         設定ファイル
└── docs/                   ドキュメント
```

## Ecosystem.json의 구조와 의미

`ecosystem.json`은 커널이 Pack을 인식하기 위한 구조 정의 파일입니다. 실제 파일 내용을 기준으로 한 구조는 다음과 같습니다.

**`pack_id`**(`"defaults"`)은 팩의 고유 식별자입니다. 핸들러 이름의 첫 번째 부분으로 사용됩니다(`defaults.chat.send`의 `defaults`).**`pack_identity`**(`"github:harupipipipi/rumiai-defaults"`)은 팩의 원격 식별자입니다.**`version`**(`"1.0.0"`)은 팩 버전입니다.**`vocabulary.types`**은 Pack에서 제공하는 구성요소 종류 목록입니다. `["chat", "agent", "coding", "ai_client", "tool", "prompt", "memory", "media", "frontend", "dev"]` 중 10개가 정의되어 있습니다.**`components`**은 각 구성요소의 정의입니다. 각 구성 요소에는 `type`, `id`, `path`(블록 내 디렉터리 경로) 및 `connectivity.provides`(제공할 처리기 이름 목록)이 있습니다. 예를 들어 `chat` 컴포넌트는 `path: "blocks/chat"`에 위치하며 `defaults.chat.create_conversation`부터 `defaults.chat.auto_trim`까지 18개의 핸들러를 제공합니다.**`load_order`**은 구성 요소 초기화 순서입니다. `memory` → `prompt` → `media` → `ai_client` → `tool` → `coding` → `chat` → `agent` → `dev` → `frontend` 순서로 로드됩니다.**`metadata`**은 팩 메타 정보(설명, 작성자, 라이센스)입니다.

## KernelFacade와의 접점

기본 팩은 세 가지 주요 지점에서 커널과 상호 작용합니다.

**`io.http.server`**: `blocks/frontend/start.py`은 커널로부터 `facade`를 수신하고 이를 `transport/http.py`의 `start_http_server(facade)`에 전달하여 HTTP 서버를 시작합니다. 파사드는 `DefaultsHttpServer` 인스턴스에 보관되며 `_handle_context_info()`는 `facade.list_interfaces()`을 호출하여 인터페이스 목록을 반환합니다.**`get_interface` / `list_interfaces`**: 커널이 등록한 InterfaceRegistry에서 다른 팩이나 커널 자체가 제공하는 인터페이스를 검색하는 데 사용됩니다. `/api/context` 현재 엔드포인트에서 사용 가능한 인터페이스 목록을 확인할 수 있습니다.**`emit`(EventBus)**: `call_handler`은 핸들러의 `context`를 통해 제공되며 이를 통해 다른 핸들러를 호출합니다. `call_handler("defaults.ai.complete", params)`과 같은 핸들러 이름과 매개변수를 지정하여 호출하세요. 이는 커널의 EventBus/InterfaceRegistry를 통해 해결됩니다.
