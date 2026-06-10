<!-- docs-i18n-links:start -->
[EN](../../../quality_pack/claude_desktop_quality_pack.md) | [JP](../../ja/quality_pack/claude_desktop_quality_pack.md) | [KR](./claude_desktop_quality_pack.md) | [CN](../../zh-cn/quality_pack/claude_desktop_quality_pack.md)
<!-- docs-i18n-links:end -->

# rumi_ai를 위한 Claude 데스크톱 수준 품질 팩

이 문서는 rumi_ai를 고품질로 지속적으로 개발, 감사, 검증하기 위한 실용적인 팩입니다.  
**PR1은 품질 자산만 추가하며 제품 동작을 변경하지 않습니다. **

---

## 1. 팩의 목적

1. 기존 테스트와 누락된 영역을 하나의 운영 절차로 통합합니다.
2. 단시간에 장애를 분리하고 재현할 수 있도록 합니다.
3. README/설계 철학(No Favoritism, Fail-Soft, Malicious Assumption, Least Privilege)과의 일관성을 기계적으로 확인합니다.

---

## 2. 실행 명령(권장 순서)

저장소 루트에서 실행:

```bash
bash rumi_ai_1_10/scripts/quality_pack/run_claude_quality_pack.sh
```

전체 감사 모드(기존 레거시 린트 부채 포함):

```bash
RUMI_FULL_QUALITY=1 bash rumi_ai_1_10/scripts/quality_pack/run_claude_quality_pack.sh
```

개별 실행:

```bash
# root (version-stable entrypoint) テスト
python -m pytest tests -v

# package テスト
cd rumi_ai_1_10
python -m pytest tests -v

# 追加した品質契約テストのみ
python -m pytest tests/test_claude_quality_pack_contract.py -v
cd ..
python -m pytest tests/test_entrypoint_contracts.py -v

# Python 品質ゲート
cd rumi_ai_1_10
python -m ruff check tests/test_claude_quality_pack_contract.py
python -m ruff format --check tests/test_claude_quality_pack_contract.py
python -m mypy tests/test_claude_quality_pack_contract.py
cd ..
python -m ruff check tests/test_entrypoint_contracts.py
python -m ruff format --check tests/test_entrypoint_contracts.py
python -m mypy tests/test_entrypoint_contracts.py

# Frontend/Viewer/Pack-shell
cd rumi_viewer/frontend && npm run lint && npm run build && cd ../..
cd pack-shell && cargo test && cd ..
```

---

## 3. 추가 테스트 영역

## 3.1 이념적합성 점검
- 생각메모, 품질팩문서에 필수항목이 있는지 확인
- README/CI 정의 계약이 깨졌는지 확인하기 위한 정적 검증

## 3.2 CLI/백엔드 계약
- 루트 진입점(`rumi_ai/__main__.py`)이 `rumi_ai_1_10.app`에 연결되는 컨트랙트
- 버전 정렬(`rumi_ai/__init__.py` 및 `rumi_ai_1_10/pyproject.toml`)

## 3.3 UI/극작가와 동일(정적 계약)
- `localhost:8765`은 Tauri 설정의 CSP에 포함되어야 합니다.
- `connect-src`에서는 `https://` 또는 `*`를 허용하지 않습니다.
- 유형 확인/빌드 스크립트가 프런트엔드 패키지에 있어야 합니다.

## 3.4 설정/권한/장애 시스템
- 루트 pytest/패키지 pytest/카고 테스트는 CI 워크플로에 정의되어야 합니다.
- 릴리스 워크플로에는 `v*` 태그 트리거와 `cargo tauri build`이 있습니다.

---

## 4. 감사 절차

1. 감사 로그 확인
   - §루미§0§
   - §루미§0§
   - §루미§0§
2. 승인상태 확인
   - 승인되지 않은 팩이 실행되지 않습니다.
   - `modified` 상태 팩이 재인증 없이 실행되지 않습니다.
3. 권한 확인
   - 기능 부여와 네트워크 부여는 최소 권한입니다.
4. 고장기록
   - 재현 명령, 예상값, 실제값, 영향 범위, 해결 방법 및 영구 대책 후보 남겨두기

---

## 5. 수동 확인 단계(최소 설정)

1. 시동 안전
   - 엄격한 시작: `python app.py`
- 개발 시작 : `python app.py --permissive` (허가 조건 확인)
2. 승인 흐름
   - 팩 스캔 -> 보류 중 -> 승인/거부 -> 상태 전환 확인
3. 네트워크 권한
   - 승인 없이 거절당함
   - grant 부여 후 부여되는 것
4.뷰어 디스플레이
   - 뷰어는 localhost 패널을 표시할 수 있습니다.
   - 외부 URL 안내는 CSP/권한에 의해 통제됩니다.

---

## 6. 회귀 확인 절차

1. 기존 CI(root/package/cargo)와 동일한 명령어 실행
2. 추가된 품질 계약 테스트 실행
3. 린트/타입 검사/빌드 전달
4. 실패한 경우 '테스트 구현 문제'인지 '제품 버그'인지 구분합니다.
   - 테스트 구현 문제: PR1에서 수정됨
   - 제품 버그 : PR2 후보로 기록됨
   - 레거시 린트 부채: `RUMI_FULL_QUALITY=1`로 감지하고 점진적인 상환 계획 수립

---

## 7. 출시 전 확인

1. `.github/workflows/test.yml` 및 `release.yml`은 현재 운영과 일치합니다.
2. 추가 테스트는 녹색입니다.
3. 감사/문제 해결 절차가 최신 상태입니다.
4. 보안 모드(엄격/허용)에 대한 설명이 일관됩니다.
5. 루트 README 및 `rumi_ai_1_10/README.md` 링크가 유효합니다.

---

## 8. 이념 호환성 체크리스트

- [ ] 공식 코어에서는 특정 도메인 전제 조건 논리가 증가되지 않았습니다(선호도 없음).
- [ ] 부분적인 고장(Fail-Soft) 시에도 연속운전이 중단되지 않습니다.
- [ ] 악성팩에 따른 승인, 검증, 격리가 약화되지 않습니다.
- [ ] 외부 통신 및 위험한 작업은 기능 외부로 전환되지 않습니다.
- [ ] 감사 로그에서 추적 가능한 구현을 유지합니다.

---

## 9. 장애 발생 시 격리 절차

1. 어떤 게이트가 실패했는지 분류
   - 루트 pytest / 패키지 pytest / ruff / mypy / 프론트엔드 lint-build / 화물 테스트
2. 최소한의 재현
   - 단일 테스트 파일 또는 단일 명령으로 축소
3. 원인 분류
   - 구성 불일치
- 부적절한 테스트 가정
   - 제품 버그(PR2용)
4. 영향평가
   - 심각도(높음/중간/낮음)
   - 재현성(상수/조건부)
- 사용자 영향(보안/데이터/UX)

---

## 10. AI 에이전트 작업 프롬프트(작업 템플릿)

처음에 다음을 추가하여 작동하십시오.

```text
README・docs・思想メモを先に読み、No Favoritism / Fail-Soft / 悪意前提 / 最小権限を判断基準にする。
PR1では品質資産のみ、PR2で実害バグを修正する。
失敗時はテスト不備と製品バグを分離し、製品バグは再現条件と優先度付きで記録する。
全検証コマンドを実行し、結果をコマンド単位で報告する。
```

---

## 11. 알려진 PR2 후보자 기록 템플릿

```text
- 事象:
- 再現手順:
- 期待挙動:
- 実際の挙動:
- 重大度:
- 再現性:
- ユーザー影響:
- 思想逸脱:
```
