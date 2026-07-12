# Defaultspack Authoring

Defaultspack resources are authored as components, blocks, functions, flows, prompts, nodes, and graphs.

Blocks live under `ecosystem/defaultspack/blocks/` and expose `run(input_data, context)`. Function manifests live under `functions/<function_id>/manifest.json`; generated wrappers call the defaultspack function dispatcher. Components advertise callable aliases in `components/*/manifest.json` and `ecosystem.json`.

Profile snapshots must copy only referenced flow, prompt, node, and block resources. They write `manifest.lock.json` with source paths and SHA-256 hashes so profile edits and defaultspack updates remain explainable.
