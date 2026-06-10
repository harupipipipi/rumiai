<!-- docs-i18n-links:start -->
[EN](../../node_spec.md) | [JP](../ja/node_spec.md) | [KR](./node_spec.md) | [CN](../zh-cn/node_spec.md)
<!-- docs-i18n-links:end -->

# 노드 정의 사양

노드 정의는 에코시스템 팩에 의해 노출되는 정적 기능 노드를 설명합니다.

버전: `rumi.node.v1`

## 발견

Core는 생태계 노드 검색 전에 내장 노드를 등록합니다. 1단계에는 정확히 하나의 코어 소유 내장 노드가 있습니다.

```json
{
  "node_id": "rumi.start",
  "kind": "core.builtin",
  "display_name": {
    "en": "Start",
    "ja": "開始"
  },
  "ports": [
    {
      "id": "out",
      "direction": "output",
      "standards": ["rumi.flow.start"],
      "multiple": true,
      "required": false
    }
  ],
  "metadata": {
    "owner": "core"
  }
}
```

`rumi.start`은 팩을 스캔하기 전에 글로벌 노드 레지스트리에 등록되므로 에코시스템 팩 없이도 그래프에서 참조할 수 있습니다. 에코시스템 팩은 코어 소유 내장 노드 ID를 재정의해서는 안 됩니다.

1단계 검색 경로:

1. §루미§0§
2. §루미§0§

재귀적 `**/node.json` 검색은 의도적으로 연기됩니다.

팩 제공 노드 정의 파일은 기존 팩 승인 및 해시 확인 흐름을 통과한 팩에서만 로드됩니다. 이는 팩에서 제공하는 흐름 로딩을 반영합니다. 사용자 공유 파일은 향후 로더에서 지원될 경우 여전히 스키마 유효성 검사 및 진단이 필요하지만 팩 승인 콘텐츠로 처리되지 않습니다.

## 파일 모양

파일은 하나 이상의 노드를 정의할 수 있습니다.

```json
{
  "version": "rumi.node.v1",
  "nodes": [
    {
      "node_id": "defaultspack.agent",
      "kind": "ecosystem.component",
      "display_name": {
        "en": "Agent",
        "ja": "エージェント"
      },
      "description": {
        "en": "Runtime node that combines AI, tools, memory, and prompts.",
        "ja": "AI・ツール・メモリ・プロンプトを束ねて実行するノード。"
      },
      "ports": [
        {
          "id": "start",
          "direction": "input",
          "display_name": {
            "en": "Start",
            "ja": "開始"
          },
          "standards": ["rumi.flow.start"],
          "aliases": ["start", "entry"],
          "multiple": false,
          "required": true
        },
        {
          "id": "tools",
          "direction": "input",
          "display_name": {
            "en": "Tools",
            "ja": "ツール"
          },
          "standards": [
            "rumi.tool.bundle",
            "defaultspack.tool.bundle.v1",
            "openai.function_tools.compat"
          ],
          "aliases": ["tools", "tool_bundle", "functions"],
          "multiple": true,
          "required": false
        },
        {
          "id": "result",
          "direction": "output",
          "display_name": {
            "en": "Result",
            "ja": "結果"
          },
          "standards": ["rumi.agent.result"],
          "aliases": ["result", "output"],
          "multiple": true,
          "required": false
        }
      ],
      "bindings": {
        "compile": "defaultspack.agent.compile_node",
        "on_input": {
          "tools": "defaultspack.agent.bind_tools"
        }
      },
      "requirements": {
        "configured_by": ["defaultspack.agent.configured"]
      },
      "metadata": {
        "pack_id": "defaultspack",
        "component": "agent",
        "icon": "bot",
        "category": "runtime"
      }
    }
  ]
}
```

## 필수 입력사항

노드:

- §루미§0§
- §루미§0§
- §루미§0§
- §루미§0§

포트:

- §루미§0§
- §루미§0§
- §루미§0§

## 포트 방향

허용되는 값:

- §루미§0§
- §루미§0§
- §루미§0§

1단계에서는 `input` 및 `output`에 대한 지원이 필요합니다. `bidirectional`는 스키마에 의해 예약되어 있으며 구현될 때까지 유효성 검사기에 의해 거부될 수 있습니다.

## 표준

`standards`은 표준 호환성 필드입니다. 항상 문자열 목록입니다.

다음과 같은 경우 포트를 연결할 수 있습니다.

```text
source.direction == "output"
target.direction == "input"
source.standards intersect target.standards is not empty
```

Core는 표준 문자열을 비교하지만 도메인 의미를 해석하지는 않습니다.

## Surface 출시 메타데이터

표면 노드는 시작 시 열려야 하는 데스크톱 앱을 광고할 수 있습니다.
Capability Graph는 이를 활성 프런트엔드 표면으로 선택합니다. 노드는 여전히
호환 가능한 출력 포트를 노출합니다. 시작 메타데이터는 핸드오프만 설명합니다.
그래프 컴파일 후 페이로드.

```json
{
  "node_id": "frontendpack.web_surface",
  "kind": "ecosystem.surface",
  "ports": [
    {
      "id": "surface",
      "direction": "output",
      "standards": ["rumi.surface"],
      "multiple": true
    }
  ],
  "metadata": {
    "pack_id": "frontendpack",
    "component_type": "frontend",
    "component_id": "web",
    "launch": {
      "kind": "desktop_app",
      "pack_id": "frontendpack",
      "surface": "browser",
      "default": true,
      "env": {
        "FRONTENDPACK_SURFACE": "web"
      }
    }
  }
}
```

안전을 위해 `metadata.launch.pack_id`은 노드의 자체 팩 ID와 일치해야 합니다. 노드
한 팩의 시작 시작이 다른 팩의 시작을 가리킬 수는 없습니다.

## 레거시 입력 호환성

레거시 파일은 다음을 사용할 수 있습니다.

```json
{
  "node_id": "defaultspack.agent",
  "name": "Agent",
  "ports": [
    {
      "id": "tools",
      "direction": "input",
      "contract": "rumi.tool.bundle"
    }
  ]
}
```

로더는 이를 v1 모델로 정규화합니다.

- `name`는 `display_name`가 없을 때 `display_name.en`이 됩니다.
- `contract`는 `standards`가 없을 때 `standards: [contract]`이 됩니다.

내부 모델은 `display_name` 및 `standards`만 사용해야 합니다.

## 표시 이름 대체

디스플레이 텍스트 해상도:

1. §루미§0§
2. §루미§0§
3. 레거시 `name`
4. `node_id` 또는 포트 `id`

## 바인딩

바인딩 이름 팩 소유 핸들러. Core는 핸들러 ID를 저장하고 확인하지만 도메인 의미를 할당하지는 않습니다.

일반적인 바인딩 슬롯:

- §루미§0§
- §루미§0§

바인딩 핸들러는 승인된 레지스트리 또는 커널 핸들러 인프라를 통해 해결되어야 합니다. 직접 임의 가져오기는 허용되지 않습니다.
