#!/usr/bin/env python3

from __future__ import annotations

import argparse
import html
import os
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urlencode
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
LINK_BLOCK_START = "<!-- docs-i18n-links:start -->"
LINK_BLOCK_END = "<!-- docs-i18n-links:end -->"
SPLIT_TOKEN = "\n§§§RUMI_DOC_SPLIT§§§\n"
PLACEHOLDER_PREFIX = "§RUMI§"


@dataclass(frozen=True)
class LangSpec:
    code: str
    label: str
    dir_name: str | None


LANGS: tuple[LangSpec, ...] = (
    LangSpec("en", "EN", None),
    LangSpec("ja", "JP", "ja"),
    LangSpec("ko", "KR", "ko"),
    LangSpec("zh-CN", "CN", "zh-cn"),
)


TARGET_PATTERNS: tuple[tuple[Path, tuple[str, ...]], ...] = (
    (ROOT, ("README.md",)),
    (ROOT / "pack-shell", ("README.md",)),
    (ROOT / "rumi_mobile", ("README.md", "TODO.md")),
    (ROOT / "browser_extensions" / "rumi_browser_companion", ("README.md",)),
    (ROOT / "rumi_viewer" / "frontend", ("README.md",)),
    (ROOT / "rumi_ai_1_10", ("README.md", "CHANGELOG.md")),
    (ROOT / "rumi_ai_1_10" / "docs", ("**/*.md",)),
    (ROOT / "rumi_ai_1_10" / "core_runtime" / "core_pack" / "core_control_panel", ("README.md",)),
    (ROOT / "rumi_ai_1_10" / "ecosystem" / "defaultspack", ("README.md",)),
    (ROOT / "rumi_ai_1_10" / "ecosystem" / "defaultspack" / "docs", ("**/*.md",)),
    (ROOT / "rumi_ai_1_10" / "ecosystem" / "defaults", ("README.md",)),
    (ROOT / "rumi_ai_1_10" / "ecosystem" / "defaults" / "docs", ("**/*.md",)),
)


HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)(?:\s+#+\s*)?$")
CODE_FENCE_RE = re.compile(r"^\s*```")
TABLE_DELIMITER_RE = re.compile(r"^\s*\|?(?:\s*:?-{3,}:?\s*\|)+\s*:?-{3,}:?\s*\|?\s*$")
INLINE_CODE_RE = re.compile(r"`[^`\n]+`")
HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
HTML_TAG_RE = re.compile(r"</?[\w:-]+(?:\s+[^<>]*?)?>")
BARE_URL_RE = re.compile(r"https?://[^\s)>\"]+")
LINK_RE = re.compile(r"(!?)\[([^\]]*)\]\(([^)\n]+)\)")
PATHLIKE_LABEL_RE = re.compile(r"(^\.{0,2}/)|(/)|(\.[A-Za-z0-9]{1,8}$)")
LANG_BLOCK_RE = re.compile(
    rf"^\s*{re.escape(LINK_BLOCK_START)}\n.*?\n{re.escape(LINK_BLOCK_END)}\n*",
    re.DOTALL,
)
ASCII_OR_CJK_RE = re.compile(r"[A-Za-z0-9\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]")
CJK_RE = re.compile(r"[\u3040-\u30ff\u3400-\u9fff\uac00-\ud7af]")


class GoogleMobileTranslator:
    def __init__(self) -> None:
        self.cache: dict[tuple[str, str], str] = {}

    def translate_many(self, texts: Iterable[str], target: str) -> dict[str, str]:
        unique: list[str] = []
        seen: set[str] = set()
        for text in texts:
            if text in seen:
                continue
            seen.add(text)
            if not self._needs_translation(text, target):
                self.cache[(target, text)] = text
                continue
            if (target, text) not in self.cache:
                unique.append(text)
        if not unique:
            return {text: self.cache[(target, text)] for text in seen}
        for batch in self._build_batches(unique):
            self._store_batch(batch, target)
        return {text: self.cache[(target, text)] for text in seen}

    def translate_one(self, text: str, target: str) -> str:
        return self.translate_many([text], target)[text]

    def _needs_translation(self, text: str, target: str) -> bool:
        stripped = text.strip()
        if not stripped:
            return False
        if not ASCII_OR_CJK_RE.search(stripped):
            return False
        if target == "en" and not CJK_RE.search(stripped):
            return False
        return True

    def _build_batches(self, texts: list[str], max_chars: int = 1800) -> Iterable[list[str]]:
        batch: list[str] = []
        size = 0
        for text in texts:
            extra = len(text) + (len(SPLIT_TOKEN) if batch else 0)
            if batch and size + extra > max_chars:
                yield batch
                batch = [text]
                size = len(text)
            else:
                batch.append(text)
                size += extra
        if batch:
            yield batch

    def _store_batch(self, batch: list[str], target: str) -> None:
        if not batch:
            return
        payload = SPLIT_TOKEN.join(batch)
        try:
            translated_payload = self._translate_chunk(payload, target)
            parts = translated_payload.split(SPLIT_TOKEN)
            if len(parts) != len(batch):
                raise ValueError("translation split token count did not match batch size")
            for item, translated in zip(batch, parts, strict=True):
                self.cache[(target, item)] = translated
        except HTTPError as exc:
            if exc.code == 400 and len(batch) > 1:
                midpoint = max(1, len(batch) // 2)
                self._store_batch(batch[:midpoint], target)
                self._store_batch(batch[midpoint:], target)
                return
            if exc.code == 400 and len(batch) == 1:
                self.cache[(target, batch[0])] = self._translate_long_text(batch[0], target)
                return
            raise
        except ValueError:
            if len(batch) == 1:
                self.cache[(target, batch[0])] = self._translate_long_text(batch[0], target)
                return
            midpoint = max(1, len(batch) // 2)
            self._store_batch(batch[:midpoint], target)
            self._store_batch(batch[midpoint:], target)

    def _translate_long_text(self, text: str, target: str, max_chars: int = 900) -> str:
        if len(text) <= max_chars:
            return self._translate_chunk(text, target)
        return "".join(self._translate_long_text(piece, target, max_chars) for piece in self._split_text(text, max_chars))

    def _split_text(self, text: str, max_chars: int) -> list[str]:
        if len(text) <= max_chars:
            return [text]
        midpoint = len(text) // 2
        search_start = max(1, midpoint - max_chars // 2)
        search_end = min(len(text) - 1, midpoint + max_chars // 2)
        separators = ("\n", "|", "。", ". ", "; ", ", ", " ")
        candidate_positions: list[int] = []
        for separator in separators:
            position = text.rfind(separator, search_start, search_end)
            if position != -1:
                candidate_positions.append(position + len(separator))
        split_at = min(candidate_positions, key=lambda value: abs(value - midpoint)) if candidate_positions else midpoint
        split_at = max(1, min(len(text) - 1, split_at))
        return self._split_text(text[:split_at], max_chars) + self._split_text(text[split_at:], max_chars)

    def _translate_chunk(self, text: str, target: str) -> str:
        params = urlencode({"sl": "auto", "tl": target, "q": text})
        request = Request(
            "https://translate.google.com/m?" + params,
            headers={"User-Agent": "Mozilla/5.0"},
        )
        attempts = 0
        while True:
            attempts += 1
            try:
                with urlopen(request, timeout=30) as response:
                    body = response.read().decode("utf-8", errors="ignore")
                match = re.search(
                    r"<div[^>]+class=\"[^\"]*result-container[^\"]*\"[^>]*>(.*?)</div>",
                    body,
                    re.DOTALL,
                )
                if not match:
                    raise RuntimeError("could not find translation payload in Google response")
                return html.unescape(match.group(1))
            except HTTPError as exc:
                if exc.code == 429 and attempts < 6:
                    time.sleep(min(2**attempts, 20))
                    continue
                raise
            except URLError:
                if attempts < 4:
                    time.sleep(attempts)
                    continue
                raise


def discover_targets(only: list[str], exact_files: set[Path]) -> list[Path]:
    files: list[Path] = []
    seen: set[Path] = set()
    for base, patterns in TARGET_PATTERNS:
        for pattern in patterns:
            for path in sorted(base.glob(pattern)):
                if not path.is_file():
                    continue
                if "i18n" in path.parts:
                    continue
                resolved = path.resolve()
                if exact_files and resolved not in exact_files:
                    continue
                if only and not any(token in path.as_posix() for token in only):
                    continue
                if resolved not in seen:
                    seen.add(resolved)
                    files.append(path)
    return sorted(files)


def choose_root(path: Path) -> Path:
    candidates = [base for base, _ in TARGET_PATTERNS if path == base or base in path.parents]
    if not candidates:
        raise RuntimeError(f"no documentation root found for {path}")
    return max(candidates, key=lambda candidate: len(candidate.parts))


def output_path_for(path: Path, lang: LangSpec) -> Path:
    if lang.dir_name is None:
        return path
    base = choose_root(path)
    relative = path.relative_to(base)
    return base / "i18n" / lang.dir_name / relative


def normalize_relpath(path: str) -> str:
    path = path.replace(os.sep, "/")
    if not path.startswith((".", "/")):
        path = "./" + path
    return path


def strip_language_block(text: str) -> str:
    text = text.lstrip("\ufeff")
    return LANG_BLOCK_RE.sub("", text, count=1)


def unwrap_markdown_wrapper(text: str) -> str:
    lines = text.splitlines()
    non_empty = [index for index, line in enumerate(lines) if line.strip()]
    if len(non_empty) >= 2 and lines[non_empty[0]].strip() == "```markdown" and lines[non_empty[-1]].strip() == "```":
        del lines[non_empty[-1]]
        del lines[non_empty[0]]
    return "\n".join(lines).strip() + "\n"


def github_slug(text: str, seen: dict[str, int]) -> str:
    text = re.sub(r"`([^`]*)`", r"\1", text)
    text = re.sub(r"[*_~]", "", text)
    text = re.sub(r"<[^>]+>", "", text)
    text = html.unescape(text).strip().lower()
    text = re.sub(r"[^\w\u00a1-\uffff\s-]", "", text)
    text = re.sub(r"\s+", "-", text)
    text = re.sub(r"-{2,}", "-", text).strip("-")
    count = seen.get(text, 0)
    seen[text] = count + 1
    if count == 0:
        return text
    return f"{text}-{count}"


def build_heading_maps(
    sources: dict[Path, str],
    langs: Iterable[LangSpec],
    translator: GoogleMobileTranslator,
) -> dict[Path, dict[str, dict[str, str]]]:
    heading_maps: dict[Path, dict[str, dict[str, str]]] = {}
    for path, text in sources.items():
        print(f"indexing headings {path.relative_to(ROOT)}", flush=True)
        lines = text.splitlines()
        original_headings: list[str] = []
        in_fence = False
        for line in lines:
            if CODE_FENCE_RE.match(line):
                in_fence = not in_fence
                continue
            if in_fence:
                continue
            match = HEADING_RE.match(line)
            if match:
                original_headings.append(match.group(2).strip())
        path_maps: dict[str, dict[str, str]] = {}
        original_seen: dict[str, int] = {}
        original_slugs = [github_slug(heading, original_seen) for heading in original_headings]
        for lang in langs:
            prepared_headings: list[str] = []
            replacements_by_heading: list[dict[str, str]] = []
            for heading in original_headings:
                prepared, replacements = prepare_inline(heading, path, lang, path, {}, {})
                prepared_headings.append(prepared)
                replacements_by_heading.append(replacements)
            translated_lookup = translator.translate_many(prepared_headings, lang.code)
            translated_headings = [
                replace_tokens(translated_lookup[prepared].replace("&#39;", "'"), replacements)
                for prepared, replacements in zip(prepared_headings, replacements_by_heading, strict=True)
            ]
            translated_seen: dict[str, int] = {}
            translated_slugs = [github_slug(heading, translated_seen) for heading in translated_headings]
            path_maps[lang.code] = {
                original_slug: translated_slug
                for original_slug, translated_slug in zip(original_slugs, translated_slugs, strict=True)
            }
        heading_maps[path] = path_maps
    return heading_maps


def rewrite_link_target(
    raw_target: str,
    source_path: Path,
    current_output: Path,
    lang: LangSpec,
    heading_maps: dict[Path, dict[str, dict[str, str]]],
    target_outputs: dict[Path, dict[str, Path]],
) -> str:
    target = raw_target.strip()
    if not target:
        return target
    suffix = ""
    if " " in target and not target.startswith("<"):
        candidate, remainder = target.split(" ", 1)
        if not any(ch in candidate for ch in ('"', "'")):
            target = candidate
            suffix = " " + remainder
    enclosed = target.startswith("<") and target.endswith(">")
    if enclosed:
        target = target[1:-1]
    if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", target):
        rebuilt = target
    else:
        path_part, fragment = target, ""
        if "#" in target:
            path_part, fragment = target.split("#", 1)
        fragment_key = unquote(fragment).strip()
        if path_part:
            resolved = (source_path.parent / path_part).resolve()
        else:
            resolved = source_path.resolve()
        rebuilt_path = path_part
        if resolved in target_outputs:
            desired = target_outputs[resolved][lang.code]
            rebuilt_path = normalize_relpath(os.path.relpath(desired, current_output.parent))
        if fragment_key and resolved in heading_maps:
            fragment_key = fragment_key.lstrip("#")
            fragment_lookup = heading_maps[resolved][lang.code]
            fragment = fragment_lookup.get(fragment_key, fragment_lookup.get(fragment_key.lower(), fragment_key))
        rebuilt = rebuilt_path if path_part else ""
        if fragment:
            rebuilt += f"#{fragment}"
        if not rebuilt and fragment:
            rebuilt = f"#{fragment}"
    if enclosed:
        rebuilt = f"<{rebuilt}>"
    return rebuilt + suffix


def replace_tokens(text: str, replacements: dict[str, str]) -> str:
    for token, value in replacements.items():
        text = text.replace(token, value)
    return text


def prepare_inline(
    text: str,
    source_path: Path,
    lang: LangSpec,
    current_output: Path,
    heading_maps: dict[Path, dict[str, dict[str, str]]],
    target_outputs: dict[Path, dict[str, Path]],
) -> tuple[str, dict[str, str]]:
    if not text.strip():
        return text, {}
    replacements: dict[str, str] = {}
    counter = 0

    def make_token(value: str) -> str:
        nonlocal counter
        token = f"{PLACEHOLDER_PREFIX}{counter}§"
        counter += 1
        replacements[token] = value
        return token

    def link_sub(match: re.Match[str]) -> str:
        bang, label, raw_target = match.groups()
        rewritten_target = rewrite_link_target(
            raw_target,
            source_path,
            current_output,
            lang,
            heading_maps,
            target_outputs,
        )
        if PATHLIKE_LABEL_RE.search(label.strip()):
            return make_token(f"{bang}[{label}]({rewritten_target})")
        target_token = make_token(rewritten_target)
        return f"{bang}[{label}]({target_token})"

    prepared = LINK_RE.sub(link_sub, text)
    prepared = INLINE_CODE_RE.sub(lambda match: make_token(match.group(0)), prepared)
    prepared = HTML_COMMENT_RE.sub(lambda match: make_token(match.group(0)), prepared)
    prepared = HTML_TAG_RE.sub(lambda match: make_token(match.group(0)), prepared)
    prepared = BARE_URL_RE.sub(lambda match: make_token(match.group(0)), prepared)
    return prepared, replacements


def render_document(
    source_path: Path,
    source_text: str,
    lang: LangSpec,
    translator: GoogleMobileTranslator,
    heading_maps: dict[Path, dict[str, dict[str, str]]],
    target_outputs: dict[Path, dict[str, Path]],
) -> str:
    current_output = target_outputs[source_path][lang.code]
    lines = source_text.splitlines()
    translated_lines: list[str] = []
    in_fence = False
    batch_inputs: list[str] = []
    prepared_lines: dict[int, str] = {}
    replacements_by_index: dict[int, dict[str, str]] = {}
    literal_lines: dict[int, str] = {}

    for index, line in enumerate(lines):
        stripped = line.strip()
        if CODE_FENCE_RE.match(line):
            in_fence = not in_fence
            literal_lines[index] = line
            continue
        if in_fence or TABLE_DELIMITER_RE.match(line) or stripped.startswith("<!-- docs-i18n-links:"):
            literal_lines[index] = line
            continue
        if not stripped:
            literal_lines[index] = ""
            continue
        prepared, replacements = prepare_inline(
            line,
            source_path,
            lang,
            current_output,
            heading_maps,
            target_outputs,
        )
        prepared_lines[index] = prepared
        replacements_by_index[index] = replacements
        batch_inputs.append(prepared)

    translated_lookup = translator.translate_many(batch_inputs, lang.code)

    for index, line in enumerate(lines):
        if index in literal_lines:
            translated_lines.append(literal_lines[index])
        else:
            translated = translated_lookup[prepared_lines[index]].replace("&#39;", "'")
            translated_lines.append(replace_tokens(translated, replacements_by_index[index]))

    link_line = " | ".join(
        f"[{candidate.label}]({normalize_relpath(os.path.relpath(target_outputs[source_path][candidate.code], current_output.parent))})"
        for candidate in LANGS
    )
    body = "\n".join(translated_lines).strip() + "\n"
    return f"{LINK_BLOCK_START}\n{link_line}\n{LINK_BLOCK_END}\n\n{body}"


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate multilingual markdown docs with language switch links.")
    parser.add_argument(
        "--only",
        action="append",
        default=[],
        help="Limit processing to source paths containing this token. Can be supplied multiple times.",
    )
    parser.add_argument(
        "--file",
        action="append",
        default=[],
        help="Process exactly this repo-relative markdown file. Can be supplied multiple times.",
    )
    parser.add_argument(
        "--start-at",
        default=None,
        help="Resume from this repo-relative markdown file in discovery order.",
    )
    parser.add_argument(
        "--residual-japanese-only",
        action="store_true",
        help="Process only source documents whose current canonical file still contains Japanese text.",
    )
    args = parser.parse_args()

    exact_files = {(ROOT / value).resolve() for value in args.file}
    discovered = discover_targets(args.only, exact_files)
    if args.start_at:
        start_path = (ROOT / args.start_at).resolve()
        try:
            start_index = next(index for index, path in enumerate(discovered) if path.resolve() == start_path)
        except StopIteration as exc:
            raise SystemExit(f"--start-at path not found in discovery set: {args.start_at}") from exc
        discovered = discovered[start_index:]
    if args.residual_japanese_only:
        discovered = [
            path
            for path in discovered
            if CJK_RE.search(path.read_text(encoding="utf-8"))
        ]
    sources: dict[Path, str] = {}
    for path in discovered:
        raw = path.read_text(encoding="utf-8")
        cleaned = unwrap_markdown_wrapper(strip_language_block(raw))
        sources[path.resolve()] = cleaned

    if not sources:
        print("No source documents matched.", file=sys.stderr)
        return 1

    translator = GoogleMobileTranslator()
    heading_maps = build_heading_maps(sources, LANGS, translator)
    target_outputs = {
        path: {lang.code: output_path_for(path, lang).resolve() for lang in LANGS}
        for path in sources
    }

    for path, source_text in sources.items():
        print(f"processing {path.relative_to(ROOT)}", flush=True)
        for lang in LANGS:
            output_path = target_outputs[path][lang.code]
            output_path.parent.mkdir(parents=True, exist_ok=True)
            rendered = render_document(path, source_text, lang, translator, heading_maps, target_outputs)
            output_path.write_text(rendered, encoding="utf-8")
            print(f"wrote {output_path.relative_to(ROOT)}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
