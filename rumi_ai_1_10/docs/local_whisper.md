# Local Whisper Transcription

Rumi can run ambient speech transcription locally through `whisper.cpp`.

Expected packaged layout:

```text
bundled/
  whisper/
    macos-aarch64/
      whisper-cli
    models/
      ggml-tiny.bin
```

The detector also accepts:

- `bundled/whisper/bin/whisper-cli`
- `bundled/bin/whisper-cli`
- `bundled/models/whisper/ggml-tiny.bin`
- the app-data model path returned by `scripts/setup_local_whisper.py`

License/source summary checked for this integration:

- `whisper.cpp`: MIT License
- OpenAI Whisper code and model weights: MIT License
- `ggerganov/whisper.cpp` GGML model conversions on Hugging Face: MIT License

Rumi does not commit model binaries in this repository. Build/package steps may
place `whisper-cli` and `ggml-tiny.bin` in the layout above, or users may run:

```bash
python scripts/setup_local_whisper.py --download-model --print-license
```

Audio stays local. The ambient audit log stores trigger metadata and
transcription status only, not raw audio.
