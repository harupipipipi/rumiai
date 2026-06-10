<!-- docs-i18n-links:start -->
[EN](../../consent.md) | [JP](../ja/consent.md) | [KR](./consent.md) | [CN](../zh-cn/consent.md)
<!-- docs-i18n-links:end -->

# 동의 안내

## 1. 개념과 목적

동의 툴은 AI 응답이 투자 조언, 의학적 조언, 법률 자문 등 전문 분야에 속할 경우 사용자에게 고지 사항을 표시하고 동의를 요청하는 메커니즘입니다.

기본 팩은 전체 동의 메커니즘(판단 로직, 핸들러, UI 팝업 협업, 이벤트 통신)을 제공합니다. 특히 기본 팩에는 다음 파일이 포함됩니다.

| 파일 | 설명 |
|---|---|
| §루미§0§ | 심판 처리자(`defaults.tool.consent_check`) |
| §루미§0§ | 동의 기록 처리기(`defaults.tool.consent_confirm`) |
| §루미§0§ | `ConsentChecker` 클래스(판단 로직/동의 기록 관리) |

`defaults.tool.consent_check` 및 `defaults.tool.consent_confirm`은 `ecosystem.json`의 `tool` 구성 요소 중 `provides`에 선언되어 있습니다. HTTP 전송은 `POST /api/consent/check` 및 `POST /api/consent/{id}/confirm` 경로를 사용하여 액세스할 수 있습니다.


## 2. 판단 메커니즘

### 키워드 기반 판단

가볍고 빠른 1차 판단. 응답 텍스트에 특정 키워드가 포함되어 있는지 확인하세요. `domain/tool/consent.py`의 `ConsentChecker.check_keywords()`이 실행됩니다. 카테고리와 키워드는 `CATEGORIES` 명령에 따라 모듈에 하드 코딩되어 있습니다.

```python
# domain/tool/consent.py より抜粋
CATEGORIES = {
    "investment": {
        "keywords": ["投資", "株", "株式", "株価", "銘柄", "ポートフォリオ",
                     "資産運用", "利回り", "配当", "投資信託", "ファンド",
                     "FX", "為替", "仮想通貨", "暗号資産", "ビットコイン",
                     "ETF", "NISA", "iDeCo", "信用取引", "空売り",
                     "investment", "stock", "portfolio", "dividend", "fund",
                     "forex", "crypto", "bitcoin", "trading"],
        "disclaimer": "【免責事項 — 投資に関する情報】..."
    },
    "medical": {
        "keywords": ["診断", "治療", "処方", "薬", "服薬", "投薬",
                     "症状", "病気", "疾患", "手術", "副作用",
                     "医療", "医師", "病院", "クリニック",
                     "diagnosis", "treatment", "prescription", "medication",
                     "symptom", "disease", "surgery", "side effect"],
        "disclaimer": "【免責事項 — 医療に関する情報】..."
    },
    "legal": {
        "keywords": ["訴訟", "裁判", "弁護士", "法律相談", "契約書",
                     "損害賠償", "慰謝料", "示談", "告訴", "起訴",
                     "法的", "判例", "法令", "条文", "権利",
                     "lawsuit", "attorney", "legal advice", "contract",
                     "liability", "damages", "litigation"],
        "disclaimer": "【免責事項 — 法律に関する情報】..."
    },
    "tax": {
        "keywords": ["税金", "確定申告", "所得税", "住民税", "消費税",
                     "法人税", "相続税", "贈与税", "控除", "節税",
                     "税務", "年末調整", "源泉徴収", "経費", "減価償却",
                     "tax", "deduction", "income tax", "tax return"],
        "disclaimer": "【免責事項 — 税務に関する情報】..."
    },
}
```

### AI 기반 판단

`consent_check` 핸들러의 `use_ai` 매개변수를 `true`로 설정하면 `ConsentChecker.check_ai()`가 AI 기반 판단을 수행합니다. 텍스트가 민감한 카테고리에 속하는지 여부를 분류하기 위해 내부적으로 `AIClient.complete()`를 호출합니다.

```python
# domain/tool/consent.py の AI 判定用システムプロンプト
_AI_JUDGE_SYSTEM = (
    "You are a content classifier. Analyze the given text and determine "
    "if it contains sensitive advice in any of these categories: "
    "investment, tax, medical, legal.\n"
    "Respond with ONLY a JSON object: "
    '{"categories": ["category1", ...], "confidence": 0.0-1.0}\n'
    "If no sensitive content is found, respond: "
    '{"categories": [], "confidence": 1.0}'
)
```

`ConsentChecker.check()`은 키워드 판단과 AI 판단을 결합합니다. 키워드 판단은 오탐이 많지만 누락이 적고, AI 판단은 오탐이 적지만 속도가 느립니다.


## 3. 핸들러 API

### defaults.tool.consent_check

텍스트를 확인하고 동의가 필요한지 여부를 반환합니다.

**HTTP**: §루미§0§

**입력_데이터**:

| 필드 | 유형 | 필수 | 설명 |
|---|---|---|---|
| §루미§0§ | §루미§1§ | 예 | 판정대상 텍스트 |
| §루미§0§ | §루미§1§ | 아니요 | AI 판단 사용(기본값 `false`) |
| §루미§0§ | §루미§1§ | 아니요 | AI 판단 시 모델 지정(기본 `"stub/default"`) |

**반환 값**:

```json
{
  "status": "ok",
  "data": {
    "requires_consent": true,
    "categories": ["investment", "medical"],
    "consent_id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
    "disclaimers": {
      "investment": "【免責事項 — 投資に関する情報】...",
      "medical": "【免責事項 — 医療に関する情報】..."
    }
  }
}
```

`requires_consent`이 `false`이면 `categories`는 빈 배열이고, `consent_id`은 `null`이고 `disclaimers`는 빈 사전입니다.

### defaults.tool.consent_confirm

사용자 동의/거부를 기록합니다.

**HTTP**: §루미§0§

**입력_데이터**:

| 필드 | 유형 | 필수 | 설명 |
|---|---|---|---|
| §루미§0§ | §루미§1§ | 예 | `consent_check`에서 반환된 동의_ID(HTTP의 경로 매개변수에서 삽입됨) |
| §루미§0§ | §루미§1§ | 예 | 사용자 동의 |

**반환 값**:

```json
{
  "status": "ok",
  "data": {
    "consent_id": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
    "accepted": true,
    "accepted_at": "2025-01-01T00:00:00Z"
  }
}
```

동의 기록은 `user_data/shared/consent_log/{consent_id}.json`(`ConsentChecker._persist()`에 작성됨)에서 영구적으로 기록됩니다.


## 4. chat.send에 통합하는 방법(제안)

`blocks/tool/consent_check.py`에 대한 문서 문자열에 설명된 대로 통합 제안:

```python
# blocks/chat/send.py の assistant_msg 生成後に追加
consent_result = call_handler("defaults.tool.consent_check", {
    "text": assistant_response_text,
    "use_ai": False,
})
if consent_result["data"]["requires_consent"]:
    context["emit_widget"]({
        "type": "consent_popup",
        "consent_id": consent_result["data"]["consent_id"],
        "disclaimers": consent_result["data"]["disclaimers"],
    })
    user_response = context["wait_event"]("ui.consent_response",
        timeout=300,
        filter={"consent_id": consent_result["data"]["consent_id"]})
    call_handler("defaults.tool.consent_confirm", {
        "consent_id": consent_result["data"]["consent_id"],
        "accepted": user_response.get("accepted", False),
    })
```


## 5. 프런트 엔드에 표시

`emit_widget` 또는 `emit_event("ui.popup.show", ...)`에 동의 팝업이 표시됩니다. 프런트 엔드의 자산은 이 이벤트를 수신하고 팝업을 그립니다.

Asset의 JS가 `event.broadcast`을 수신하고 `event_type`이 `"ui.popup.show"`인 경우 팝업이 표시됩니다. 사용자가 버튼을 클릭하면 `event.broadcast`는 `"ui.popup.response"` 이벤트를 다시 보냅니다.

팝업을 위젯으로 표현하는 경우:

```json
{
  "type": "card",
  "style_hint": {"variant": "warning"},
  "header": {"type": "text", "text": "投資に関する免責事項"},
  "body": {"type": "markdown", "content": "この情報は一般的な情報提供を目的としており..."},
  "footer": {
    "type": "row",
    "children": [
      {"type": "button", "label": "同意して表示", "action": "consent_accept", "variant": "primary"},
      {"type": "button", "label": "表示しない", "action": "consent_deny", "variant": "secondary"}
    ]
  }
}
```

동의 도구 팝업은 프런트 엔드 자산에 의해 그려집니다. defaults는 Emit_event / wait_event / Emit_widget이라는 범용 통신 메커니즘과 판단 및 기록을 위한 핸들러를 제공합니다.
