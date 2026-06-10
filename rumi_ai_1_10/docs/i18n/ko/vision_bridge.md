<!-- docs-i18n-links:start -->
[EN](../../vision_bridge.md) | [JP](../ja/vision_bridge.md) | [KR](./vision_bridge.md) | [CN](../zh-cn/vision_bridge.md)
<!-- docs-i18n-links:end -->

# 비전브릿지

Vision Bridge를 사용하면 비비전 기본 모델이 이미지와 대화를 계속할 수 있습니다. 비전 지원 유틸리티 모델은 구조화된 이미지 이해를 생성한 다음 defaultspack이 요약, OCR 텍스트, 관련 세부 정보 및 불확실성을 텍스트 컨텍스트로 삽입합니다.

대화 메타데이터는 `conversation_image_context`를 저장하므로 비비전 모델로 전환할 때 동일한 이미지 컨텍스트를 재사용할 수 있습니다.
