# Rumi Ambient Trigger Pack

This pack connects voice wake, camera pinch, and external hook triggers to the
defaultspack input dispatcher through a shared ambient trigger layer.

The pack is opt-in and high-risk. It requests Rumi-side permissions for
`microphone.capture`, `camera.capture`, and `ambient.trigger.dispatch`, and it
keeps those grants separate from OS microphone/camera permission status.

Privacy defaults:

- raw microphone audio is not stored
- camera frames and images are not stored
- hand landmarks are local-only short-lived data
- only trigger audit events are written
