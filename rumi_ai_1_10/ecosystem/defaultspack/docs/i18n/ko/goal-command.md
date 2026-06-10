<!-- docs-i18n-links:start -->
[EN](../../goal-command.md) | [JP](../ja/goal-command.md) | [KR](./goal-command.md) | [CN](../zh-cn/goal-command.md)
<!-- docs-i18n-links:end -->

# /goal 슬래시 명령

`/goal <description>`은 직접적인 도구 실행 없이 defaultspack 콘솔에서 목표 추적 루프를 실행합니다.

1. **Worker** 에이전트는 목표를 향한 다음 구체적인 기여를 생성합니다.
2. 각 작업자 차례가 끝나면 독립적인 제3자 **평가자** 에이전트
   목표가 달성되었는지 확인합니다.
3. 목표가 아직 달성되지 않은 경우 평가자는 새로운 결과를 반환합니다.
   `next_instruction`, 그러면 작업자에게 다시 메시지가 표시됩니다.
4. 평가자가 목표를 달성한 것으로 표시하거나 목표가 달성된 것으로 표시하면 루프가 중지됩니다.
   `max_iterations` 캡이 적중되었습니다(기본 `5`, 하드 캡 `20`).

## 인수

| 이름 | 유형 | 필수 | 기본값 | 설명 |
|------------------|---------|----------|---------|-----------------------------------------------------------------------------|
| §루미§0§ | 문자열 | 예 | — | 작업자가 추구해야 하는 목표에 대한 자유로운 형식의 설명입니다.                 |
| §루미§0§ | 문자열 | 아니 | §루미§1§ | 최대 작업자/평가자 왕복. 1~20으로 고정됩니다.                      |
| §루미§0§ | 문자열 | 아니 | 활성 | 작업자 및 평가자 차례 모두에 전달되는 선택적 모델 힌트입니다.              |

슬래시 명령은 다음 위치에 등록됩니다.
§루미§0§ 및
행동은 [`blocks/goal/run.py`](../blocks/goal/run.py)에 있습니다.

## 결과 봉투

성공하면 명령이 다음을 반환합니다.

```json
{
  "status": "ok",
  "data": {
    "command": { "...": "manifest fields" },
    "executed": true,
    "result": {
      "goal": "Write a haiku about programming",
      "achieved": true,
      "reason": "Three-line haiku produced as requested.",
      "iterations": [
        {
          "iteration": 1,
          "worker_output": "...",
          "verdict": { "achieved": true, "reason": "...", "next_instruction": "" }
        }
      ],
      "iteration_count": 1,
      "final_output": "...",
      "max_iterations": 5,
      "stopped_reason": "achieved"
    }
  }
}
```

루프가 목표를 달성하지 못한 채 `max_iterations`에 도달하면 `achieved`
`false`가 되고 `stopped_reason`은 `"max_iterations_reached"`가 됩니다. 때
작업자 또는 평가자 모델 호출이 실패하고 명령이 반환됩니다.
`status: "error"`와 `code: "WORKER_FAILED"` 또는 `code: "EVALUATOR_FAILED"`
그리고 부분적인 진행 상황을 기록하는 `iterations` 배열입니다.

## 확장성 참고 사항: `pack_block` 실행 유형

`pack_block` 후크가 설치된 후 `/goal` 자체가 파일 추가를 통해 구현됩니다.

* `commands/manifests/goal.json`은 슬래시 명령을 선언합니다.
* `blocks/goal/run.py`은 목표 추구 루프를 구현합니다.

이 기능은 `pack_block` 실행 유형을 통해 연결됩니다.
`SlashCommandRegistry`, 다음의 Python 블록에 매니페스트를 디스패치할 수 있습니다.
`blocks/<dotted.path>` 노출 `run(input, context) -> dict`.

이 블록은 도구를 직접 실행하지 않습니다. 모델 호출만 수행합니다.
작업자와 평가자가 차례대로 돌아갑니다.
`pack_block`은 `default` 및 `pack` 매니페스트 출처에만 허용됩니다.
`user_data/shared/commands/` 아래의 사용자 매니페스트의 경우), 따라서 신뢰할 수 없는 명령
매니페스트는 임의의 모듈을 로드할 수 없습니다.

백엔드 동작이 필요한 향후 슬래시 명령은 이제 다음을 통해 추가할 수 있습니다.

1. 매니페스트를 `commands/manifests/<command>.json`에 삭제합니다.
2. `blocks/<area>/<file>.py`에 블록을 삭제하여 `run` 호출 가능 항목을 노출합니다.

해당 추가를 위해 기존 파일을 변경할 필요가 없습니다.
