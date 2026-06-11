<!-- docs-i18n-links:start -->
[EN](./vision_bridge.md) | [JP](./i18n/ja/vision_bridge.md) | [KR](./i18n/ko/vision_bridge.md) | [CN](./i18n/zh-cn/vision_bridge.md)
<!-- docs-i18n-links:end -->

# Vision Bridge

Vision Bridge lets a non-vision primary model continue a conversation with images. A vision-capable utility model creates structured image understanding, then defaultspack inserts the summary, OCR text, relevant details, and uncertainties as text context.

Conversation metadata stores `conversation_image_context` so the same image context can be reused when switching to a non-vision model.
