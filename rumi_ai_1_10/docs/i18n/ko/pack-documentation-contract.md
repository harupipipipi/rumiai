<!-- docs-i18n-links:start -->
[EN](../../pack-documentation-contract.md) | [JP](../ja/pack-documentation-contract.md) | [KR](./pack-documentation-contract.md) | [CN](../zh-cn/pack-documentation-contract.md)
<!-- docs-i18n-links:end -->

# Pack Documentation Contract

Pack 고유 docs를 `ecosystem/<pack_id>/docs/`에 집약하기 위한 공통 규약입니다.

## Responsibility Split

`rumi_ai_1_10/docs/`는 runtime 공통 docs와 Pack 공통 규칙만 넣습니다.

- kernel, flow, approval, grant 등 runtime 공통 설명
- Pack을 만드는 방법
- docs 약관

`ecosystem/<pack_id>/docs/`는 해당 팩 관련 설명만 넣습니다.

- Pack의 책임
- 실장 구조
- flows/functions/handlers/routes
- 운영 방법
- 제약

root docs는 Pack 본문을 설명하지 않습니다. Pack에 대한 입구 링크와 공통 약관만 있습니다.

## Required Files

각 팩에는 최소한 다음이 있습니다.

- `ecosystem/<pack_id>/README.md`
- `ecosystem/<pack_id>/docs/README.md`
- `ecosystem/<pack_id>/docs/architecture.md`
- `ecosystem/<pack_id>/docs/interfaces.md`
- `ecosystem/<pack_id>/docs/operations.md`

각 파일의 책임 :

- `README.md`: 3분에서 알 수 있는 개요, 제공하는 것, 제공하지 않는 것,docs의 입구
- `docs/README.md`: pack 내의 docs의 목차, 읽는 방법 가이드, 초보용 도선
- `docs/architecture.md`: 책임, 주요 디렉토리, 실행 경로, 런타임과의 접촉
- `docs/interfaces.md`: flows / functions / handlers / routes / events / stores / required secrets / network / grants
- `docs/operations.md`: 기동방법, 개발방법, 테스트방법, 흔한 파손방법, 변경시 확인 관점

## Conditionally Required Files

해당 기능을 가진 팩은 추가 docs를 넣습니다.

- `docs/flows.md`: flow / modifier를 가질 때

## Cross-Link Rules

- root docs에서 팩을 설명할 때는 짧은 소개와 입구 링크에 둡니다.
- Pack 고유의 설명은 `ecosystem/<pack_id>/docs/README.md`에 링크한다
- Pack 내 개별 doc 는, 필요하다면 `docs/README.md` 에서 추적할 수 있도록 한다

## PR Rule

다음 변경에서는 docs 업데이트가 필요합니다.

- 새로운 flow / modifier 를 늘렸다
- 새로운 function / handler / route 를 늘렸다
- required secrets / grants / network 가 바뀌었다
- 기동방법이나 운용방법이 바뀌었다
- 팩의 책임이 바뀌었다.

## Scaffold Expectation

`pack_scaffold` 는 contract 의 필수 docs 를 토하는 상태를 유지합니다. 새 팩을 만들 때 README와 `docs/README.md` / `architecture.md` / `interfaces.md` / `operations.md`가 자연스럽게 정렬되도록 합니다.
