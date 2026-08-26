# Computer Host / Tool Boundary

## Purpose

Computer Use has two different responsibilities that must remain separate:

1. the native host touches a macOS, Windows, Linux, browser, or isolated desktop surface;
2. a Rumi tool defines the model-facing action contract and decides how that host capability is used.

The host is infrastructure. `computer_use` is one consumer of that infrastructure, not the host itself.

## Ownership

### Native host layer

The host layer owns operating-system and runtime integration:

- surface, process, window, and tab discovery;
- screenshots and accessibility/DOM observations;
- native semantic actions and input transports;
- coordinate conversion;
- host permission acquisition;
- execution evidence and postcondition observations.

A host must not depend on model names, provider profiles, prompt text, or public tool schemas. macOS and Windows implementations should expose the same host protocol even when their internal transports differ.

### Tool and pack layer

The tool layer owns:

- public JSON schemas and normalized action names;
- inspect/act/verify workflow policy;
- approval and audit integration;
- fallback and retry policy;
- user-facing recovery messages;
- app-specific semantic actions;
- profile and feature-bundle integration.

This allows another pack to implement Electron-, Tauri-, VS Code-, Office-, or application-specific tools while reusing the same native host.

## Runtime seam

`defaultspack.domain.host_bridge.computer_host.ComputerHost` is the model-agnostic execution seam. The current adapters are:

- `ViewerBrokerComputerHost`: native execution through the Rumi Viewer host broker;
- `LocalControllerComputerHost`: compatibility adapter around the existing in-process controller.

`computer_router.run_computer_action()` accepts an injected `ComputerHost`. This keeps approval and audit behavior in defaultspack while allowing tests and future tools to use a fake or app-specific host without importing platform drivers.

```text
profile / agent / app-specific pack
        |
        v
model-facing tool
        |
        v
defaultspack computer router
  approval / audit / target context
        |
        v
ComputerHost
        |
        +-- Rumi Viewer native host
        +-- Windows native host
        +-- Linux or isolated seat
        +-- app-specific host adapter
```

## Provider profiles

Provider profiles transform inbound and outbound messages only. A profile such as `line.computer_use` may enable a shared Computer Use feature, but LINE does not own the Computer Use architecture or native host.

## Migration rules

1. Keep the existing public `computer_use` behavior stable while routing it through `ComputerHost`.
2. Treat `browser_computer` as a compatibility alias rather than a second host implementation.
3. Move direct operating-system imports behind host adapters.
4. Let tools and packs define higher-level semantics without adding another macOS or Windows driver.
5. Expand host results to distinguish delivery, observed effect, and verified postcondition.
6. Bind actions to a surface identity and observation revision before enabling broad background control.
