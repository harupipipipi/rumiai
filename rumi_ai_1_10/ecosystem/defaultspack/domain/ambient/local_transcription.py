from __future__ import annotations

import base64
import binascii
import importlib.util
import os
import platform
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence


COMMAND_ENV_KEY = "RUMI_LOCAL_WHISPER_COMMAND"
BINARY_ENV_KEYS = ("RUMI_WHISPER_CPP_BIN", "WHISPER_CPP_BIN")
MODEL_ENV_KEYS = (
    "RUMI_LOCAL_WHISPER_MODEL",
    "WHISPER_CPP_MODEL",
    "RUMI_WHISPER_MODEL_PATH",
)
ALLOW_DOWNLOAD_ENV_KEYS = ("RUMI_LOCAL_WHISPER_ALLOW_DOWNLOAD", "RUMI_WHISPER_ALLOW_DOWNLOAD")
COMMON_COMMANDS = ("whisper-cli", "whisper.cpp", "whisper-cpp", "whisper")
FFMPEG_ENV_KEYS = ("RUMI_FFMPEG_BIN", "FFMPEG_BIN")
LOCAL_WHISPER_DIR_ENV = "RUMI_LOCAL_WHISPER_DIR"
DEFAULT_MODEL_SIZE = "base"
MODEL_FILENAMES = (
    "ggml-small.bin",
    "ggml-base.bin",
    "ggml-tiny.bin",
)
DEFAULT_MODEL_FILENAME = f"ggml-{DEFAULT_MODEL_SIZE}.bin"
APP_DATA_DIR_NAME = "dev.rumiai.app"
DEFAULT_TIMEOUT_SECONDS = 45
WHISPER_CPP_SUPPORTED_SUFFIXES = {".wav", ".mp3", ".ogg", ".flac"}


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str = ""
    stderr: str = ""


def transcribe_local_audio(
    audio_payload: str,
    *,
    mime_type: str = "",
    language: str = "",
    prompt: str = "",
    timeout_seconds: int | float | None = None,
) -> dict[str, Any]:
    audio_bytes = _decode_audio_payload(audio_payload)
    if not audio_bytes:
        return _unavailable(
            "audio_payload_invalid",
            "音声データを読み取れませんでした。",
        )

    suffix = _audio_suffix(mime_type)
    timeout = _coerce_timeout(timeout_seconds)
    audio_path: Path | None = None
    try:
        fd, path = tempfile.mkstemp(prefix="rumi-ambient-audio-", suffix=suffix)
        audio_path = Path(path)
        with os.fdopen(fd, "wb") as handle:
            handle.write(audio_bytes)
        return _transcribe_audio_file(
            audio_path,
            language=str(language or "").strip(),
            prompt=str(prompt or "").strip(),
            timeout_seconds=timeout,
        )
    finally:
        if audio_path is not None:
            _unlink_quietly(audio_path)


def _transcribe_audio_file(
    audio_path: Path,
    *,
    language: str,
    prompt: str,
    timeout_seconds: int | float,
) -> dict[str, Any]:
    env = os.environ
    model = _configured_model(env)
    attempts: list[dict[str, str]] = []

    with tempfile.TemporaryDirectory(prefix="rumi-ambient-stt-") as output_dir_raw:
        output_dir = Path(output_dir_raw)
        command = _configured_command(env)
        if command is not None:
            result = _run_command_candidate(
                command,
                audio_path=audio_path,
                output_dir=output_dir,
                model=model,
                language=language,
                prompt=prompt,
                timeout_seconds=timeout_seconds,
            )
            if result.get("status") == "ok":
                return result
            attempts.append(_attempt_summary(result))
        else:
            command_missing_reason = "local_whisper_command_missing"

        if _has_python_module("faster_whisper"):
            if _library_model_allowed(model):
                result = _run_faster_whisper(
                    audio_path,
                    model=str(model or ""),
                    language=language,
                    prompt=prompt,
                )
                if result.get("status") == "ok":
                    return result
                attempts.append(_attempt_summary(result))
            else:
                attempts.append(
                    {
                        "engine": "faster_whisper",
                        "code": "local_whisper_model_missing",
                        "reason": "local model path missing",
                    }
                )

        if _has_python_module("whisper"):
            if _library_model_allowed(model):
                result = _run_openai_whisper_library(
                    audio_path,
                    model=str(model or ""),
                    language=language,
                    prompt=prompt,
                )
                if result.get("status") == "ok":
                    return result
                attempts.append(_attempt_summary(result))
            else:
                attempts.append(
                    {
                        "engine": "whisper",
                        "code": "local_whisper_model_missing",
                        "reason": "local model path missing",
                    }
                )

    missing_model_codes = {"local_whisper_model_missing", "local_whisper_not_configured"}
    if not model and any(item.get("code") in missing_model_codes for item in attempts):
        return _unavailable(
            "local_whisper_not_configured",
            (
                "ローカルWhisperが未設定です。RUMI_LOCAL_WHISPER_MODEL または "
                "WHISPER_CPP_MODEL を設定してください。"
            ),
            attempts=attempts[-5:],
        )
    if attempts:
        return _unavailable(
            "local_whisper_failed",
            "ローカルWhisperで文字起こしできませんでした。",
            attempts=attempts[-5:],
        )
    return _unavailable(
        "local_whisper_not_configured",
        (
            "ローカルWhisperが未設定です。RUMI_LOCAL_WHISPER_COMMAND または "
            "WHISPER_CPP_BIN と RUMI_LOCAL_WHISPER_MODEL を設定するか、"
            "文字起こし対応プロバイダを使用してください。"
        ),
        attempts=[
            {
                "engine": command_missing_reason,
                "code": "local_whisper_not_configured",
                "reason": "no local engine found",
            }
        ],
    )


def local_whisper_status() -> dict[str, Any]:
    env = os.environ
    command = _configured_command(env)
    model = _configured_model(env)
    ffmpeg = _configured_ffmpeg(env)
    configured = bool(command and model)
    return {
        "status": "local_whisper_configured" if configured else "local_whisper_not_configured",
        "configured": configured,
        "command": str((command or {}).get("command") or ""),
        "command_label": str((command or {}).get("label") or ""),
        "model": str(model or ""),
        "model_quality": _model_quality(model),
        "ffmpeg": ffmpeg,
        "can_convert_audio": bool(ffmpeg),
        "reason": "" if configured else _local_whisper_missing_reason(command=command, model=model),
    }


def default_local_whisper_model_dir() -> Path:
    override = str(os.environ.get(LOCAL_WHISPER_DIR_ENV) or "").strip()
    if override:
        return Path(override).expanduser()
    if os.name == "posix" and Path.home().anchor == "/":
        mac_app_support = Path.home() / "Library" / "Application Support"
        if mac_app_support.exists() or str(os.uname().sysname).lower() == "darwin":
            return mac_app_support / APP_DATA_DIR_NAME / "models" / "whisper"
    xdg_data = str(os.environ.get("XDG_DATA_HOME") or "").strip()
    if xdg_data:
        return Path(xdg_data).expanduser() / APP_DATA_DIR_NAME / "models" / "whisper"
    return Path.home() / ".local" / "share" / APP_DATA_DIR_NAME / "models" / "whisper"


def default_local_whisper_model_path(model_size: str = DEFAULT_MODEL_SIZE) -> Path:
    normalized = str(model_size or DEFAULT_MODEL_SIZE).strip().lower()
    if normalized not in {"tiny", "base", "small"}:
        normalized = DEFAULT_MODEL_SIZE
    return default_local_whisper_model_dir() / f"ggml-{normalized}.bin"


def _configured_command(env: os._Environ[str]) -> dict[str, str] | None:
    custom = str(env.get(COMMAND_ENV_KEY) or "").strip()
    if custom:
        return {"kind": "custom", "command": custom, "label": "command"}
    for key in BINARY_ENV_KEYS:
        value = str(env.get(key) or "").strip()
        if value:
            return {
                "kind": _command_kind(value),
                "command": value,
                "label": Path(value).name or value,
            }
    for path in _bundled_command_candidates(env):
        if _is_executable_file(path):
            return {
                "kind": _command_kind(path.name),
                "command": str(path),
                "label": path.name,
            }
    for name in COMMON_COMMANDS:
        path = shutil.which(name)
        if path:
            return {"kind": _command_kind(name), "command": path, "label": name}
    for path in _well_known_command_candidates():
        if _is_executable_file(path):
            return {
                "kind": _command_kind(path.name),
                "command": str(path),
                "label": path.name,
            }
    return None


def _configured_model(env: os._Environ[str]) -> str:
    for key in MODEL_ENV_KEYS:
        value = str(env.get(key) or "").strip()
        if value:
            return value
    for candidate in _bundled_model_candidates(env):
        if candidate.exists():
            return str(candidate)
    for candidate in _default_model_candidates(env):
        if candidate.exists():
            return str(candidate)
    return ""


def _configured_ffmpeg(env: os._Environ[str]) -> str:
    for key in FFMPEG_ENV_KEYS:
        value = str(env.get(key) or "").strip()
        if value:
            return value
    for path in _bundled_ffmpeg_candidates(env):
        if _is_executable_file(path):
            return str(path)
    return shutil.which("ffmpeg") or ""


def _bundled_command_candidates(env: os._Environ[str]) -> list[Path]:
    names = _platform_binary_names(("whisper-cli", "main", "whisper.cpp", "whisper-cpp"))
    return _candidate_files(_bundled_binary_dirs(env, "whisper"), names)


def _bundled_ffmpeg_candidates(env: os._Environ[str]) -> list[Path]:
    return _candidate_files(_bundled_binary_dirs(env, "ffmpeg"), _platform_binary_names(("ffmpeg",)))


def _bundled_model_candidates(env: os._Environ[str]) -> list[Path]:
    candidates: list[Path] = []
    for app_dir in _runtime_app_dirs(env):
        for filename in MODEL_FILENAMES:
            candidates.extend(
                [
                    app_dir / "bundled" / "whisper" / "models" / filename,
                    app_dir / "bundled" / "models" / "whisper" / filename,
                    app_dir / "models" / "whisper" / filename,
                ]
            )
    return _dedupe_paths(candidates)


def _bundled_binary_dirs(env: os._Environ[str], tool: str) -> list[Path]:
    slug = _platform_slug()
    dirs: list[Path] = []
    for app_dir in _runtime_app_dirs(env):
        dirs.extend(
            [
                app_dir / "bundled" / tool / slug / "bin",
                app_dir / "bundled" / tool / slug,
                app_dir / "bundled" / tool / "bin",
                app_dir / "bundled" / tool,
                app_dir / "bundled" / "bin",
                app_dir / "bundled",
            ]
        )
    return _dedupe_paths(dirs)


def _runtime_app_dirs(env: os._Environ[str]) -> list[Path]:
    candidates: list[Path] = []
    for key in ("RUMI_APP_DIR", "RUMI_HOME"):
        value = str(env.get(key) or "").strip()
        if value:
            candidates.append(Path(value).expanduser())
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "app.py").exists():
            candidates.append(parent)
            break
    return _dedupe_paths(candidates)


def _candidate_files(dirs: list[Path], names: list[str]) -> list[Path]:
    return _dedupe_paths([directory / name for directory in dirs for name in names])


def _is_executable_file(path: Path) -> bool:
    if not path.is_file():
        return False
    if sys.platform.startswith("win"):
        return True
    return os.access(path, os.X_OK)


def _platform_binary_names(base_names: Sequence[str]) -> list[str]:
    names: list[str] = []
    for name in base_names:
        names.append(f"{name}.exe" if sys.platform.startswith("win") else name)
    return _dedupe_strings(names)


def _platform_slug() -> str:
    system = platform.system().lower() or sys.platform.lower()
    machine = platform.machine().lower()
    if machine in {"arm64", "aarch64"}:
        arch = "aarch64"
    elif machine in {"x86_64", "amd64"}:
        arch = "x86_64"
    else:
        arch = machine or "unknown"
    if system == "darwin":
        os_name = "macos"
    elif system.startswith("win"):
        os_name = "windows"
    elif system == "linux":
        os_name = "linux"
    else:
        os_name = system or "unknown"
    return f"{os_name}-{arch}"


def _well_known_command_candidates() -> list[Path]:
    names = _platform_binary_names(COMMON_COMMANDS)
    roots = [
        Path("/opt/homebrew/bin"),
        Path("/usr/local/bin"),
        Path("/usr/bin"),
        Path.home() / ".local" / "bin",
    ]
    return _candidate_files(roots, names)


def _default_model_candidates(env: os._Environ[str]) -> list[Path]:
    roots: list[Path] = []
    configured_dir = str(env.get(LOCAL_WHISPER_DIR_ENV) or "").strip()
    if configured_dir:
        roots.append(Path(configured_dir).expanduser())
    roots.append(default_local_whisper_model_dir())
    xdg_data = str(env.get("XDG_DATA_HOME") or "").strip()
    if xdg_data:
        roots.append(
            Path(xdg_data).expanduser()
            / APP_DATA_DIR_NAME
            / "models"
            / "whisper"
        )
    roots.extend(
        [
            Path.home()
            / "Library"
            / "Application Support"
            / "Rumi AI"
            / "models"
            / "whisper",
            Path.home()
            / ".local"
            / "share"
            / APP_DATA_DIR_NAME
            / "models"
            / "whisper",
            Path.home()
            / ".cache"
            / "rumi"
            / "models"
            / "whisper",
        ]
    )
    candidates = [
        root / filename
        for root in _dedupe_paths(roots)
        for filename in MODEL_FILENAMES
    ]
    return _dedupe_paths(candidates)


def _run_command_candidate(
    command: dict[str, str],
    *,
    audio_path: Path,
    output_dir: Path,
    model: str,
    language: str,
    prompt: str,
    timeout_seconds: int | float,
) -> dict[str, Any]:
    kind = command["kind"]
    label = command["label"]
    output_prefix = output_dir / "transcript"
    output_txt = output_dir / "transcript.txt"
    if kind != "custom" and not model:
        return _unavailable(
            "local_whisper_model_missing",
            "ローカルWhisperのモデルが未設定です。",
            engine=label,
        )

    prepared_audio_path = audio_path
    if kind == "whisper_cpp":
        prepared = _prepare_whisper_cpp_audio(
            audio_path,
            output_dir=output_dir,
            timeout_seconds=timeout_seconds,
            engine=label,
        )
        if isinstance(prepared, dict):
            return prepared
        prepared_audio_path = prepared

    try:
        argv = _build_command_argv(
            command,
            audio_path=prepared_audio_path,
            output_dir=output_dir,
            output_prefix=output_prefix,
            output_txt=output_txt,
            model=model,
            language=language,
            prompt=prompt,
        )
    except ValueError as exc:
        return _unavailable("local_whisper_not_configured", str(exc), engine=label)

    try:
        completed = _run_subprocess(argv, timeout_seconds=timeout_seconds)
    except subprocess.TimeoutExpired:
        return _unavailable(
            "local_whisper_timeout",
            "ローカルWhisperが時間内に完了しませんでした。",
            engine=label,
        )
    except OSError:
        return _unavailable(
            "local_whisper_not_configured",
            "ローカルWhisperコマンドを起動できませんでした。",
            engine=label,
        )

    text = _read_transcript_output(output_dir, completed.stdout)
    if completed.returncode == 0 and text:
        return _ok(text, engine=label, model_label=_model_label(model, fallback=label))
    if completed.returncode == 0:
        return _unavailable(
            "local_whisper_empty",
            "ローカルWhisperの結果が空でした。",
            engine=label,
        )
    return _unavailable(
        "local_whisper_failed",
        _command_error_reason(completed),
        engine=label,
    )


def _prepare_whisper_cpp_audio(
    audio_path: Path,
    *,
    output_dir: Path,
    timeout_seconds: int | float,
    engine: str,
) -> Path | dict[str, Any]:
    if audio_path.suffix.lower() in WHISPER_CPP_SUPPORTED_SUFFIXES:
        return audio_path
    ffmpeg = _configured_ffmpeg(os.environ)
    if not ffmpeg:
        return _unavailable(
            "local_audio_conversion_unavailable",
            (
                "ffmpegが見つからないため、"
                "録音音声をWhisper用のwavへ変換できません。"
            ),
            engine=engine,
        )
    converted = output_dir / "input.wav"
    argv = [
        ffmpeg,
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(audio_path),
        "-ar",
        "16000",
        "-ac",
        "1",
        "-c:a",
        "pcm_s16le",
        str(converted),
    ]
    try:
        completed = _run_subprocess(argv, timeout_seconds=min(float(timeout_seconds), 60.0))
    except subprocess.TimeoutExpired:
        return _unavailable(
            "local_audio_conversion_timeout",
            "音声変換が時間内に完了しませんでした。",
            engine=engine,
        )
    except OSError:
        return _unavailable(
            "local_audio_conversion_unavailable",
            "ffmpegを起動できませんでした。",
            engine=engine,
        )
    if completed.returncode != 0 or not converted.exists():
        return _unavailable(
            "local_audio_conversion_failed",
            _conversion_error_reason(completed),
            engine=engine,
        )
    return converted


def _build_command_argv(
    command: dict[str, str],
    *,
    audio_path: Path,
    output_dir: Path,
    output_prefix: Path,
    output_txt: Path,
    model: str,
    language: str,
    prompt: str,
) -> list[str]:
    raw = command["command"]
    try:
        tokens = shlex.split(raw)
    except ValueError as exc:
        message = "ローカルWhisperコマンドの形式を確認してください。"
        raise ValueError(message) from exc
    if not tokens:
        raise ValueError("ローカルWhisperコマンドが空です。")

    placeholders = {
        "{audio}": str(audio_path),
        "{model}": model,
        "{output_dir}": str(output_dir),
        "{output_prefix}": str(output_prefix),
        "{output_txt}": str(output_txt),
        "{language}": language,
        "{prompt}": prompt,
    }
    if any(key in token for token in tokens for key in placeholders):
        argv = []
        for token in tokens:
            replaced = _replace_placeholders(token, placeholders)
            if replaced:
                argv.append(replaced)
        return argv

    kind = command["kind"]
    if kind == "whisper":
        argv = [
            *tokens,
            str(audio_path),
            "--model",
            model,
            "--output_format",
            "txt",
            "--output_dir",
            str(output_dir),
        ]
        if language:
            argv.extend(["--language", language])
        if prompt:
            argv.extend(["--initial_prompt", prompt])
        return argv
    if kind == "whisper_cpp":
        argv = [
            *tokens,
            "-m",
            model,
            "-f",
            str(audio_path),
            "-otxt",
            "-of",
            str(output_prefix),
        ]
        argv.extend(["-l", language or "auto"])
        if prompt:
            argv.extend(["--prompt", prompt])
        return argv
    return [*tokens, str(audio_path)]


def _run_subprocess(argv: Sequence[str], *, timeout_seconds: int | float) -> CommandResult:
    completed = subprocess.run(
        list(argv),
        capture_output=True,
        check=False,
        text=True,
        timeout=timeout_seconds,
    )
    return CommandResult(completed.returncode, completed.stdout or "", completed.stderr or "")


def _run_faster_whisper(
    audio_path: Path,
    *,
    model: str,
    language: str,
    prompt: str,
) -> dict[str, Any]:
    try:
        from faster_whisper import WhisperModel  # type: ignore

        kwargs: dict[str, Any] = {
            "device": os.environ.get("RUMI_LOCAL_WHISPER_DEVICE", "cpu"),
            "compute_type": os.environ.get("RUMI_LOCAL_WHISPER_COMPUTE_TYPE", "int8"),
        }
        if not _allow_downloads():
            kwargs["local_files_only"] = True
        whisper_model = WhisperModel(model, **kwargs)
        segments, _info = whisper_model.transcribe(
            str(audio_path),
            language=language or None,
            initial_prompt=prompt or None,
            beam_size=5,
            best_of=5,
            temperature=0.0,
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 350},
            condition_on_previous_text=False,
            no_speech_threshold=0.6,
        )
        text = " ".join(
            str(getattr(segment, "text", "") or "").strip()
            for segment in segments
        ).strip()
        if text:
            return _ok(
                text,
                engine="faster_whisper",
                model_label=_model_label(model, fallback="faster_whisper"),
            )
        return _unavailable(
            "local_whisper_empty",
            "ローカルWhisperの結果が空でした。",
            engine="faster_whisper",
        )
    except Exception:
        return _unavailable(
            "local_whisper_failed",
            "faster-whisperで文字起こしできませんでした。",
            engine="faster_whisper",
        )


def _run_openai_whisper_library(
    audio_path: Path,
    *,
    model: str,
    language: str,
    prompt: str,
) -> dict[str, Any]:
    try:
        import whisper  # type: ignore

        whisper_model = whisper.load_model(model)
        response = whisper_model.transcribe(
            str(audio_path),
            language=language or None,
            initial_prompt=prompt or None,
            fp16=False,
            temperature=0.0,
            condition_on_previous_text=False,
            no_speech_threshold=0.6,
        )
        text = str(response.get("text") if isinstance(response, dict) else "").strip()
        if text:
            return _ok(text, engine="whisper", model_label=_model_label(model, fallback="whisper"))
        return _unavailable(
            "local_whisper_empty",
            "ローカルWhisperの結果が空でした。",
            engine="whisper",
        )
    except Exception:
        return _unavailable(
            "local_whisper_failed",
            "whisperで文字起こしできませんでした。",
            engine="whisper",
        )


def _read_transcript_output(output_dir: Path, stdout: str) -> str:
    txt_files = sorted(
        output_dir.glob("*.txt"),
        key=lambda item: item.stat().st_mtime if item.exists() else 0,
        reverse=True,
    )
    for path in txt_files:
        try:
            text = _clean_transcript(path.read_text(encoding="utf-8", errors="ignore"))
        except OSError:
            text = ""
        if text:
            return text
    return _clean_transcript(stdout)


def _clean_transcript(value: str) -> str:
    lines: list[str] = []
    for raw_line in str(value or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        line = re.sub(r"^\[[0-9:. ,>-]+\]\s*", "", line).strip()
        lowered = line.lower()
        if lowered.startswith(("whisper_", "system_info:", "main:", "usage:")):
            continue
        lines.append(line)
    return "\n".join(lines).strip()


def _decode_audio_payload(audio_payload: str) -> bytes:
    value = str(audio_payload or "").strip()
    if not value:
        return b""
    if value.startswith("data:") and "," in value:
        header, encoded = value.split(",", 1)
        if ";base64" not in header.lower():
            return b""
        value = encoded.strip()
    try:
        return base64.b64decode(value, validate=False)
    except (binascii.Error, ValueError):
        return b""


def _audio_suffix(mime_type: str) -> str:
    lowered = str(mime_type or "").lower()
    if "wav" in lowered:
        return ".wav"
    if "mp4" in lowered or "m4a" in lowered:
        return ".m4a"
    if "mpeg" in lowered or "mp3" in lowered:
        return ".mp3"
    if "ogg" in lowered:
        return ".ogg"
    return ".webm"


def _command_kind(command_name: str) -> str:
    name = Path(str(command_name or "")).name.lower()
    if name == "whisper":
        return "whisper"
    if name in {"whisper-cli", "whisper.cpp", "whisper-cpp", "main"}:
        return "whisper_cpp"
    return "custom"


def _library_model_allowed(model: str) -> bool:
    if not model:
        return False
    if Path(model).expanduser().exists():
        return True
    return _allow_downloads()


def _allow_downloads() -> bool:
    for key in ALLOW_DOWNLOAD_ENV_KEYS:
        value = str(os.environ.get(key) or "").strip().lower()
        if value in {"1", "true", "yes", "on"}:
            return True
    return False


def _has_python_module(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def _coerce_timeout(value: int | float | None) -> int | float:
    if isinstance(value, (int, float)) and value > 0:
        return min(float(value), 300.0)
    env_value = os.environ.get("RUMI_LOCAL_WHISPER_TIMEOUT_SECONDS")
    try:
        parsed = float(env_value) if env_value else DEFAULT_TIMEOUT_SECONDS
    except (TypeError, ValueError):
        parsed = DEFAULT_TIMEOUT_SECONDS
    return min(max(parsed, 1.0), 300.0)


def _model_quality(model: str) -> str:
    filename = Path(str(model or "")).name.lower()
    if "small" in filename:
        return "quality"
    if "base" in filename:
        return "balanced"
    if "tiny" in filename:
        return "fast"
    return "custom" if str(model or "").strip() else "unconfigured"


def _model_label(model: str, *, fallback: str) -> str:
    value = str(model or "").strip()
    if not value:
        return fallback
    path = Path(value)
    if path.name:
        return path.name
    return value


def _ok(text: str, *, engine: str, model_label: str) -> dict[str, Any]:
    return {
        "status": "ok",
        "text": str(text or "").strip(),
        "source": "local_whisper",
        "model": f"local-whisper:{model_label}",
        "engine": engine,
    }


def _unavailable(
    code: str,
    reason: str,
    *,
    engine: str = "",
    attempts: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "status": "unavailable",
        "code": str(code or "local_whisper_unavailable"),
        "reason": _redact_temp_paths(
            str(reason or "ローカルWhisperを利用できません。")
        )[:300],
        "text": "",
    }
    if engine:
        result["engine"] = engine
    if attempts:
        result["attempts"] = attempts
    return result


def _attempt_summary(result: dict[str, Any]) -> dict[str, str]:
    return {
        "engine": str(result.get("engine") or ""),
        "code": str(result.get("code") or ""),
        "reason": str(result.get("reason") or "")[:160],
    }


def _command_error_reason(result: CommandResult) -> str:
    text = _redact_temp_paths(_clean_transcript(result.stderr or result.stdout))
    if text:
        return f"ローカルWhisperコマンドが失敗しました: {text[:120]}"
    return "ローカルWhisperコマンドが失敗しました。"


def _conversion_error_reason(result: CommandResult) -> str:
    text = _redact_temp_paths(_clean_transcript(result.stderr or result.stdout))
    if text:
        return f"音声変換に失敗しました: {text[:120]}"
    return "音声変換に失敗しました。"


def _local_whisper_missing_reason(*, command: dict[str, str] | None, model: str) -> str:
    if not command and not model:
        return (
            "ローカルWhisperが未設定です。"
            "whisper.cpp と baseモデルをセットアップしてください。"
        )
    if not command:
        return "ローカルWhisperコマンドが見つかりません。"
    if not model:
        return "ローカルWhisperモデルが見つかりません。"
    return ""


def _replace_placeholders(token: str, placeholders: dict[str, str]) -> str:
    value = token
    for key, replacement in placeholders.items():
        value = value.replace(key, replacement)
    return value


def _redact_temp_paths(value: str) -> str:
    text = str(value or "")
    text = re.sub(
        r"[/\\][^\s'\"`]*rumi-ambient-(?:audio|stt)-[^\s'\"`]*",
        "[temporary audio]",
        text,
    )
    return text


def _dedupe_paths(values: list[Path]) -> list[Path]:
    result: list[Path] = []
    seen: set[str] = set()
    for value in values:
        resolved = str(value.expanduser())
        if resolved in seen:
            continue
        seen.add(resolved)
        result.append(Path(resolved))
    return result


def _dedupe_strings(values: Sequence[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "")
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _unlink_quietly(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass
