# Vendored frontend assets

Defaultspack keeps the ambient hand tracking assets local-first. The webapp
loads them from `webapp/public/` in development, and `npm run build` copies the
same public assets into the packaged `ui/` directory via Vite.

Run this check after updating MediaPipe or rebuilding packaged UI assets:

```bash
cd rumi_ai_1_10/ecosystem/defaultspack/webapp
npm run check:vendored-assets
```

CI runs the stricter packaged check after `npm run build`:

```bash
npm run check:vendored-assets -- --require-ui
```

That mode requires both `webapp/public/` and the generated packaged `ui/`
copies to exist and match the recorded hashes.
The checker normalizes JavaScript asset line endings to LF before hashing so
Windows checkouts do not report false drift for text assets.

## MediaPipe hand tracking

- WASM runtime: `@mediapipe/tasks-vision@0.10.35`
- Package integrity: `sha512-HOvadwVRE6JC+45nyYhmnywnr5h/J8KZvOeUNVOG9q/0875pZgItznFB9bRTvLc264YSJqiZ1NsIpCStJw/egg==`
- Package license: Apache-2.0
- MediaPipe license reference: `https://github.com/google-ai-edge/mediapipe/blob/master/LICENSE`
- Model: `https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/1/hand_landmarker.task`
- Model provenance: MediaPipe hand landmarker model distributed for MediaPipe Tasks.

| Asset | SHA-256 |
| --- | --- |
| `mediapipe/wasm/vision_wasm_internal.js` | `11fdcbe35b15e222bd60f02c1be7e5f8dd8a73721a0a55cf8adcf38b88977b9e` |
| `mediapipe/wasm/vision_wasm_internal.wasm` | `6a5c64584c2ab61c763b6e204afbdbc7ce1caf7f5216187322bca8df94f646bc` |
| `mediapipe/wasm/vision_wasm_module_internal.js` | `e23be0c990685926cc0a13a46936015527f36e95adf965250ea08d3b9fd28ef2` |
| `mediapipe/wasm/vision_wasm_module_internal.wasm` | `617b8e0248dbd27e9d7ece4218004eae4cefb499196d1bb4fa0e3fef21708756` |
| `mediapipe/wasm/vision_wasm_nosimd_internal.js` | `df375e4da93bbc1078481da6e2e519fd55ea125a14a00379a9b7bb395fb56c80` |
| `mediapipe/wasm/vision_wasm_nosimd_internal.wasm` | `8a3092d34c79d3f57e6ba8592105e8a90f6b07c27891ffecd14cca428bfd3e31` |
| `models/hand_landmarker.task` | `fbc2a30080c3c557093b5ddfc334698132eb341044ccee322ccf8bcf3607cde1` |
