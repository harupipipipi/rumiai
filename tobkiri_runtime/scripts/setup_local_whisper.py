#!/usr/bin/env python3
"""Explicit helper for configuring Rumi's local Whisper transcription.

This script is intentionally opt-in. It never runs from app startup and it does
not add Python package dependencies. On macOS it can install whisper.cpp through
Homebrew when --install-brew is provided, and it can download an explicitly
selected GGML model when --download-model is provided.

License note: whisper.cpp, OpenAI Whisper code, and OpenAI Whisper model
weights are MIT licensed. The default model URL points at the MIT-licensed
ggerganov/whisper.cpp GGML conversion repository.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULTSPACK_ROOT = ROOT / "ecosystem" / "defaultspack"
if str(DEFAULTSPACK_ROOT) not in sys.path:
    sys.path.insert(0, str(DEFAULTSPACK_ROOT))

from domain.ambient.local_transcription import (  # noqa: E402
    default_local_whisper_model_path,
    local_whisper_status,
)


DEFAULT_MODEL_URL_TEMPLATE = "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-{model_size}.bin"
DEFAULT_MODEL_LICENSE = "MIT"
DEFAULT_MODEL_SOURCE = "https://huggingface.co/ggerganov/whisper.cpp"


def main() -> int:
    parser = argparse.ArgumentParser(description="Set up local whisper.cpp for Rumi ambient STT.")
    parser.add_argument(
        "--install-brew",
        action="store_true",
        help="Install whisper-cpp with Homebrew.",
    )
    parser.add_argument(
        "--download-model",
        action="store_true",
        help="Download the selected GGML model (explicit opt-in).",
    )
    parser.add_argument(
        "--model-size",
        choices=("tiny", "base", "small"),
        default="base",
        help="Local model quality/speed tier. Default: base.",
    )
    parser.add_argument(
        "--model-url",
        default="",
        help="Override the GGML model URL to download.",
    )
    parser.add_argument("--model-path", default="", help="Override destination model path.")
    parser.add_argument(
        "--print-env",
        action="store_true",
        help="Print shell exports for this setup.",
    )
    parser.add_argument(
        "--print-license",
        action="store_true",
        help="Print the local Whisper license/source summary.",
    )
    args = parser.parse_args()

    if args.install_brew:
        if not shutil.which("brew"):
            print(
                "Homebrew was not found. Install Homebrew first or set WHISPER_CPP_BIN manually.",
                file=sys.stderr,
            )
            return 2
        subprocess.run(["brew", "install", "whisper-cpp"], check=True)

    model_path = (
        Path(args.model_path).expanduser()
        if args.model_path
        else default_local_whisper_model_path(args.model_size)
    )
    model_url = args.model_url or DEFAULT_MODEL_URL_TEMPLATE.format(model_size=args.model_size)
    if args.download_model:
        model_path.parent.mkdir(parents=True, exist_ok=True)
        if not model_path.exists():
            print(f"Downloading {model_url} -> {model_path}")
            print(f"Model source: {DEFAULT_MODEL_SOURCE} ({DEFAULT_MODEL_LICENSE})")
            urllib.request.urlretrieve(model_url, model_path)
        else:
            print(f"Model already exists: {model_path}")

    status = local_whisper_status()
    print(json.dumps(status, ensure_ascii=False, indent=2))

    if args.print_license:
        print()
        print("Local Whisper license/source:")
        print("- Engine: whisper.cpp (MIT)")
        print("- Original code/model weights: OpenAI Whisper (MIT)")
        print(f"- Default GGML model source: {DEFAULT_MODEL_SOURCE} ({DEFAULT_MODEL_LICENSE})")

    if args.print_env:
        command = status.get("command") or shutil.which("whisper-cli") or ""
        print()
        if command:
            print(f'export WHISPER_CPP_BIN="{command}"')
        print(f'export WHISPER_CPP_MODEL="{model_path}"')
        ffmpeg = status.get("ffmpeg") or shutil.which("ffmpeg") or ""
        if ffmpeg:
            print(f'export FFMPEG_BIN="{ffmpeg}"')

    return 0 if status.get("configured") else 1


if __name__ == "__main__":
    raise SystemExit(main())
