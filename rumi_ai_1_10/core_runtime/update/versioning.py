"""Small semver helpers used by update compatibility checks."""

from __future__ import annotations

import re
from pathlib import Path

_SEMVER_RE = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:[-+][0-9A-Za-z.-]+)?$")


def normalize_version(version: str) -> str:
    return version.strip().removeprefix("v")


def is_valid_semver(version: str) -> bool:
    return bool(_SEMVER_RE.match(normalize_version(version)))


def parse_version_tuple(version: str) -> tuple[int, int, int]:
    clean = normalize_version(version).split("-", 1)[0].split("+", 1)[0]
    parts = clean.split(".")
    if len(parts) != 3:
        return (0, 0, 0)
    parsed: list[int] = []
    for item in parts:
        try:
            parsed.append(int(item))
        except ValueError:
            parsed.append(0)
    return (parsed[0], parsed[1], parsed[2])


def version_newer(latest: str, current: str) -> bool:
    return parse_version_tuple(latest) > parse_version_tuple(current)


def sort_versions(versions: list[str] | tuple[str, ...]) -> list[str]:
    return sorted(versions, key=parse_version_tuple)


def satisfies_constraint(version: str, constraint: str | None) -> bool:
    if not constraint:
        return True
    raw = constraint.strip()
    operators = (">=", "<=", ">", "<", "==", "=")
    op = "=="
    expected = raw
    for candidate in operators:
        if raw.startswith(candidate):
            op = candidate
            expected = raw[len(candidate):].strip()
            break
    left = parse_version_tuple(version)
    right = parse_version_tuple(expected)
    if op == ">=":
        return left >= right
    if op == "<=":
        return left <= right
    if op == ">":
        return left > right
    if op == "<":
        return left < right
    return left == right


def read_pyproject_version(path: Path) -> str | None:
    if not path.is_file():
        return None
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("version"):
            _, _, value = stripped.partition("=")
            return value.strip().strip('"').strip("'")
    return None
