# Composer mention metadata

The defaultspack composer keeps the human-facing spelling of a selected
mention in message text. Stable catalog identifiers are carried separately in
the message `metadata.mentions` array and in the existing tool-selection
request. Normal chat UI must not substitute tool or skill identifiers for the
selected label.

Each semantic mention records an `id`, `kind`, localized `label`, and the exact
human-facing `syntax` inserted into the composer. The supported kinds are
`tool`, `skill`, `service`, and `file`. Duplicate labels remain safe because
selection metadata, rather than text reparsing, owns the stable identifier.

History rendering treats metadata as active only when its exact syntax is
still present unescaped in visible message text. This preserves badges across
reload while keeping email addresses and escaped forms such as
`\@Browser Computer` literal. Older messages may reconstruct the same public
metadata from semantic `dropped_widgets`, but only when the visible syntax is
still active.

Mention metadata is presentation and selection context. It does not grant
tool authority, bypass approval, select a Pack outside the resolved catalog,
or create a host-execution fallback. Runtime execution continues through the
resolved ProfileLock/ResolvedPlan and PackVM authority paths.
