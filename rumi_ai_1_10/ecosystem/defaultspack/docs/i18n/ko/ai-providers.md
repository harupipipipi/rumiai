<!-- docs-i18n-links:start -->
[EN](../../ai-providers.md) | [JP](../ja/ai-providers.md) | [KR](./ai-providers.md) | [CN](../zh-cn/ai-providers.md)
<!-- docs-i18n-links:end -->

# AI 제공업체 가이드

## 1. 공급자 정보 소스

defaultspack의 ai_client는 매니페스트 우선으로 공급자를 확인합니다. OpenAI 호환 제공업체는
`extensions/llm/providers/<provider_id>/manifest.json` 및 `models/*.json`로만 추가할 수 있습니다.
독점 프로토콜이 필요한 경우에만 Python 공급자 클래스를 사용하십시오.

런타임의 선별된 테이블은 호환성 대체이며 새 공급자를 추가하기 위한 기본 경로가 아닙니다.

## 2. 지원되는 공급자 목록

| 제공자 ID | 설명 |
|---|---|
| `openai` | OpenAI API(GPT-4o, GPT-4o-mini, o3, o4-mini 등) |
| `anthropic` | Anthropic API(Claude Opus 4, Sonnet 4, Haiku 3 등) |
| `google` | Google Gemini API(Gemini 2.5 Pro, Gemini 2.5 Flash 등) |
| `openrouter` | OpenRouter API(defaultspack에서는 `tencent/hy3-preview:free`만) |
| `gitlawb-opengateway` | Gitlawb OpenGateway(MiMo에 대한 고정 허용 목록. 모든 모델에 필요한 API 키) |
| `groq` | Groq OpenAI 호환 API |
| `cerebras` | Cerebras OpenAI 호환 API |
| `nvidia` | NVIDIA NIM OpenAI 호환 API |
| `moonshotai` | Moonshot AI OpenAI 호환 API |
| `xiaomi-mimo` | Xiaomi MiMo 직접 API 지역 카탈로그 항목(초기 상태를 실행할 수 없음) |
| `stub` | 테스트 스텁. 고정 응답 반환 |
| `rumi` | 루미의 자체 메타 제공자(파이프라인, 라우팅, 평가) |


## 3. 각 공급자별 환경변수 설정

### 오픈AI

```bash
OPENAI_API_KEY=sk-...
# オプション:
OPENAI_BASE_URL=https://api.openai.com/v1    # カスタムエンドポイント
OPENAI_ORG_ID=org-...                         # 組織ID
```

### 인류학

```bash
ANTHROPIC_API_KEY=sk-ant-...
# オプション:
ANTHROPIC_BASE_URL=https://api.anthropic.com  # カスタムエンドポイント
```

### 구글

```bash
GOOGLE_API_KEY=AIza...
# または:
GEMINI_API_KEY=AIza...
# オプション:
GOOGLE_BASE_URL=https://generativelanguage.googleapis.com/v1beta/openai
```

### 오픈라우터

defaultspack의 OpenRouter 통합은 현재 `tencent/hy3-preview:free`만 대상으로 합니다.
API 키는 데스크톱 UI의 설정에서 저장할 수 있습니다. 값은 `user_data/secrets/OPENROUTER_API_KEY.json`입니다.
파일은 암호화되어 저장되며, 저장 여부만 프론트 엔드에 반환됩니다.

```bash
OPENROUTER_API_KEY=sk-or-...
# オプション:
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
```

### Gitlawb OpenGateway

Gitlawb OpenGateway는 OpenAI 호환 외부 게이트웨이입니다. 현재 모든 모델에는 API 키가 필요하므로 Rumi 런타임은 이를 `GITLAWB_OPENGATEWAY_API_KEY`로 저장하여 전송합니다. 클라우드 공급자로 취급되므로 런타임에 사용하려면 명시적인 옵트인이 필요합니다.

```bash
RUMI_DEFAULTSPACK_ENABLE_CLOUD_PROVIDERS=1
GITLAWB_OPENGATEWAY_API_KEY=ogw_live_...
# オプション:
GITLAWB_OPENGATEWAY_BASE_URL=https://opengateway.gitlawb.com/v1
```

사용 가능한 유일한 모델은 고정 허용 목록입니다.

| 모델명 | 특징 |
|---|---|
| `gitlawb-opengateway/mimo-v2.5-pro` | 추론을 위한 MiMo V2.5 Pro |
| `gitlawb-opengateway/mimo-v2-flash` | 빠른 MiMo V2 플래시 |
| `gitlawb-opengateway/mimo-v2-omni` | 이미지 입력 ​​기능이 있는 MiMo V2 Omni |
| `gitlawb-opengateway/mimo-v2-pro` | 추론을 위한 MiMo V2 Pro |
| `gitlawb-opengateway/mimo-v2.5` | 추론을 위한 MiMo V2.5 |

`mimo` 시스템은 Gitlawb OpenGateway의 OpenAI 호환 `POST /v1/chat/completions`으로 전송되며 유일한 차이점은 `model`입니다. `mimo-v2-omni` 이미지 인식은 OpenAI 호환 `content` 배열 형식을 사용합니다. 런타임은 게이트웨이 호환성을 위해 브라우저 사용자 에이전트를 할당합니다.

일반 OpenAI 호환 클라이언트에서 직접 사용하는 경우 기본 URL 및 API 키를 OpenAI 호환 환경 변수에 할당할 수 있습니다.

```bash
OPENAI_BASE_URL=https://opengateway.gitlawb.com/v1
OPENAI_API_KEY=ogw_live_...
OPENAI_MODEL=mimo-v2-omni
```

### Cloud OpenAI 호환 제공업체

Groq / Cerebras / NVIDIA NIM / Moonshot AI가 매니페스트 우선 공급자로 추가되었습니다. API 키가 설정되면 `detect_available_providers()`에서 런타임 공급자로 감지됩니다.

```bash
GROQ_API_KEY=...
CEREBRAS_API_KEY=...
NVIDIA_API_KEY=...      # または NGC_API_KEY
MOONSHOT_API_KEY=...
```

서비스 계층 및 미리 보기/엔터프라이즈 전용 조건은 메타데이터에만 저장되며 초기 구현 시 요청 본문에 자동으로 삽입되지 않습니다.

### 샤오미 MiMo 다이렉트 API

`xiaomi-mimo`은 Gitlawb OpenGateway와 별개의 우산 카탈로그 항목입니다. 직접 API는 `xiaomi-mimo-global` 및 `xiaomi-mimo-cn`로 지역화되며 공식 기본 URL/인증/토큰 부여 조건이 확인될 때까지 런타임 공급자로 자동 활성화되지 않습니다.

MiMo 토큰 계획은 공급자 카탈로그에서 `subscription_plans`으로 유지됩니다. 현재 우리는 `mimo_orbit_100t_grant_if_available`을 카탈로그 메타데이터로만 게시하고 이를 수동 가입/지역 범위 지정/자동 활성화 안함으로 처리합니다.

경고: 이 공급자를 활성화하면 프롬프트, 대화 기록 및 도구 결과와 같은 컨텍스트가 Xiaomi MiMo 직접 API로 전송됩니다.

### 스텁

환경 변수가 필요하지 않습니다. 테스트용.

### 루미

```bash
# rumi プロバイダーは他のプロバイダーの API キーを使用する。
# rumi 固有の設定は user_data/shared/ai_models/rumi/ に配置。
```

`user_data/config.json`의 `ai.providers` 섹션이나 OS 환경 변수에서 환경 변수를 설정합니다. `config.json` 값이 우선합니다.


## 4. 각 공급자가 사용할 수 있는 모델 목록

### 오픈AI

| 모델명 | 특징 |
|---|---|
| `gpt-4o` | 기함. 다중 모드 호환 |
| `gpt-4o-mini` | 경량, 고속, 저비용 |
| `o3` | 추론 전문화(추론 토큰) |
| `o4-mini` | 추론 전문/라이트 버전 |
| `gpt-4.1` | 최신 세대(사용 가능한 경우) |
| `gpt-4.1-mini` | 최신 세대/경량 버전 |
| `gpt-4.1-nano` | 최신 세대 및 가장 가벼운 |

### 인류학

| 모델명 | 특징 |
|---|---|
| `claude-opus-4-20250514` | 최고의 성능. 확장된 사고 대응 |
| `claude-sonnet-4-20250514` | 균형 잡힌 유형. 확장된 사고 대응 |
| `claude-haiku-3-20250307` | 빠른 속도와 저렴한 비용 |

### 구글

| 모델명 | 특징 |
|---|---|
| `gemini-2.5-pro` | 기함. 생각의 대응 |
| `gemini-2.5-flash` | 빠른 속도와 저렴한 비용 |
| `gemini-2.0-flash` | 안정 버전 |

### 스텁

| 모델명 | 특징 |
|---|---|
| `stub/echo` | 입력을 있는 그대로 반환 |
| `stub/fixed` | 고정 텍스트 반환 |
| `stub/error` | 항상 오류를 반환합니다 |

### 루미

| 모델명 | 특징 |
|---|---|
| `rumi/pipeline` | 여러 모델의 파이프라인 실행 |
| `rumi/router` | 업무에 따른 자동 모델 선택 |
| `rumi/moa` | 에이전트의 혼합물 |
| `rumi/eval` | 생성된 결과의 자동 평가 및 순위 재지정 |


## 5. 모델 사양 방법

### "공급자/모델" 형식

`"provider/model"` 형식의 문자열을 사용하여 모델을 지정합니다.

```
"openai/gpt-4o"
"anthropic/claude-sonnet-4-20250514"
"google/gemini-2.5-pro"
"stub/echo"
"rumi/router"
```

공급자를 생략하면 ai_client는 알려진 모델 이름에서 공급자를 자동으로 추론합니다. `"gpt-4o"`는 `"openai/gpt-4o"`으로 해석됩니다.

### 프로필 이름

`user_data/shared/ai_models/`에 있는 프로필 이름을 지정할 수도 있습니다.

```
"fast"          → config で定義されたプロファイル
"reasoning"     → config で定義されたプロファイル
"coding"        → config で定義されたプロファイル
```

이는 Agent.json의 `model` 섹션에서 사용됩니다.

```json
{
  "model": {
    "default": "claude-sonnet-4-20250514",
    "fallback": "gpt-4o-mini",
    "fast": "claude-haiku",
    "reasoning": "claude-opus-4-20250514"
  }
}
```


## 6. 프로필 설정 방법

`user_data/shared/ai_models/{provider_id}/profiles/{profile_name}/`에 프로필을 배치합니다.

```
user_data/shared/ai_models/
├── openai/
│   └── profiles/
│       ├── gpt-4o/
│       │   ├── profile.json
│       │   └── ui/
│       │       └── events.ui.yaml
│       └── o3/
│           └── profile.json
├── anthropic/
│   └── profiles/
│       ├── claude-sonnet-4/
│       │   ├── profile.json
│       │   └── ui/
│       │       └── events.ui.yaml
│       └── claude-opus-4/
│           └── profile.json
└── rumi/
    └── profiles/
        └── router/
            └── profile.json
```

### profile.json의 구조

```json
{
  "model_id": "claude-sonnet-4-20250514",
  "provider": "anthropic",
  "display_name": "Claude Sonnet 4",
  "capabilities": {
    "tool_calls": true,
    "vision": true,
    "thinking": true,
    "streaming": true,
    "json_mode": true
  },
  "context_length": 200000,
  "max_output_tokens": 64000,
  "pricing": {
    "input_per_1m_tokens": 3.00,
    "output_per_1m_tokens": 15.00,
    "cached_input_per_1m_tokens": 1.50,
    "currency": "USD"
  },
  "default_params": {
    "temperature": 0.7,
    "max_tokens": 8192
  },
  "thinking_config": {
    "budget_tokens": 10000
  }
}
```

`ui/events.ui.yaml`은 스트리밍되는 애니메이션 위젯을 정의하는 임의 파일입니다. 자세한 내용은 ai_client.md를 참조하세요.


## 7. 호환 기능 매트릭스

| 특징 | 오픈AI | 인류학 | 구글 | 스텁 | 루미 |
|---|---|---|---|---|---|
| `defaults.ai.complete` | ✅ | ✅ | ✅ | ✅ | ✅ |
| `defaults.ai.stream` | ✅ | ✅ | ✅ | ✅ | ✅ |
| `defaults.ai.embed` | ✅ | ❌ | ✅ | ❌ | ❌ |
| `defaults.ai.image_gen` | ✅ (달이) | ❌ | ✅ (이미지) | ❌ | ❌ |
| `defaults.ai.image_analyze` | ✅ (비전) | ✅ (비전) | ✅ (비전) | ❌ | ✅ |
| `defaults.ai.transcribe` | ✅ (속삭임) | ❌ | ✅ | ❌ | ❌ |
| `defaults.ai.tts` | ✅ | ❌ | ✅ | ❌ | ❌ |
| 도구 호출 | ✅ | ✅ | ✅ | ✅ | ✅ |
| 사고/추론 | ✅ (o3 시리즈) | ✅ (확장된 사고) | ✅ (제미니 2.5) | ❌ | ✅ |
| 비전 | ✅ | ✅ | ✅ | ❌ | ✅ |
| 캐싱 | ❌ | ✅ (임시 캐시) | ✅ (컨텍스트 캐시) | ❌ | ❌ |
| json_모드 | ✅ | ✅ | ✅ | ❌ | ✅ |
| 스트리밍 | ✅ | ✅ | ✅ | ✅ | ✅ |


## 7. 루미 모델 개요

루미 공급자는 다른 공급자의 모델을 결합하는 메타 공급자입니다. ai_client의 관점에서 볼 때 일반 공급자와 동일한 인터페이스를 가지고 있지만 내부적으로 여러 모델을 호출합니다.

### 루미/파이프라인 — 파이프라인

여러 모델을 연속적으로 실행합니다. 이전 단계의 출력을 다음 단계의 입력으로 전달합니다.

```json
{
  "model_id": "rumi/pipeline",
  "config": {
    "stages": [
      {"model": "openai/o3", "role": "planner"},
      {"model": "anthropic/claude-sonnet-4", "role": "executor"}
    ]
  }
}
```

### 루미/라우터 — 라우팅

작업 유형에 따라 모델을 자동으로 선택합니다. 분류에는 라우팅 모델(경량 모델)이 사용됩니다.

```json
{
  "model_id": "rumi/router",
  "config": {
    "classifier_model": "openai/gpt-4o-mini",
    "routes": {
      "coding": "anthropic/claude-sonnet-4",
      "reasoning": "openai/o3",
      "creative": "anthropic/claude-opus-4",
      "simple": "openai/gpt-4o-mini"
    }
  }
}
```

### rumi/moa — 에이전트의 혼합물

동일한 프롬프트를 여러 모델에 보내고 결과를 대조하여 최종 답을 생성합니다.

```json
{
  "model_id": "rumi/moa",
  "config": {
    "agents": [
      "openai/gpt-4o",
      "anthropic/claude-sonnet-4",
      "google/gemini-2.5-pro"
    ],
    "synthesizer": "anthropic/claude-opus-4"
  }
}
```

### rumi/eval — 평가

생성된 결과는 평가 모델을 이용하여 점수를 매기고, 가장 높은 점수를 받은 결과를 반환합니다.

```json
{
  "model_id": "rumi/eval",
  "config": {
    "generator": "anthropic/claude-sonnet-4",
    "evaluator": "openai/o3",
    "num_candidates": 3
  }
}
```

모든 루미 공급자 정의는 `user_data/shared/ai_models/rumi/profiles/`에 있습니다. 기본값은 루미 공급자의 실행 엔진 메커니즘만 제공하며 특정 파이프라인 구성은 user_data 측에서 정의됩니다.
