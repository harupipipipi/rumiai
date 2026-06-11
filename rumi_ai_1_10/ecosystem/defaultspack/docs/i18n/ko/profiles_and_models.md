<!-- docs-i18n-links:start -->
[EN](../../profiles_and_models.md) | [JP](../ja/profiles_and_models.md) | [KR](./profiles_and_models.md) | [CN](../zh-cn/profiles_and_models.md)
<!-- docs-i18n-links:end -->

# Rumi AI OS 기본값 프로필 및 모델

이 문서에서는 `defaults` 팩이 AI 프로필, 도구 구성 및 사용자 데이터를 관리하여 극도의 유연성, 사용자 지정 지침 및 고급 모델 조정(예: 에이전트 혼합)에 대한 요구 사항을 충족하는 방법을 자세히 설명합니다.

## "무슨 일이든 가능" 프로필의 원칙

전통적인 접근 방식은 `AI Profile`를 엄격하게 정의하는 것입니다(예: `model_name` 및 `temperature`). Rumi AI OS는 핵심 프로필 개체에 대해 유연하고 스키마가 없는 접근 방식을 채택하여 팩에 필요한 모든 것을 주입할 수 있습니다.

### 1. 유연한 AI 프로필
* **구조:** AI 프로필(`user_data/ai_profiles/`에 저장됨)은 JSON 개체입니다. `defaults` 팩에는 `id`, `name` 및 `provider`와 같은 표준 필드가 필요하지만 나머지는 열려 있습니다.
* **맞춤 지침:** 사용자 또는 팩은 다음과 같은 필드를 추가할 수 있습니다.
    ```json
    {
      "id": "coding_assistant",
      "provider": "openai",
      "model": "gpt-4",
      "system_prompt": "You are a helpful coding assistant.",
      "user_preferences": {
        "language_requirement": "English Recommended",
        "output_format": "markdown",
        "verbosity": "concise"
      },
      "custom_pack_data": {
        "my_pack_id": {
          "special_feature_enabled": true
        }
      }
    }
    ```
* **해석:** `defaults` 팩의 프롬프트 빌더는 이러한 `user_preferences`을 읽고 이를 LLM으로 보내기 전에 최종 시스템 프롬프트 컨텍스트에 동적으로 삽입합니다.

### 2. 사용자 데이터 표준화
특정 사용자의 환경과 관련된 모든 구성은 `user_data/`에 저장되어야 합니다. 여기에는 다음이 포함됩니다.
* `user_data/ai_profiles/`
* `user_data/tool_settings/`
* `user_data/agent_configs/`
* `user_data/ui_preferences/`

이러한 표준화를 통해 사용자 구성은 이식 가능하고 쉽게 백업되며 시스템 수준 팩 파일과 격리됩니다.

## 고급 모델 지원 (MoA, Ensembles 등)

MoA(Mixture of Agents) 또는 사용자 정의 라우팅 아키텍처와 같은 개념을 지원하기 위해 `defaults` 팩은 에이전트와 단일 모델 간의 1:1 관계를 가정해서는 안 됩니다.

### 1. "가상 공급자" 개념
MoA를 지원하기 위해 핵심 엔진을 수정하는 대신 `defaults` 팩은 "가상 공급자" 생성을 권장합니다.
* **구현:** 팩은 새로운 AI 제공자를 등록할 수 있습니다(예: `provider: moa_router`). `defaults` 팩 에이전트에게 이것은 다른 LLM처럼 보입니다.
* **위임:** 에이전트가 `moa_router`에 메시지를 보내면 `moa_router` 팩의 백엔드 핸들러가 인계받습니다. 그런 다음 다양한 실제 모델(GPT-4, Claude 등)에 대한 하위 요청을 생성하고 결과(MoA 프로세스)를 종합한 다음 최종 응답을 에이전트에 다시 반환할 수 있습니다.

### 2. 다중 모델 에이전트
또는 `defaults` 팩의 `agent.json` 스키마를 사용하면 기본 모델과 선택적 **폴백 모델** 또는**계획/추론** 대**도구 실행**에 대한 특정 모델을 지정할 수 있습니다.

```json
{
  ...
  "models": {
    "primary": "anthropic/claude-3-opus",
    "fallback": "openai/gpt-3.5-turbo",
    "planner": "openai/gpt-4"
  },
  ...
}
```
이를 통해 기본 다양한 모델 사용을 위한 특수 MoA 팩이 필요 없이 내장 에이전트가 매우 강력하고 비용 효율적일 수 있습니다.
