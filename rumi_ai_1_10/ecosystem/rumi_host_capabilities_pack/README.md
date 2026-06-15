# Rumi Host Capabilities Pack

`rumi_host_capabilities_pack` owns the local host capability boundary.
Defaultspack may request, display, approve, and route host intents, but it must not
execute host operations itself.

Host-touching functions return typed `host_intent` or `host_stream_intent`
payloads. The Viewer/host broker validates the intent, checks Authority, binds
the approval token to the operation, caller, args hash, and stream settings, and
then performs the OS-specific action.

`host.process.exec_guarded` is intentionally excluded from the default grant set.
It requires a one-shot Authority request with typed confirmation.
