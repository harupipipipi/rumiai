# Architecture

Voice wake, camera pinch, and optional LINE/Discord/Web hook triggers produce an
`AmbientTriggerEvent`.

```text
voice / gesture / hook
  -> AmbientTriggerEvent
  -> Rumi permission check
  -> debounce / cooldown
  -> ambient_trigger_router
  -> RumiInputEnvelope
  -> submit_input / dispatch_input
```

The router enforces `ambient_monitor.enabled`; mic and camera events are ignored
while monitoring is off.

Camera pinch is a hold-to-record gesture: thumb/index contact emits
`record_audio_start`, records microphone audio in memory only, and the release
emits `dispatch_audio` with an ephemeral audio attachment. The recording is sent
to the active AI input path and is not persisted to workspace attachments or
ambient audit logs.
