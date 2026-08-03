"""Traceability records for normative schemas, migrations, and inventories."""

from __future__ import annotations

import hashlib
import subprocess
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Mapping

from .canonical import canonical_digest
from .errors import ProtocolError
from .ids import validate_artifact_digest

PROVENANCE_SCHEMA = "io.tobkiri.provenance.v1"
PROVENANCE_GENERATOR = "tobkiri-protocol"
PROVENANCE_GENERATOR_VERSION = "1.0.0"


@dataclass(frozen=True)
class EvidenceRef:
    """One stable evidence location supporting a serialized decision."""

    path: str
    rule_id: str
    digest: str
    line: int | None = None

    def __post_init__(self) -> None:
        validate_artifact_digest(self.digest, field="evidence.digest")
        if not self.path or not self.rule_id:
            raise ProtocolError("evidence path and rule_id are required")
        if self.line is not None and self.line < 1:
            raise ProtocolError("evidence line must be positive")

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe evidence record."""
        return asdict(self)


@dataclass(frozen=True)
class ProvenanceRecord:
    """Immutable provenance attached to a manifest or migration result."""

    source_kind: str
    source_path: str
    source_digest: str
    repository_commit: str
    repository_tree: str
    generator: str = PROVENANCE_GENERATOR
    generator_version: str = PROVENANCE_GENERATOR_VERSION
    normative: bool = False
    evidence: tuple[EvidenceRef, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.source_kind not in {"repository", "migration", "generated", "external"}:
            raise ProtocolError(f"unknown provenance source kind: {self.source_kind}")
        validate_artifact_digest(self.source_digest, field="provenance.source_digest")
        if not self.source_path or not self.repository_commit or not self.repository_tree:
            raise ProtocolError("provenance path, commit, and tree are required")
        if len(self.repository_tree) != 64 or any(
            character not in "0123456789abcdef" for character in self.repository_tree
        ):
            raise ProtocolError("provenance.repository_tree must be a lowercase SHA-256")

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe provenance record."""
        result = asdict(self)
        result["schema"] = PROVENANCE_SCHEMA
        result["evidence"] = [item.to_dict() for item in self.evidence]
        return result


def sha256_bytes(value: bytes) -> str:
    """Return a lowercase SHA-256 digest with the protocol prefix."""
    return "sha256:" + hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    """Hash a file without executing or importing its contents."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def repository_commit(root: Path) -> str:
    """Return the current Git commit or a deterministic working-tree marker."""
    result = _git(root, "rev-parse", "HEAD")
    return result or "working-tree"


def repository_tree_digest(root: Path, paths: list[Path] | None = None) -> str:
    """Hash sorted relative path/digest pairs for a reproducible source tree."""
    selected = paths if paths is not None else _tracked_files(root)
    lines: list[str] = []
    for path in sorted(selected):
        if not path.is_file():
            continue
        try:
            relative = path.relative_to(root).as_posix()
        except ValueError:
            continue
        lines.append(f"{relative}\0{sha256_file(path)}\n")
    return hashlib.sha256("".join(lines).encode("utf-8")).hexdigest()


def make_provenance(
    *,
    root: Path,
    source_path: str,
    payload: Mapping[str, Any],
    source_kind: str,
    normative: bool = False,
    evidence: tuple[EvidenceRef, ...] = (),
) -> ProvenanceRecord:
    """Build a provenance record from a canonical serialized payload."""
    source_digest = canonical_digest(dict(payload))
    paths = [root / source_path] if (root / source_path).is_file() else None
    return ProvenanceRecord(
        source_kind=source_kind,
        source_path=source_path,
        source_digest=source_digest,
        repository_commit=repository_commit(root),
        repository_tree=repository_tree_digest(root, paths),
        evidence=evidence,
        normative=normative,
    )


def provenance_from_dict(value: Mapping[str, Any]) -> ProvenanceRecord:
    """Parse a provenance mapping without granting authority."""
    if not isinstance(value, Mapping):
        raise ProtocolError("provenance must be an object")
    evidence = tuple(
        EvidenceRef(
            path=str(item["path"]),
            rule_id=str(item["rule_id"]),
            digest=str(item["digest"]),
            line=item.get("line"),
        )
        for item in value.get("evidence", [])
        if isinstance(item, Mapping)
    )
    return ProvenanceRecord(
        source_kind=str(value.get("source_kind", "")),
        source_path=str(value.get("source_path", "")),
        source_digest=str(value.get("source_digest", "")),
        repository_commit=str(value.get("repository_commit", "")),
        repository_tree=str(value.get("repository_tree", "")),
        generator=str(value.get("generator", PROVENANCE_GENERATOR)),
        generator_version=str(
            value.get("generator_version", PROVENANCE_GENERATOR_VERSION)
        ),
        normative=bool(value.get("normative", False)),
        evidence=evidence,
    )


def _git(root: Path, *args: str) -> str | None:
    try:
        completed = subprocess.run(
            ["git", *args],
            cwd=root,
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    value = completed.stdout.strip()
    return value or None


def _tracked_files(root: Path) -> list[Path]:
    output = _git(root, "ls-files", "-z")
    if not output:
        return [path for path in root.rglob("*") if path.is_file()]
    return [root / item for item in output.split("\0") if item]
