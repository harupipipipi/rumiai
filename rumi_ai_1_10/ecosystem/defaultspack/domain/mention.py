"""Shared Unicode-safe product mention parsing contract."""

from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata


ASCII_MENTION_BOUNDARY_BLOCKERS = frozenset(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_.%+-/:@\\"
)
MENTION_TOKEN_SYMBOLS = frozenset("_./:-")
URL_SCHEME_IN_CURRENT_SEGMENT_RE = re.compile(r"(?:https?|ftp)://\S*$", re.I)


@dataclass(frozen=True, slots=True)
class MentionToken:
    """A normalized mention token and its source span."""

    start: int
    end: int
    value: str


def is_mention_start(text: str, at_index: int) -> bool:
    """Return whether an at sign begins a product mention, not an email or URL."""

    if at_index < 0 or at_index >= len(text) or text[at_index] != "@":
        return False
    if at_index == 0:
        return True
    previous_character = text[at_index - 1]
    if previous_character in ASCII_MENTION_BOUNDARY_BLOCKERS:
        return False

    # Japanese prose intentionally supports adjacency (お願い@pm), while an @
    # inside the current URL segment or before a domain-like suffix is literal.
    if URL_SCHEME_IN_CURRENT_SEGMENT_RE.search(text[:at_index]):
        return False
    if _is_unicode_word_char(previous_character):
        end = at_index + 1
        while end < len(text) and _is_mention_token_char(text[end]):
            end += 1
        while end > at_index + 1 and text[end - 1] == ".":
            end -= 1
        if _looks_like_domain(text[at_index + 1 : end]):
            return False
    return True


def _is_unicode_word_char(value: str) -> bool:
    return bool(value) and unicodedata.category(value)[0] in {"L", "M", "N"}


def _looks_like_domain(value: str) -> bool:
    labels = value.split(".")
    if len(labels) < 2 or any(not label for label in labels):
        return False
    for label in labels:
        if not _is_unicode_word_char(label[0]) or not _is_unicode_word_char(label[-1]):
            return False
        if any(
            not (_is_unicode_word_char(character) or character == "-")
            for character in label
        ):
            return False
    return True


def _is_mention_token_char(value: str) -> bool:
    if not value:
        return False
    if value in MENTION_TOKEN_SYMBOLS:
        return True
    return unicodedata.category(value)[0] in {"L", "M", "N"}


def iter_mention_tokens(text: str) -> list[MentionToken]:
    """Extract Unicode-safe product mentions with deterministic source spans."""

    content = str(text or "")
    result: list[MentionToken] = []
    search_from = 0
    while True:
        at_index = content.find("@", search_from)
        if at_index < 0:
            break
        search_from = at_index + 1
        if not is_mention_start(content, at_index):
            continue
        end = at_index + 1
        while end < len(content) and _is_mention_token_char(content[end]):
            end += 1
        while end > at_index + 1 and content[end - 1] == ".":
            end -= 1
        if end == at_index + 1:
            continue
        result.append(
            MentionToken(start=at_index, end=end, value=content[at_index + 1 : end])
        )
    return result


def extract_mention_values(text: str) -> list[str]:
    """Return mention values in source order without changing their case."""

    return [token.value for token in iter_mention_tokens(text)]
