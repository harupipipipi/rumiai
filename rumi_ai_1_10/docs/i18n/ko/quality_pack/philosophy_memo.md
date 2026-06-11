<!-- docs-i18n-links:start -->
[EN](../../../quality_pack/philosophy_memo.md) | [JP](../../ja/quality_pack/philosophy_memo.md) | [KR](./philosophy_memo.md) | [CN](../../zh-cn/quality_pack/philosophy_memo.md)
<!-- docs-i18n-links:end -->

# rumi_ai 사상 메모(개발 판단 기준)

## 1. 목적

rumi_ai는 "채팅 및 도구가 내장 된 앱"이 아니라 **Flow 실행, 승인, 격리, 권한 및 감사**를 제공하는 실행 기반입니다. 공식 코어는 특정 도메인에 최선을 다하지 않으며 기능은 Pack이 담당합니다 (No Favoritism).

## 2. 사용자 경험(UX) 목표

사용자는 Pack을 안전하게 추가하면서 전체 시스템을 멈추지 않고 운영할 수 있어야 합니다. 깨진 팩은 무효화하고 감사 로그와 진단으로 상태를 추적하는 것 (Fail-Soft + Observability)을 UX의 핵심으로 만듭니다.

## 3. 안전 설계의 핵심

1. **악의 Pack 전제**: 미승인 Pack은 실행 불가, 승인 후에도 해시 불일치로 자동 무효화.
2. **검역 실행**: strict 모드에서는 Docker 필수, Pack은 원칙 `--network=none`.
3. **최소 권한**: 외부 통신이나 호스트 권한은 Capability(Trust + Grant) 경유만.
4. **감사 가능성**: 권한 조작, 통신, 실행 결과를 감사 로그에 남겨 추적 가능하게 한다.

## 4. 품질 기준

1. **계속 검증 가능**: pytest / cargo test / lint / typecheck / build 를 반복 가능한 형태로 유지.
2. **회귀 내성**: 기존 기능을 파괴하지 않는 계약 테스트(CLI·설정·CI·보안 경계)를 가진다.
3. **운용 용이성**: 실패 시의 분리 절차, 수동 검증, 릴리스 전 체크를 문서화.
4. **사상 정합**: 변경이 No Favoritism / Fail-Soft / 악의 전제 / 최소 권한에 반하지 않는지 확인.

## 5. 변경 판단 규칙(이 작업에서 사용)

1. PR1은 **품질 자산만**(테스트, 검증 스크립트, 체크리스트, 감사 절차, 운영 문서)을 추가하고 제품 거동은 변경하지 않는다.
2. PR2는 PR1에서 검출한 결함 중 사용자 영향·재현성·사상 일탈이 높은 것을 우선하여 수정한다.
3. 헤매면 「안전측」 「감사 가능」 「회귀하기 어렵다」 선택을 우선한다.
