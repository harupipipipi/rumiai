"""
transport/cli_formatter.py — Terminal output formatter.

Converts AI response content (Markdown-like) to terminal-friendly output.
Supports:
  - Code block detection with language label
  - Bold / italic via ANSI escape codes
  - Horizontal rules
  - Streaming character-by-character display
  - JSON raw output mode
"""

import json
import os
import sys
import re


# ── ANSI colour helpers ──────────────────────────────────────

RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
ITALIC = "\033[3m"
UNDERLINE = "\033[4m"
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
BLUE = "\033[34m"
MAGENTA = "\033[35m"
CYAN = "\033[36m"
GRAY = "\033[90m"
BG_GRAY = "\033[100m"


def supports_colour():
    """Return True if stdout likely supports ANSI colours."""
    if os.environ.get("NO_COLOR"):
        return False
    if not hasattr(sys.stdout, "isatty"):
        return False
    return sys.stdout.isatty()

_USE_COLOUR = None


def _colour_enabled():
    global _USE_COLOUR
    if _USE_COLOUR is None:
        _USE_COLOUR = supports_colour()
    return _USE_COLOUR


def c(code, text):
    """Wrap *text* in ANSI *code* if colour is enabled."""
    if _colour_enabled():
        return code + text + RESET
    return text


# ── Markdown → terminal conversion ──────────────────────────

def format_markdown(text):
    """Convert a Markdown string to terminal-friendly output.

    This is intentionally lightweight — it handles the most common patterns
    produced by LLMs without pulling in a full Markdown parser.
    """
    if not text:
        return ""

    lines = text.split("\n")
    output_lines = []
    in_code_block = False
    code_lang = ""

    for line in lines:
        # ── Code fence ──
        if line.lstrip().startswith("```"):
            if not in_code_block:
                in_code_block = True
                code_lang = line.lstrip()[3:].strip()
                label = code_lang if code_lang else "code"
                output_lines.append(c(DIM, "─── " + label + " ───"))
                continue
            else:
                in_code_block = False
                output_lines.append(c(DIM, "─" * 20))
                continue

        if in_code_block:
            output_lines.append(c(CYAN, "  " + line))
            continue

        # ── Headings ──
        heading_match = re.match(r"^(#{1,6})\s+(.*)", line)
        if heading_match:
            level = len(heading_match.group(1))
            heading_text = heading_match.group(2)
            if level == 1:
                output_lines.append(c(BOLD + MAGENTA, "▌ " + heading_text))
            elif level == 2:
                output_lines.append(c(BOLD + BLUE, "▌ " + heading_text))
            else:
                output_lines.append(c(BOLD, "  " * (level - 2) + "▸ " + heading_text))
            continue

        # ── Horizontal rule ──
        if re.match(r"^---+$|^\*\*\*+$|^___+$", line.strip()):
            output_lines.append(c(DIM, "─" * 40))
            continue

        # ── Bullet list ──
        bullet_match = re.match(r"^(\s*)[*\-+]\s+(.*)", line)
        if bullet_match:
            indent = bullet_match.group(1)
            content = _inline_format(bullet_match.group(2))
            output_lines.append(indent + c(GREEN, "• ") + content)
            continue

        # ── Numbered list ──
        num_match = re.match(r"^(\s*)\d+\.\s+(.*)", line)
        if num_match:
            indent = num_match.group(1)
            content = _inline_format(num_match.group(2))
            output_lines.append(indent + c(GREEN, "▹ ") + content)
            continue

        # ── Block quote ──
        if line.lstrip().startswith(">"):
            quote_text = line.lstrip()[1:].lstrip()
            output_lines.append(c(DIM + ITALIC, "  │ " + quote_text))
            continue

        # ── Normal line with inline formatting ──
        output_lines.append(_inline_format(line))

    return "\n".join(output_lines)


def _inline_format(text):
    """Apply inline Markdown formatting (bold, italic, code) via ANSI."""
    if not _colour_enabled():
        return text

    # Inline code: `code`
    text = re.sub(r"`([^`]+)`", lambda m: BG_GRAY + m.group(1) + RESET, text)
    # Bold + italic: ***text*** or ___text___
    text = re.sub(r"\*\*\*(.+?)\*\*\*", lambda m: BOLD + ITALIC + m.group(1) + RESET, text)
    # Bold: **text** or __text__
    text = re.sub(r"\*\*(.+?)\*\*", lambda m: BOLD + m.group(1) + RESET, text)
    text = re.sub(r"__(.+?)__", lambda m: BOLD + m.group(1) + RESET, text)
    # Italic: *text* or _text_  (but not inside words like some_var_name)
    text = re.sub(r"(?<!\w)\*([^*]+?)\*(?!\w)", lambda m: ITALIC + m.group(1) + RESET, text)

    return text


# ── Streaming display ───────────────────────────────────────

def stream_print(text, delay=0.0):
    """Print *text* character by character for a streaming effect.

    If *delay* is 0 (default), characters are flushed immediately without
    artificial slowdown — the natural network/generation latency provides
    the streaming feel.
    """
    sys.stdout.write(text)
    sys.stdout.flush()


def stream_print_line(text=""):
    """Print *text* followed by a newline, flushed immediately."""
    sys.stdout.write(text + "\n")
    sys.stdout.flush()


# ── JSON output ─────────────────────────────────────────────

def format_json(data):
    """Pretty-print a dict/list as JSON."""
    return json.dumps(data, indent=2, ensure_ascii=False)


# ── Response content extraction ─────────────────────────────

def extract_text_from_response(response_data):
    """Extract plain text from a block response's data field.

    Handles the common patterns:
      - response_data is a message dict with "content" list of {type, text}
      - response_data is a dict with a nested "message" key
      - response_data is a string
    """
    if response_data is None:
        return ""
    if isinstance(response_data, str):
        return response_data

    # Case: {"message": {..., "content": [...]}}
    msg = response_data
    if "message" in response_data and isinstance(response_data["message"], dict):
        msg = response_data["message"]

    content = msg.get("content")
    if content is None:
        # Maybe it's the raw AI response with content list at top level
        return str(response_data)

    if isinstance(content, str):
        return content

    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(item.get("text", ""))
            elif isinstance(item, str):
                parts.append(item)
        return "".join(parts)

    return str(content)


# ── Prompt helpers ──────────────────────────────────────────

def print_prompt(conversation_id=None):
    """Print the interactive prompt."""
    if conversation_id:
        short_id = conversation_id[:8]
        prompt_str = c(GREEN + BOLD, "rumi") + c(DIM, ":" + short_id) + c(GREEN + BOLD, "> ")
    else:
        prompt_str = c(GREEN + BOLD, "rumi> ")
    sys.stdout.write(prompt_str)
    sys.stdout.flush()


def print_assistant_label():
    """Print the assistant response label."""
    sys.stdout.write("\n" + c(BLUE + BOLD, "AI") + c(DIM, " ─── ") + "\n\n")
    sys.stdout.flush()


def print_system_message(text):
    """Print a system/info message."""
    sys.stdout.write(c(YELLOW, "ℹ " + text) + "\n")
    sys.stdout.flush()


def print_error_message(text):
    """Print an error message."""
    sys.stdout.write(c(RED + BOLD, "✗ ") + c(RED, text) + "\n")
    sys.stdout.flush()


def print_success_message(text):
    """Print a success message."""
    sys.stdout.write(c(GREEN, "✓ " + text) + "\n")
    sys.stdout.flush()


def print_welcome():
    """Print the welcome banner."""
    banner = r"""
  ┌─────────────────────────────────────┐
  │  rumi defaults — CLI transport      │
  │  Type /help for commands, /quit     │
  │  to exit.                           │
  └─────────────────────────────────────┘
"""
    sys.stdout.write(c(CYAN, banner))
    sys.stdout.flush()
