<!-- docs-i18n-links:start -->
[EN](../../defaultspack_authoring.md) | [JP](../ja/defaultspack_authoring.md) | [KR](./defaultspack_authoring.md) | [CN](../zh-cn/defaultspack_authoring.md)
<!-- docs-i18n-links:end -->

# Defaultspack 저작

Defaultspack 리소스는 구성 요소, 블록, 함수, 흐름, 프롬프트, 노드 및 그래프로 작성됩니다.

블록은 `ecosystem/defaultspack/blocks/` 아래에 있으며 `run(input_data, context)`을 노출합니다. 기능은 `functions/<function_id>/manifest.json`에 따라 실시간으로 나타납니다. 생성된 래퍼는 defaultspack 함수 디스패처를 호출합니다. 구성 요소는 `components/*/manifest.json` 및 `ecosystem.json`에서 호출 가능한 별칭을 광고합니다.

프로필 스냅샷은 참조된 흐름, 프롬프트, 노드 및 블록 리소스만 복사해야 합니다. 소스 경로와 SHA-256 해시를 사용하여 `manifest.lock.json`을 작성하므로 프로필 편집 및 defaultspack 업데이트를 설명할 수 있습니다.
