# Ambient Trigger System Policy

Ambient triggers may open input or dispatch user-approved input, but they must
not directly run autonomous work without passing through `ambient_trigger_router`
and the defaultspack input dispatcher.

Voice wake must use enrolled audio embeddings or local classifier evidence.
String or transcript-only wake matching is not allowed.
