"""Receipt-gated Git publication to an exact configured remote."""

from __future__ import annotations

import re
import hashlib
import subprocess
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.parse import urlparse

AUTHORITY = "rumi.service.host.authorize.v1"
GIT_READ = "rumi.service.git.read.v1"
WORKSPACE = "rumi.resource.workspace.v1"
SERVICE_PACK_ID = "rumi_git_publish_pack"
_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]{0,199}$")
_REMOTE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


class GitPublishService:
    """Publish one branch without owning local Git mutation or credentials."""

    def __init__(self, client: Any) -> None:
        self.client = client

    def invoke(self, name: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        """Push or dry-run an exact remote/branch pair."""
        if name not in {"push", "dry_run"}:
            raise ValueError(f"unknown Git publish operation: {name}")
        arguments = _arguments(payload, dry_run=name == "dry_run")
        root, repository = self._roots(payload)
        _assert_repository_oid_widths(repository, arguments)
        _assert_local_source(
            repository,
            arguments["branch"],
            arguments["expected_source_oid"],
        )
        remote_url = _git(repository, ["remote", "get-url", "--push", arguments["remote"]]).strip()
        if remote_url != arguments["expected_remote_url"]:
            raise PermissionError("Git remote URL changed or was not preflighted")
        remote_host = _remote_host(arguments["expected_remote_url"])
        remote_url_hash = hashlib.sha256(
            arguments["expected_remote_url"].encode("utf-8")
        ).hexdigest()
        if arguments["expected_remote_url_hash"] != remote_url_hash:
            raise PermissionError("Git remote URL changed or was not preflighted")
        self._redeem(name, payload, arguments)
        _assert_local_source(
            repository,
            arguments["branch"],
            arguments["expected_source_oid"],
        )
        current_url = _git(repository, ["remote", "get-url", "--push", arguments["remote"]]).strip()
        if current_url != arguments["expected_remote_url"]:
            raise PermissionError("Git remote URL changed after authorization")
        _assert_non_force_fast_forward(repository, arguments)
        args = ["push"]
        if arguments["dry_run"]:
            args.append("--dry-run")
        # A lease is required for both normal and force flows.  The normal
        # path separately proves its update is fast-forward before using the
        # lease, so this CAS option cannot turn an unapproved non-FF update
        # into a force push.
        args.append(
            "--force-with-lease="
            f"refs/heads/{arguments['branch']}:"
            f"{arguments['expected_remote_oid']}"
        )
        if arguments["set_upstream"]:
            args.append("--set-upstream")
        # Never push a mutable local branch name.  The source side is the
        # object ID sealed into the authority receipt; changing the branch
        # after approval cannot change the bytes that reach the remote.
        exact_refspec = f"{arguments['expected_source_oid']}:refs/heads/{arguments['branch']}"
        # Use the captured push URL itself.  Passing the remote name would
        # re-read .git/config inside `git push`, allowing a retarget after the
        # last hash check to choose a different network destination.
        args.extend(["--", arguments["expected_remote_url"], exact_refspec])
        output = _git(repository, args, timeout=180)
        return {
            "workspace_id": str(payload.get("workspace_id") or ""),
            "repository_root": (
                repository.relative_to(root).as_posix() if repository != root else "."
            ),
            "remote": arguments["remote"],
            "remote_host": remote_host,
            "remote_url": arguments["expected_remote_url"],
            "branch": arguments["branch"],
            "source_oid": arguments["expected_source_oid"],
            "expected_remote_oid": arguments["expected_remote_oid"],
            "force_with_lease": arguments["force_with_lease"],
            "dry_run": arguments["dry_run"],
            "published": not arguments["dry_run"],
            "output": output,
            "authority_receipt_redeemed": True,
        }

    def _roots(self, payload: Mapping[str, Any]) -> tuple[Path, Path]:
        common = {
            "profile_id": _profile(payload),
            "workspace_id": str(payload.get("workspace_id") or ""),
        }
        mount = self.client.invoke(WORKSPACE, "get", common)
        if not isinstance(mount, Mapping):
            raise KeyError("workspace mount is unknown")
        if int(mount.get("mount_revision") or 0) != int(
            payload.get("expected_mount_revision") or -1
        ):
            raise PermissionError("workspace mount revision changed")
        root = Path(str(mount.get("root_path") or "")).resolve(strict=True)
        read = self.client.invoke(GIT_READ, "root", common)
        repository = (root / str(read.get("repository_root") or ".")).resolve(strict=True)
        try:
            repository.relative_to(root)
        except ValueError as exc:
            raise PermissionError("Git repository root escapes workspace") from exc
        return root, repository

    def _redeem(self, name: str, payload: Mapping[str, Any], arguments: Mapping[str, Any]) -> None:
        result = self.client.invoke(
            AUTHORITY,
            "redeem",
            {
                "receipt": str(payload.get("authority_receipt") or ""),
                "service_pack_id": SERVICE_PACK_ID,
                "operation": f"git.publish.{name}",
                "authority": "git.publish",
                "caller_id": str(payload.get("caller_id") or ""),
                "caller_pack_id": str(payload.get("caller_pack_id") or ""),
                "caller_function_id": str(payload.get("caller_function_id") or ""),
                "profile_id": _profile(payload),
                "workspace_id": str(payload.get("workspace_id") or ""),
                "session_id": str(payload.get("session_id") or ""),
                "arguments": dict(arguments),
            },
        )
        if not result.get("authorized"):
            raise PermissionError(str(result.get("reason") or "Git publication denied"))


def create_git_publish_operation(
    client: Any,
) -> Callable[[str, Mapping[str, Any]], Any]:
    """Create receipt-gated Git publication operations."""
    return GitPublishService(client).invoke


def _arguments(payload: Mapping[str, Any], *, dry_run: bool) -> dict[str, Any]:
    remote = str(payload.get("remote") or "origin").strip()
    branch = str(payload.get("branch") or "").strip()
    if not _REMOTE.fullmatch(remote):
        raise ValueError("Git remote name is invalid")
    if not _NAME.fullmatch(branch) or branch.startswith(("-", "/")) or ".." in branch:
        raise ValueError("Git branch is invalid")
    expected_source_oid = _oid(payload.get("expected_source_oid") or payload.get("expected_head"))
    expected_remote_oid = _oid(
        payload.get("expected_remote_oid"),
        allow_zero=True,
    )
    expected_mount_revision = int(payload.get("expected_mount_revision") or -1)
    if expected_mount_revision < 1:
        raise ValueError("expected_mount_revision is required")
    expected_remote_url = str(payload.get("expected_remote_url") or "").strip()
    _remote_host(expected_remote_url)
    expected_remote_url_hash = str(payload.get("expected_remote_url_hash") or "").strip()
    if hashlib.sha256(expected_remote_url.encode("utf-8")).hexdigest() != expected_remote_url_hash:
        raise ValueError("Git remote URL snapshot is invalid")
    return {
        "remote": remote,
        "branch": branch,
        "force_with_lease": bool(payload.get("force_with_lease", False)),
        "set_upstream": bool(payload.get("set_upstream", False)),
        "dry_run": dry_run,
        "expected_remote_url": expected_remote_url,
        "expected_remote_url_hash": expected_remote_url_hash,
        "expected_source_oid": expected_source_oid,
        "expected_remote_oid": expected_remote_oid,
        "expected_mount_revision": expected_mount_revision,
    }


def _oid(value: Any, *, allow_zero: bool = False) -> str:
    normalized = str(value or "").strip().lower()
    if allow_zero and _is_zero_oid(normalized):
        return normalized
    if not re.fullmatch(r"[0-9a-f]{40,64}", normalized):
        raise ValueError("Git object ID is invalid")
    return normalized


def _is_zero_oid(value: str) -> bool:
    """Recognize only supported all-zero Git object-ID widths."""

    return len(value) in {40, 64} and value == "0" * len(value)


def _object_oid_width(repository: Path) -> int:
    """Return the object-ID width selected by this repository."""

    object_format = _git(repository, ["rev-parse", "--show-object-format"]).strip()
    if object_format == "sha1":
        return 40
    if object_format == "sha256":
        return 64
    raise PermissionError("Git object format is unsupported")


def _assert_repository_oid_widths(
    repository: Path,
    arguments: Mapping[str, Any],
) -> None:
    """Reject receipt OIDs whose width differs from the Git object format."""

    object_width = _object_oid_width(repository)
    for field in ("expected_source_oid", "expected_remote_oid"):
        if len(str(arguments[field])) != object_width:
            raise PermissionError(f"Git {field} does not match the repository object format")


def _assert_local_source(
    repository: Path,
    branch: str,
    expected_source_oid: str,
) -> None:
    """Reject a changed source branch before its immutable OID is published."""

    current = _git(repository, ["rev-parse", "--verify", f"refs/heads/{branch}"]).strip()
    if current != expected_source_oid:
        raise PermissionError("Git local source ref changed after preflight")


def _assert_non_force_fast_forward(
    repository: Path,
    arguments: Mapping[str, Any],
) -> None:
    """Require a normal leased push to remain a genuine fast-forward."""

    if arguments["force_with_lease"]:
        return
    expected_remote_oid = arguments["expected_remote_oid"]
    if _is_zero_oid(expected_remote_oid):
        return
    completed = subprocess.run(
        [
            "git",
            "-C",
            str(repository),
            "merge-base",
            "--is-ancestor",
            expected_remote_oid,
            arguments["expected_source_oid"],
        ],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if completed.returncode != 0:
        raise PermissionError(
            "Git normal publication is not a fast-forward from the approved remote"
        )


def _remote_host(remote_url: str) -> str:
    value = str(remote_url or "").strip()
    if value.startswith(("file:", "/", "./", "../", "ext::")):
        raise PermissionError("local and external-helper Git remotes are denied")
    if "://" in value:
        parsed = urlparse(value)
        if parsed.scheme not in {"https", "ssh"} or not parsed.hostname:
            raise PermissionError("Git remote transport is denied")
        return parsed.hostname
    if "@" in value and ":" in value:
        host = value.split("@", 1)[1].split(":", 1)[0]
        if host:
            return host
    raise PermissionError("Git remote URL is not an approved network form")


def _git(repository: Path, args: list[str], *, timeout: int = 30) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repository), *args],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    output = (completed.stdout + completed.stderr)[:256_000]
    if completed.returncode != 0:
        raise RuntimeError(output.strip() or "Git publication failed")
    return output


def _profile(payload: Mapping[str, Any]) -> str:
    return str(payload.get("profile_id") or "default")
