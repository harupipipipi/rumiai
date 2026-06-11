<!-- docs-i18n-links:start -->
[EN](../../competitive_agent_install_eval.md) | [JP](../ja/competitive_agent_install_eval.md) | [KR](./competitive_agent_install_eval.md) | [CN](../zh-cn/competitive_agent_install_eval.md)
<!-- docs-i18n-links:end -->

# 경쟁 에이전트 설치 평가

날짜: 2026-06-03

이 노트는 다음에 대해 실행된 defaultspack 설치/온보딩 검사를 기록합니다.
Genspark, Manus, Cline, Hermes 및 OpenClaw에 대한 현재 공개 설치 흐름입니다.
이는 defaultspack을 브라우저 우선 및
로컬 우선 보안 모델을 약화시키지 않고 에이전트 런타임 제품을 제공합니다.

## 테스트된 흐름

| 제품 | 설치 또는 실행 경로가 관찰됨 | 실용적인 바 defaultspack은 |를 충족해야 합니다.
| --- | --- | --- |
| 젠스파크 | Claw, 워크플로, 드라이브 및 앱 진입점이 표시되는 `https://www.genspark.ai/ja`의 브라우저 작업 공간입니다. | 첫 번째 화면에서는 문서를 읽지 않고도 채팅, 도구, 작업 영역 및 설정을 검색할 수 있어야 합니다. |
| 마누스 | `https://manus.im/app`의 브라우저 앱. | 앱 셸은 하나의 URL에서 로드되어야 하며 인증 또는 빈 초기 상태를 허용해야 합니다. |
| 클라인 | 공식 설치 문서에는 IDE 확장, CLI, Kanban 및 SDK 경로가 표시됩니다. IDE 설치 방법은 확장 프로그램 열기, Cline 검색, 설치, 활동 표시줄 열기, 공급자 승인입니다. CLI 설치는 `npm install -g cline`, `cline auth`, 그 다음 `cline`입니다. | defaultspack은 UI 우선 및 명령 우선 설정을 모두 지원해야 하며 공급자 설정은 설치 후 명시적이어야 합니다. |
| 헤르메스 | `NousResearch/hermes-agent` GitHub 페이지는 설치 프로그램, 데스크톱 빌드, 게이트웨이, 공급자, 플러그인, 기술 및 대시보드 표면이 포함된 대규모 에이전트 런타임을 노출합니다. | defaultspack에는 원시 채팅보다는 눈에 띄는 공급자, 도구, 승인 및 대시보드 기본 요소가 필요합니다. |
| 오픈클로 | 공식 문서는 설치 프로그램 스크립트, npm 설치, 온보딩, 게이트웨이 상태, 대시보드 실행 및 채널 설정을 제공합니다. Windows 설치 프로그램은 `iwr -useb https://openclaw.ai/install.ps1 | iex`입니다. 온보드 없음 모드도 문서화되어 있습니다. | defaultspack에는 짧은 설치 경로, 네트워크 없음/키 없음 로컬 모드 및 게이트웨이/UI/모델 상태에 대한 명확한 다음 단계 확인이 필요합니다. |

## defaultspack 결과

- 디스크 및 쓰기 가능한 임시 프로브에 대해 `python -m rumi_ai --health`가 `UP`을 반환했습니다.
- `ecosystem/defaultspack/webapp`의 `npm test`가 207개의 테스트를 통과했습니다.
- `npm run build`는 프로덕션 쉘 자산을 생성했습니다.
- Chrome은 `http://127.0.0.1:39766/`에서 개발 UI를 열고
  defaultspack luxe 쉘.
- `npm run lint`은 Lint 스크립트가 사용되었기 때문에 Windows에서 처음에 실패했습니다.
  `new URL(...).pathname`, `C:\C:\...` 생산; 이것은 해결되었습니다
  `fileURLToPath(import.meta.url)`.

## 경쟁사 로컬 설치 참고 사항

- `npm install --prefix work/competitor-installs/cline cline@3.0.15` 완료,
  `cline --help`에서는 공급자 인증, 로컬 데이터 디렉터리, 작업 트리, 후크, MCP,
  허브, 스케줄러 및 Kanban 명령.
- `npm install --prefix work/competitor-installs/hermes --ignore-scripts
  hermes-agent@0.15.2` completed, but `hermes-agent --help` 실패
  이 Windows 환경에서는 `ModuleNotFoundError: No module named 'run_agent'`입니다.
- `npm install --prefix work/competitor-installs/openclaw openclaw@2026.5.28`
  설치 후/상태 프로세스가 계속 실행되는 동안 5분을 초과했습니다.
  두 번째 `--ignore-scripts` 시도도 3분을 초과했습니다. 이것은
  OpenClaw의 설치 프로그램은 작동할 때 매력적이지만 패키지 설치는
  defaultspack의 로컬 우선 시작보다 더 무거운 작업 경로입니다.

## 오픈코드 젠 체크

- `https://opencode.ai/zen/go/v1/models`에 대한 Python/urllib 직접 액세스는
  이 환경에서는 Cloudflare 오류 1010으로 인해 차단되었습니다.
- 제공된 Zen 키를 사용한 Chrome 채널 API 액세스가 현재 모델을 반환했습니다.
  `minimax-m3` 및 `qwen3.7-max`을 포함한 목록입니다.
- `minimax-m3`에 대한 실시간 완료 시도가 OpenCode에 도달했지만
  `CreditsError`: 워크스페이스에 결제 방법이 구성되어 있지 않기 때문입니다.
- defaultspack에는 이제 `opencode-go/minimax-m3`이 포함되어 있으며
  Python 공급자 허용 목록과 정적 모두의 `opencode-go/qwen3.7-max`
  공급자 모델 카탈로그.

## 경쟁 준비 체크리스트

- 클라우드 키 없이 로컬 우선 시작.
- 하나의 localhost URL에서 표시되는 UI 셸.
- 복제/빌드 중이 아닌 설치 후 공급자 키 설정.
- 모델 카탈로그에는 평가자가 사용하는 현재 OpenCode Zen 모델이 포함되어 있습니다.
- 브라우저/컴퓨터/도구 승인은 명시적이고 감사 가능합니다.
- Windows 린트/빌드 경로는 절대 작업공간 경로에서 작동합니다.
- 헬스, 유닛, 린트, 빌드, 크롬에서 설치 증거 재현 가능
  연기 점검.
