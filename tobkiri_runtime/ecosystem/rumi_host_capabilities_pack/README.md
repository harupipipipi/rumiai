# Rumi Host Capabilities Pack

`rumi_host_capabilities_pack` owns the local host capability boundary.
Defaultspack may request, display, approve, and route host intents, but it must not
execute host operations itself.

Only operations with `broker_runner_implemented: true` in
`core_runtime/host_permissions/default_registry.json` are advertised by this
pack. The current broker runners are limited to `host.permission.status` and
`host.permission.open_settings`; media capture and process/file/input operations
must stay out of the catalog until the Viewer has real runners for them.

Host-touching functions return typed `host_intent` payloads. The Viewer/host
broker validates the intent, checks Authority, binds the approval token to the
operation, caller, and args hash, and then performs the OS-specific action.

## Generated mediator wrappers

Function `main.py` wrappers under `functions/*/` are generated only for
implemented broker runners. They deliberately remain thin so each advertised
FunctionRegistry entry keeps its stable function id while sharing the same
host-intent mediator.

Check or refresh the wrappers after changing host permissions:

```bash
cd tobkiri_runtime/ecosystem/rumi_host_capabilities_pack
python scripts/generate_host_mediator_functions.py --check
python scripts/generate_host_mediator_functions.py --write
```
