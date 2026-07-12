# Rumi Ambient Trigger Pack

This pack connects voice wake, camera pinch, and external hook triggers to the
defaultspack input dispatcher through a shared ambient trigger layer.

It does not mutate model profiles or provider selection. Ambient events are
submitted as normal defaultspack input envelopes, so the active conversation,
profile, and tool policy remain the same unless the user explicitly changes
them elsewhere.

The pack is opt-in and high-risk. It requests Rumi-side permissions for
`host.microphone.capture`, `host.camera.capture`, and `ambient.trigger.dispatch`, and it
keeps those grants separate from OS microphone/camera permission status.

Gesture inputs:

- thumb/index hold records audio; release dispatches that recording
- thumb/index plus stable 2, 3, or 4 fingers for 3 seconds dispatches `2`, `3`,
  or `4` as a chat reply without audio
- approval windows can map 2/3 button choices without thumb/index contact
- index-only horizontal swipe rejects; index-only vertical swipe approves

Privacy defaults:

- raw microphone audio is not stored
- camera frames and images are not stored
- hand landmarks are local-only short-lived data
- only trigger audit events are written
