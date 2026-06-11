<!-- docs-i18n-links:start -->
[EN](../../../tutorials/runtime-quickstart.md) | [JP](../../ja/tutorials/runtime-quickstart.md) | [KR](./runtime-quickstart.md) | [CN](../../zh-cn/tutorials/runtime-quickstart.md)
<!-- docs-i18n-links:end -->

# Tutorial: Runtime Quickstart

이 튜토리얼은 ** "지금 리포지토리에서 런타임이 움직이는 곳까지"**를 최단으로 확인하는 단계입니다.

## 전제

- repo 루트로 작업
- Python을 사용할 수 있습니다.

## Step 1. 헬스 체크 실행

```bash
python -m rumi_ai --health
```

`status: "UP"` 또는 `status: "DEGRADED"`가 반환되면 런타임은 시작 가능 상태입니다(`DOWN`는 필수 조사).

## Step 2. runtime 시작

```bash
python -m rumi_ai --headless
```

`[Rumi] startup.success`이 나오면 기동 완료입니다.

## Step 3. API의 소통 확인

다른 터미널에서:

```bash
curl http://127.0.0.1:8765/health
```

HTTP 200과 JSON이 반환되면 API를 사용할 수 있습니다.

## Step 4. panel 루트 확인(선택 사항)

브라우저에서 `http://127.0.0.1:8765/panel/`를 열고 화면이 표시되는지 확인합니다.

## Step 5. 정지

시작된 터미널에서 `Ctrl+C`.

## 검증 스크린샷

> 실행 확인으로 얻은 이미지입니다. 환경에 따라 표시는 다소 바뀝니다.

### /health(브라우저 표시)

![Runtime health screenshot](../assets/tutorials/runtime-health.png)

### /panel(브라우저 표시)

![Runtime panel screenshot](../assets/tutorials/runtime-panel.png)

## 실행 로그

런타임의 원시 로그는 다음에 저장됩니다.

- [../assets/tutorials/runtime-quickstart.log](../assets/tutorials/runtime-quickstart.log)

## 다음 읽기

- 구조를 쫓는다: [../concepts/system-mechanism.md](../concepts/system-mechanism.md)
- 운영/API 세부사항: [../operations.md](../operations.md)
- 뷰어 측 시작 경로 : [../rumi_viewer_start.md](../rumi_viewer_start.md)
