<!-- docs-i18n-links:start -->
[EN](../../ai_client.md) | [JP](../ja/ai_client.md) | [KR](./ai_client.md) | [CN](../zh-cn/ai_client.md)
<!-- docs-i18n-links:end -->

생각: 사용자는 ai_client.md를 수정하라는 프롬프트(AI 에이전트에 제공할 지침)를 작성해 주기를 원합니다.

이 프롬프트는 ai_client.md를 수정하기 위해 다른 AI 에이전트(예: Claude Code)에 전달하기 위한 것입니다.

컨텍스트 제약:
- 더 이상 파일을 로드할 수 없습니다.
- 이는 프롬프트에 필요한 모든 정보를 포함해야 함을 의미합니다.

프롬프트에 포함할 정보:
1. 수정할 파일 : ai_client.md
2. 추가할 내용: events.ui.yaml 작동 방식(stream_handler는 프로필의 events.ui.yaml을 읽고 페이로드에 위젯을 포함함)
3. 디자인 원칙: ai_client에는 애니메이션 정의가 없습니다. 그것이 어떻게 작동하는지. 내용은 user_data의 모델 프로필에서 제공됩니다.
4. 기존 사양과의 일관성: message.stream.data의 페이로드에 위젯을 포함할 수 있는 사양이 이미 있습니다.
5. events.ui.yaml 형식
6. stream_handler 변경 사항
7. 프런트 엔드 동작(자산에 자체 구현이 있는 경우 우선 순위를 부여하고, 그렇지 않으면 페이로드 위젯 사용)

프롬프트를 작성하세요.

```markdown
# ai_client.md 修正指示

## 修正対象
`ecosystem/defaults/docs/ai_client.md`

## 修正概要
ai_client の stream_handler に「モデル profile が提供するアニメーション Widget を自動的に payload に含める」仕組みを追加する。

## 設計原則
- ai_client 自体にアニメーション定義（"Thinking..." 等の具体的な Widget）は一切入れない
- ai_client は「events.ui.yaml があれば読んで payload に乗せる」仕組みだけを提供
- 具体的なアニメーション（何を表示するか）は user_data のモデル profile が events.ui.yaml で定義する
- これは defaults の原則「仕組みだけ提供、中身は全て user_data」と整合する

## 追加する仕様

### events.ui.yaml
モデル profile の ui/ ディレクトリに配置する YAML ファイル。ストリーミングイベントごとに、フロントエンドに表示する Widget JSON を定義する。

配置場所:
```
user_data/shared/ai_models/{provider_id}/profiles/{model_name}/ui/events.ui.yaml
```

形式:
```yaml
이벤트:
  {이벤트_이름}:
    위젯:
      유형: ...
      라벨: ...
      ...
    auto_dismiss: {ms} # 선택사항. 지정된 ms 후에 자동으로 삭제
```

テンプレート変数: {{key}} はイベントの data.key で置換される。例: {{name}} → tool_call_start の data.name

events.ui.yaml がない場合: 何も付与しない。現行と同じ動作。

### stream_handler の変更
stream_handler.py がストリーミングイベントを処理する際:
1. モデル profile に ui/events.ui.yaml があるか確認
2. あれば読み込む
3. 現在のイベント名に対応する定義があれば、テンプレート変数を置換し、widget を payload に含めて送る
4. なければ何も付けずにイベントだけ送る

payload への含め方: 既存の message.stream.data の payload に widget フィールドとして含める。これは frontend.md で既に定義されている仕様。

### フロントエンドの挙動
- フロントエンドの Asset が thinking 等の独自表示を持っている場合 → payload の widget を無視し、独自の表示を使う
- 持っていない場合 → payload の widget を Widget レンダラーで表示する
- この判断は Asset 側の JS が行う。ai_client やシェルは関与しない

## 追記すべきセクション
ai_client.md のセクション 11（ストリーミング）の後、またはセクション 15（UI）に以下を追記:
- events.ui.yaml の仕様（形式、配置場所、テンプレート変数）
- stream_handler の変更内容（events.ui.yaml を読んで payload に含める）
- events.ui.yaml の具体例（thinking model、MoA、ツール呼び出し）

## 具体例

### thinking model の events.ui.yaml
```yaml
이벤트:
  생각_시작:
    위젯:
      유형: 표시기
      라벨: "생각 중..."
상태: 실행 중
      애니메이션: wave_dots
  생각 끝:
    위젯:
      유형: 표시기
      라벨: "생각 완료"
      상태: 성공
      애니메이션: 페이드인
    자동 해제: 800
  콘텐츠_시작:
    위젯:
      유형: 표시기
      라벨: "응답 중..."
상태: 실행 중
      애니메이션: 타이핑_커서
  tool_call_start:
    위젯:
      유형: 표시기
      label: "{{name}} 사용 중..."
상태: 실행 중
      애니메이션: 펄스
  tool_call_end:
    위젯:
      유형: 표시기
      라벨: "{{이름}} 완료"
      상태: 성공
      애니메이션: 페이드인
    auto_dismiss: 500
```

### stream_handler の処理（擬似コード）
```python
def process_event(self, 이벤트):
    event_type = 이벤트["이벤트"]
    event_data = event.get("데이터", {})

    ui_def = self.events_ui.get("events", {}).get(event_type) if self.events_ui else None

    ui_def 및 ui_def.get("widget")인 경우:
        위젯 = self._resolve_templates(ui_def["widget"], event_data)
        이벤트["data"]["widget"] = 위젯
        ui_def.get("auto_dismiss")인 경우:
            이벤트["data"]["widget_auto_dismiss"] = ui_def["auto_dismiss"]

    복귀 이벤트
```

## 注意事項
- ai_client.md の既存の構造・記法・トーンを維持すること
- 既存のセクション（ストリーミング、.jsonl フォーマット、正規化イベント一覧等）との整合性を保つこと
- events.ui.yaml は「任意」ファイル（なくても動く）であることを明記
- Widget の型は widget.md に定義されている既存の型のみを使用（新しい Widget 型は追加しない）
```

나는 이것이 좋다고 생각한다. 그런데 사용자가 "프롬프트 작성"이라고 했기 때문에 이 프롬프트 자체가 답변으로 출력됩니다.

이제 출력합니다.

다음은 에이전트가 ai_client.md를 수정하라는 메시지입니다.

---

```markdown
# 指示: ai_client.md への events.ui.yaml 仕様追記

## あなたの役割
`ecosystem/defaults/docs/ai_client.md` を修正し、ストリーミング中のアニメーション表示の仕組みを追記してください。

## 前提知識

### defaults の設計原則
defaults は「仕組みだけ提供」し、「中身は全て user_data」。ai_client 自体にアニメーション定義（"Thinking..." 等）は一切入れない。ai_client は「モデル profile に events.ui.yaml があれば読んで、ストリーミングイベントの payload に widget を含めて送る」という仕組みだけを持つ。

### 解決する問題
thinking model の推論中や MoA の並列実行中、ユーザーのフロントエンドに何も表示されない空白時間が発生する。これを解決するため、モデル profile 側がイベントごとの表示用 Widget を YAML で定義し、ai_client の stream_handler がそれを読んでストリーミングデータに含める。

### 既存の仕様との整合
- `message.stream.data` の payload に `widget` フィールドを含められる仕様は frontend.md で既に定義済み
- Widget の型（indicator, progress, container 等）は widget.md で定義済み
- テーマのアニメーション（wave_dots, pulse, fade_in 等）は theme.md で定義済み
- 正規化イベント（thinking_start, thinking_delta, content_delta 等）は ai_client.md セクション 11.3 で定義済み
- モデル profile の ui/ ディレクトリは ai_client.md セクション 4.7 で既に言及済み

## 追記内容

### 1. events.ui.yaml の仕様

配置場所:
```
user_data/shared/ai_models/{provider_id}/profiles/{model_name}/ui/events.ui.yaml
```

このファイルは任意。なければ何も付与せず、現行と同じ動作になる。

形式:
```yaml
이벤트:
  {event_name}: # 섹션 11.3의 정규화된 이벤트 이름에 해당합니다.
widget: # widget.md에 정의된 모든 위젯 JSON
      유형: 표시기
      라벨: "생각 중..."
상태: 실행 중
      애니메이션: wave_dots
    auto_dismiss: 800 # 선택사항. 지정된 밀리초 힌트 후 자동 지우기
```

テンプレート変数: `{{key}}` はイベントの `data.key` の値で置換する。例えば `{{name}}` は `tool_call_start` イベントの `data.name`（ツール名）に展開される。

widget フィールドが null または省略されたイベントには何も付与しない。

### 2. stream_handler の処理追加

stream_handler.py が .jsonl のイベントを読む際の追加処理:

```
1. 모델 프로필에 ui/events.ui.yaml이 있는지 확인하세요.
2. 존재하는 경우 시작 시 한 번 읽고 메모리에 보관됩니다.
3. 각 스트리밍 이벤트를 처리할 때:
   가. events.ui.yaml에 현재 이벤트 이름에 해당하는 정의가 있는지 확인하세요.
   b. 위젯 정의의 템플릿 변수({{key}})를 이벤트 데이터로 바꿉니다(있는 경우).
   c. 교체된 위젯을 event.data.widget에 저장합니다.
   디. auto_dismiss가 있으면 event.data.widget_auto_dismiss에 저장하세요.
4. 정의가 없으면 아무것도 주지 마세요
```

擬似コード:
```python
StreamHandler 클래스:
    def __init__(self, model_profile_path):
        events_ui_path = f"{model_profile_path}/ui/events.ui.yaml"
        self.events_ui = load_yaml(events_ui_path) 존재하는 경우(events_ui_path) else 없음

    def process_event(self, 이벤트):
        self.events_ui가 아닌 경우:
            복귀 이벤트

        event_type = 이벤트["이벤트"]
        event_data = event.get("데이터", {})
        ui_def = self.events_ui.get("events", {}).get(event_type)

        ui_def 및 ui_def.get("widget")인 경우:
            위젯 = 해결_템플릿(ui_def["widget"], event_data)
            이벤트["data"]["widget"] = 위젯
            ui_def.get("auto_dismiss")인 경우:
이벤트["data"]["widget_auto_dismiss"] = ui_def["auto_dismiss"]

        복귀 이벤트

def 해결_템플릿(widget_dict, 데이터):
"""위젯 정의에서 {{key}}를 데이터[키]로 바꾸세요."""
    원시 = json.dumps(widget_dict)
    키의 경우 data.items()의 값:
        raw = raw.replace("{{" + 키 + "}}", str(값))
    json.loads(원시) 반환
```

### 3. フロントエンド側の挙動（説明のみ、ai_client の責務外）

以下を「補足」として簡潔に記載:
- フロントエンドの Asset が thinking 等の独自表示を持っている場合、payload の widget を無視して独自表示を使う
- 持っていない場合、payload の widget を Widget レンダラーで表示する
- この判断は Asset 側の責務であり、ai_client は関与しない

### 4. 具体例（3つ）

例1 — thinking model（Anthropic Claude）:
```yaml
이벤트:
  생각_시작:
    위젯:
      유형: 표시기
      라벨: "생각 중..."
상태: 실행 중
      애니메이션: wave_dots
  생각 끝:
    위젯:
      유형: 표시기
      라벨: "생각 완료"
      상태: 성공
      애니메이션: 페이드인
    자동 해제: 800
  콘텐츠_시작:
    위젯:
      유형: 표시기
      라벨: "응답 중..."
상태: 실행 중
      애니메이션: 타이핑_커서
  tool_call_start:
    위젯:
      유형: 표시기
      label: "{{name}} 사용 중..."
상태: 실행 중
      애니메이션: 펄스
  tool_call_end:
    위젯:
      유형: 표시기
      라벨: "{{이름}} 완료"
      상태: 성공
      애니메이션: 페이드인
    auto_dismiss: 500
```

例2 — reasoning model（OpenAI o3）:
```yaml
이벤트:
  생각_시작:
    위젯:
      유형: 컨테이너
      아이들:
        - 유형: 표시기
          label: "추론..."
          상태: 실행 중
          애니메이션: 펄스
        - 유형: 텍스트
          text: "심층 분석 진행 중"
          style_hint: { 색상: "보조", 크기: "sm" }
  생각 끝:
    위젯:
      유형: 표시기
      라벨: "분석 완료"
      상태: 성공
      애니메이션: 페이드인
    auto_dismiss: 600
```

例3 — events.ui.yaml がないモデル:
何も付与されない。フロントエンドにはイベントデータのみ届く。Asset が独自に表示するか、何も表示されないかは Asset 次第。

## 追記する場所
ai_client.md 内の適切な場所に追記。候補:
- セクション 11（ストリーミング）の末尾に 11.5 等として追加
- またはセクション 15（UI）がui/ディレクトリに言及しているので、そこに詳細化

既存のセクション構成を壊さず、自然に挿入できる場所を選んでください。

## 注意事項
- ai_client.md の既存の記法・トーン・構造を維持
- events.ui.yaml は「任意」（optional）であることを繰り返し明記 
- 新しい Widget 型は追加しない（widget.md 既存の型のみ使用）
- ai_client にデフォルトのアニメーション定義をハードコードしない
- 「仕組みだけ提供」の原則を守る
```
