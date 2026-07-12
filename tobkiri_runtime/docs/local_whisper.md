# Local Whisper Transcription

Rumi can run ambient speech transcription locally through `whisper.cpp`.

The balanced default is `ggml-base.bin`. Rumi prefers an installed
`ggml-small.bin` for higher quality, then `ggml-base.bin`, and finally keeps
`ggml-tiny.bin` as a speed-first compatibility fallback.

Expected packaged layout:

```text
bundled/
  whisper/
    macos-aarch64/
      whisper-cli
    models/
      ggml-base.bin
```

The detector also accepts:

- `bundled/whisper/bin/whisper-cli`
- `bundled/bin/whisper-cli`
- `bundled/models/whisper/ggml-small.bin`, `ggml-base.bin`, or `ggml-tiny.bin`
- the app-data model path returned by `scripts/setup_local_whisper.py`

License/source summary checked for this integration:

- `whisper.cpp`: MIT License
- OpenAI Whisper code and model weights: MIT License
- `ggerganov/whisper.cpp` GGML model conversions on Hugging Face: MIT License

Rumi does not commit model binaries in this repository. Build/package steps may
place `whisper-cli` and a compatible GGML model in the layout above. Users can
install the balanced default explicitly:

```bash
python scripts/setup_local_whisper.py --download-model --model-size base --print-license
```

For better recognition on machines with sufficient memory and CPU/GPU budget:

```bash
python scripts/setup_local_whisper.py --download-model --model-size small --print-license
```

The faster-whisper path uses beam search, VAD, a configured language hint, and
deterministic decoding. Model or engine downloads never happen during app
startup; downloads remain explicit through the setup command or the existing
opt-in environment flag.

Audio stays local. Temporary input and conversion files are removed after each
transcription. The ambient audit log stores trigger metadata and transcription
status only, not raw audio or transcript text.
