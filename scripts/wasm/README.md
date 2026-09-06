# Shell Policy Wasm migration

The first candidate is `rumi_shell_policy_pack`: its command classification is
pure computation. The Host still owns authorization and command execution.
Native/OS workloads retain their existing VM or Host-brokered execution.

Install `componentize-py==0.25.0` and `wasmtime==48.0.0` in an isolated Python
environment, then run its Python interpreter:

```sh
python scripts/wasm/build_shell_policy.py --output /tmp/tobkiri-wasm/policy.wasm
```

The builder copies the canonical policy source, generates the WIT bindings,
builds with `--stub-wasi`, and rejects any remaining component imports. It does
not inherit user credentials or HOME during build-time initialization. Its
`.build.json` records source, adapter, WIT, output digests and tool versions.
The command is repeatable; binary identity is recorded per build rather than
assuming byte-for-byte reproducibility of the Python preinitialization image.

No filesystem, network, environment, or process interfaces are linked into this
component. Trapping WASI stubs are appropriate here because classification does
not need randomness; they must not be reused for secret/token generation.
Home paths are classified lexically without consulting an OS user database.

This is a migration artifact. It is not installed as an active Pack, registered
as a production execution backend, or evidence of complete sandbox acceptance.
Production integration still requires the existing artifact/Authority/Broker
checks, worker resource accounting, cancellation and exact domain binding.
Do not change a Pack's selected execution kind until that path is verified.

The initial native/guest comparison covered 66 cases (including home paths),
with no imports and working fuel/memory rejection. CPython component compilation
used roughly 0.5–0.7 GiB resident/peak memory locally, so this result does not yet
establish a memory advantage over VM execution.

`tobkiri_runtime/tobkiri_host/wasm_component.py` supplies the worker's private
engine. It verifies the input digest, rejects all imports, uses Pulley with fuel
and epoch interruption, limits the guest to one 128 MiB memory, and consumes
each engine for one request only. It does not bound compilation memory or start
an isolated worker itself. Those remain supervisor responsibilities.

With Wasmtime 48.0.0 and pytest installed in the test environment, run from
`tobkiri_runtime/`:

```sh
python -B -m pytest tests/test_wasm_component.py -q
```

These tests execute real components, including an infinite loop interrupted by
cancellation. The suite skips when Wasmtime is absent; a skip is not engine
validation. Before production registration, the supervisor must implement the
`RequestScopedBackend` cleanup contract: it confirms worker exit before Broker
releases the reservation, including failed starts and denied authorization.
If exit cannot be confirmed, the reservation remains charged and the request is
fenced. Concurrent reservations cannot share materialization evidence.

References: [Wasmtime sandboxing](https://docs.wasmtime.dev/security.html) and
[componentize-py](https://github.com/bytecodealliance/componentize-py).
