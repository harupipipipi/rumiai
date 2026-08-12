"""Build and bind the closed macOS packaging toolchain.

The formal Python is installed from one checked-in, digest-pinned python.org
installer.  No executable, library, or package is copied from actions/setup-
python.  Runtime requirements are installed from the repository's hash lock
into a root-owned environment inside the official, non-relocatable canonical
Framework version.  Only that exclusive version leaf is transaction-owned;
pre-existing ancestors and sibling versions are validated but never adopted.
Only after an exact inventory is sealed and reverified is that interpreter
executed.
"""

from __future__ import annotations

import argparse
import contextlib
import ctypes
import errno
import hashlib
import json
import os
import posixpath
import selectors
import shutil
import stat
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any


PROVENANCE_SCHEMA = "tobkiri.packaging-python-macos.v1"
INVENTORY_SCHEMA = "tobkiri.packaging-python-installation.v1"
INVENTORY_NAME = ".tobkiri-packaging-python.v1.json"
APPLE_TEAM_ID = "59GAB85EFG"
APPLE_GIT_IDENTIFIER = "com.apple.git"
MACOS_SYSTEM_GIT = Path("/Library/Developer/CommandLineTools/usr/bin/git")
ISOLATED_GIT_EXEC_PATH = Path("/private/var/empty")
ISOLATED_GIT_ARGUMENTS = (
    "--no-optional-locks",
    "--no-replace-objects",
    "-c",
    "core.fsmonitor=false",
    "-c",
    "core.untrackedCache=false",
    "-c",
    "core.hooksPath=/dev/null",
    "-c",
    "core.attributesFile=/dev/null",
    "-c",
    "core.excludesFile=/dev/null",
    "-c",
    "diff.external=",
    "-c",
    "core.sshCommand=false",
    "-c",
    "core.pager=cat",
    "-c",
    "pager.show=cat",
)
STAGING_PARENT = Path("/private/var/tmp")
STAGING_PREFIX = "tobkiri-python-installer-"
SEALED_PROVENANCE_NAME = "authority-provenance.json"
SEALED_REQUIREMENTS_NAME = "authority-requirements.lock"
INSTALLATION_JOURNAL_NAME = ".tobkiri-packaging-transaction.v1.json"
INSTALLATION_JOURNAL_SCHEMA = "tobkiri.packaging-python-transaction.v1"
PROVISIONAL_PREFIX = ".tobkiri-packaging-python-"
DISPLACEMENT_JOURNAL_PREFIX = ".tobkiri-packaging-displacement-"
DISPLACEMENT_JOURNAL_SCHEMA = "tobkiri.packaging-python-displacement.v1"
DISPLACED_PREFIX = ".tobkiri-packaging-displaced-"
INSTALLATION_LOCK_NAME = ".tobkiri-packaging-python.lock"
ANCESTOR_JOURNAL_PREFIX = "ancestor-"
ANCESTOR_JOURNAL_SCHEMA = "tobkiri.packaging-python-ancestor.v1"
ANCESTOR_PROVISIONAL_PREFIX = ".tobkiri-packaging-parent-"

PROVENANCE_FIELDS = frozenset(
    {
        "code_identifier",
        "executable",
        "install_root",
        "installer_sha256",
        "installer_signer",
        "installer_team_id",
        "installer_url",
        "release_page",
        "requirements_path",
        "requirements_sha256",
        "schema",
        "version",
    }
)


class ToolIdentityError(ValueError):
    """Raised when a packaging toolchain cannot be bound safely."""


@dataclass(frozen=True)
class ToolIdentity:
    """Canonical identity emitted for one packaging executable."""

    path: Path
    sha256: str


@dataclass(frozen=True)
class CodeIdentity:
    """Selected immutable fields from a verified macOS code signature."""

    identifier: str
    team_identifier: str
    cdhash: str


@dataclass(frozen=True)
class InstallerProvenance:
    """Strict checked-in authority for the official installer and lock."""

    code_identifier: str
    executable: PurePosixPath
    install_root: Path
    installer_sha256: str
    installer_signer: str
    installer_team_id: str
    installer_url: str
    release_page: str
    requirements_path: PurePosixPath
    requirements_sha256: str
    requirements_bytes: bytes
    version: str


@dataclass(frozen=True)
class MacOSPythonInstallation:
    """A verified root-owned Python installation and inventory lease input."""

    root: Path
    executable: Path
    inventory_sha256: str


def _valid_sha256(value: object) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def _safe_relative(value: object, label: str) -> PurePosixPath:
    if not isinstance(value, str):
        raise ToolIdentityError(f"{label} must be a string")
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or not path.parts
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise ToolIdentityError(f"{label} must be a safe relative path")
    return path


def _strict_json_bytes(encoded: bytes, label: str) -> dict[str, Any]:
    def reject_duplicate(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ToolIdentityError(f"duplicate JSON field: {key}")
            result[key] = value
        return result

    try:
        payload = json.loads(encoded, object_pairs_hook=reject_duplicate)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ToolIdentityError(f"invalid JSON: {label}: {error}") from error
    if not isinstance(payload, dict):
        raise ToolIdentityError(f"JSON object required: {label}")
    return payload


def _strict_json(path: Path) -> dict[str, Any]:
    try:
        encoded = path.read_bytes()
    except OSError as error:
        raise ToolIdentityError(f"invalid JSON: {path}: {error}") from error
    return _strict_json_bytes(encoded, os.fspath(path))


def _parse_provenance(
    encoded: bytes, requirements_bytes: bytes, label: str
) -> InstallerProvenance:
    payload = _strict_json_bytes(encoded, label)
    if set(payload) != PROVENANCE_FIELDS or payload.get("schema") != PROVENANCE_SCHEMA:
        raise ToolIdentityError("packaging Python provenance schema/fields mismatch")
    for field in ("installer_sha256", "requirements_sha256"):
        if not _valid_sha256(payload[field]):
            raise ToolIdentityError(f"{field} must be lowercase SHA-256")
    url = payload["installer_url"]
    if not isinstance(url, str) or not url.startswith(
        "https://www.python.org/ftp/python/"
    ):
        raise ToolIdentityError("installer_url must be a fixed python.org HTTPS URL")
    version = payload["version"]
    expected_name = f"python-{version}-macos11.pkg"
    if not url.endswith(f"/{version}/{expected_name}"):
        raise ToolIdentityError("installer URL does not match the pinned version")
    release_slug = version.replace(".", "")
    release_page = payload["release_page"]
    if (
        release_page
        != f"https://www.python.org/downloads/release/python-{release_slug}/"
    ):
        raise ToolIdentityError("release_page does not match the pinned version")
    install_root = Path(payload["install_root"])
    if install_root != Path(
        f"/Library/Frameworks/Python.framework/Versions/{'.'.join(version.split('.')[:2])}"
    ):
        raise ToolIdentityError("install_root does not match the pinned Python series")
    requirements_relative = _safe_relative(
        payload["requirements_path"], "requirements_path"
    )
    if hashlib.sha256(requirements_bytes).hexdigest() != payload["requirements_sha256"]:
        raise ToolIdentityError("hash-locked packaging requirements digest mismatch")
    for field in (
        "code_identifier",
        "installer_signer",
        "installer_team_id",
        "version",
    ):
        if not isinstance(payload[field], str) or not payload[field]:
            raise ToolIdentityError(f"{field} must be a nonempty string")
    if payload["installer_team_id"] not in payload["installer_signer"]:
        raise ToolIdentityError("installer signer is not bound to its pinned Team ID")
    return InstallerProvenance(
        code_identifier=payload["code_identifier"],
        executable=_safe_relative(payload["executable"], "executable"),
        install_root=install_root,
        installer_sha256=payload["installer_sha256"],
        installer_signer=payload["installer_signer"],
        installer_team_id=payload["installer_team_id"],
        installer_url=url,
        release_page=release_page,
        requirements_path=requirements_relative,
        requirements_sha256=payload["requirements_sha256"],
        requirements_bytes=requirements_bytes,
        version=version,
    )


def load_provenance(path: Path, repository_root: Path) -> InstallerProvenance:
    """Load checkout bytes for review tooling, never for production binding."""
    encoded = path.read_bytes()
    payload = _strict_json_bytes(encoded, os.fspath(path))
    requirements_relative = _safe_relative(
        payload.get("requirements_path"), "requirements_path"
    )
    return _parse_provenance(
        encoded,
        (repository_root / requirements_relative).read_bytes(),
        os.fspath(path),
    )


def _file_identity(metadata: os.stat_result) -> tuple[int, int, int, int, int]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
    )


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_absolute(path: Path, label: str) -> Path:
    if not path.is_absolute():
        raise ToolIdentityError(f"{label} path must be absolute: {path}")
    try:
        canonical = path.resolve(strict=True)
    except OSError as error:
        raise ToolIdentityError(
            f"{label} cannot be resolved: {path}: {error}"
        ) from error
    if canonical != path:
        raise ToolIdentityError(f"{label} path is not canonical: {path}")
    return path


def _regular_executable(path: Path, label: str) -> ToolIdentity:
    path = _canonical_absolute(path, label)
    before = path.lstat()
    if path.is_symlink() or not stat.S_ISREG(before.st_mode):
        raise ToolIdentityError(f"{label} is not a regular file: {path}")
    if not os.access(path, os.X_OK) or before.st_mode & 0o022:
        raise ToolIdentityError(f"{label} is not immutable and executable: {path}")
    digest = _sha256_file(path)
    after = path.lstat()
    if path.is_symlink() or _file_identity(before) != _file_identity(after):
        raise ToolIdentityError(f"{label} changed while hashed: {path}")
    return ToolIdentity(path, digest)


def _caller_identity() -> tuple[int, frozenset[int]]:
    """Return the effective caller and every group that grants mode authority."""
    return os.geteuid(), frozenset((os.getegid(), *os.getgroups()))


def _caller_identity_arguments() -> tuple[str, str]:
    caller_uid, caller_groups = _caller_identity()
    return str(caller_uid), ",".join(str(group) for group in sorted(caller_groups))


def _caller_can_write(metadata: os.stat_result) -> bool:
    mode = stat.S_IMODE(metadata.st_mode)
    caller_uid, caller_groups = _caller_identity()
    if metadata.st_uid == caller_uid:
        return bool(mode & stat.S_IWUSR)
    if metadata.st_gid in caller_groups:
        return bool(mode & stat.S_IWGRP)
    return bool(mode & stat.S_IWOTH)


def _fd_has_nontrivial_acl(descriptor: int) -> bool:
    """Fail closed on any macOS extended ACL attached to the opened inode."""
    if sys.platform != "darwin":
        return False
    library = ctypes.CDLL(None, use_errno=True)
    library.acl_get_fd_np.argtypes = [ctypes.c_int, ctypes.c_int]
    library.acl_get_fd_np.restype = ctypes.c_void_p
    library.acl_free.argtypes = [ctypes.c_void_p]
    library.acl_free.restype = ctypes.c_int
    ctypes.set_errno(0)
    acl = library.acl_get_fd_np(descriptor, 0x00000100)
    if not acl:
        error = ctypes.get_errno()
        if error == errno.ENOENT:
            return False
        raise ToolIdentityError(f"could not inspect macOS ACL: errno={error}")
    if library.acl_free(acl) != 0:
        raise ToolIdentityError("could not release macOS ACL")
    return True


def _require_opened_authority(
    descriptor: int, component: Path, label: str, *, sticky: Path | None
) -> None:
    metadata = os.fstat(descriptor)
    sticky_root = (
        sticky is not None
        and component == sticky
        and metadata.st_uid == 0
        and stat.S_ISDIR(metadata.st_mode)
        and bool(metadata.st_mode & stat.S_ISVTX)
    )
    if metadata.st_uid != 0:
        raise ToolIdentityError(f"{label} contains non-root authority: {component}")
    if _fd_has_nontrivial_acl(descriptor):
        raise ToolIdentityError(f"{label} contains nontrivial ACL: {component}")
    if _caller_can_write(metadata) and not sticky_root:
        raise ToolIdentityError(f"{label} contains writable authority: {component}")


def _root_owned_path(path: Path, label: str, *, sticky: Path | None = None) -> None:
    path = _canonical_absolute(path, label)
    descriptor = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    component = Path("/")
    try:
        _require_opened_authority(descriptor, component, label, sticky=sticky)
        for index, part in enumerate(path.parts[1:]):
            flags = os.O_RDONLY | os.O_NOFOLLOW
            if index < len(path.parts[1:]) - 1:
                flags |= os.O_DIRECTORY
            child = os.open(part, flags, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
            component /= part
            _require_opened_authority(descriptor, component, label, sticky=sticky)
    finally:
        os.close(descriptor)


ROOT_SEAL_TREE_CODE = r"""
import ctypes, errno, json, os, posixpath, stat, sys, time
root_path=sys.argv[1]; owner=int(sys.argv[2]); root_mode=int(sys.argv[3],8)
barrier=sys.argv[4] if len(sys.argv)>4 else ''
def acl(fd):
    if sys.platform!='darwin': return False
    lib=ctypes.CDLL(None,use_errno=True); lib.acl_get_fd_np.argtypes=[ctypes.c_int,ctypes.c_int]; lib.acl_get_fd_np.restype=ctypes.c_void_p
    lib.acl_free.argtypes=[ctypes.c_void_p]; lib.acl_free.restype=ctypes.c_int
    ctypes.set_errno(0); value=lib.acl_get_fd_np(fd,0x100)
    if not value:
        if ctypes.get_errno()==errno.ENOENT: return False
        raise SystemExit('ACL inspection failed')
    if lib.acl_free(value)!=0: raise SystemExit('ACL release failed')
    return True
def safe_target(relative,target):
    if not target or '\x00' in target or target.startswith('/'):
        raise SystemExit('unsafe absolute or empty symlink: '+relative)
    normalized=posixpath.normpath(posixpath.join(posixpath.dirname(relative),target))
    if normalized in ('','.') or normalized=='..' or normalized.startswith('../'):
        raise SystemExit('symlink escapes sealed tree: '+relative)
    return normalized
def entry(fd,name,relative,mutate,device):
    before=os.stat(name,dir_fd=fd,follow_symlinks=False)
    if before.st_uid!=owner: raise SystemExit('non-owner tree entry: '+relative)
    if before.st_dev!=device: raise SystemExit('mount boundary in sealed tree: '+relative)
    if stat.S_ISLNK(before.st_mode):
        if before.st_nlink!=1: raise SystemExit('hardlinked tree symlink: '+relative)
        # Name mutation is controlled by the held, root-owned parent directory;
        # symlink permission/ACL bits do not grant rename authority on macOS.
        target=os.readlink(name,dir_fd=fd)
        after=os.stat(name,dir_fd=fd,follow_symlinks=False)
        if (before.st_dev,before.st_ino,before.st_mode)!=(after.st_dev,after.st_ino,after.st_mode):
            raise SystemExit('symlink changed during inventory: '+relative)
        return ('symlink',before.st_dev,before.st_ino,stat.S_IMODE(before.st_mode),target,
                safe_target(relative,target))
    flags=os.O_RDONLY|os.O_NOFOLLOW
    if stat.S_ISDIR(before.st_mode): flags|=os.O_DIRECTORY
    opened=os.open(name,flags,dir_fd=fd)
    try:
        current=os.fstat(opened)
        if (before.st_dev,before.st_ino,before.st_mode)!=(current.st_dev,current.st_ino,current.st_mode):
            raise SystemExit('tree entry changed while opened: '+relative)
        if acl(opened): raise SystemExit('tree entry has nontrivial ACL: '+relative)
        if stat.S_ISREG(current.st_mode):
            if current.st_nlink!=1: raise SystemExit('hardlinked tree file: '+relative)
            if mutate: os.fchmod(opened,stat.S_IMODE(current.st_mode)&~0o222)
            sealed=os.fstat(opened)
            return ('file',sealed.st_dev,sealed.st_ino,stat.S_IMODE(sealed.st_mode),'','')
        if not stat.S_ISDIR(current.st_mode):
            raise SystemExit('special file in sealed tree: '+relative)
        children=walk(opened,relative,mutate,device)
        if mutate: os.fchmod(opened,stat.S_IMODE(current.st_mode)&~0o222)
        sealed=os.fstat(opened)
        return ('directory',sealed.st_dev,sealed.st_ino,stat.S_IMODE(sealed.st_mode),'',
                json.dumps(children,sort_keys=True,separators=(',',':')))
    finally: os.close(opened)
def walk(fd,prefix,mutate,device):
    result={}
    for name in sorted(os.listdir(fd)):
        if not name or name in ('.','..') or '/' in name or '\x00' in name:
            raise SystemExit('invalid tree entry name')
        relative=name if not prefix else prefix+'/'+name
        result[name]=entry(fd,name,relative,mutate,device)
    return result
def check_cycles(records,prefix=''):
    links={}
    def collect(values,base=''):
        for name,value in values.items():
            path=name if not base else base+'/'+name
            if value[0]=='symlink': links[path]=value[5]
            elif value[0]=='directory': collect(json.loads(value[5]),path)
    collect(records)
    for origin,target in links.items():
        value=target; seen={origin}
        for _ in range(129):
            parts=value.split('/'); found=None
            for index in range(1,len(parts)+1):
                candidate='/'.join(parts[:index])
                if candidate in links: found=(candidate,index); break
            if found is None: break
            candidate,index=found
            if candidate in seen: raise SystemExit('symlink cycle in sealed tree: '+origin)
            seen.add(candidate)
            suffix='/'.join(parts[index:])
            value=posixpath.normpath(posixpath.join(links[candidate],suffix))
            if value=='..' or value.startswith('../') or value.startswith('/'):
                raise SystemExit('symlink chain escapes sealed tree: '+origin)
        else: raise SystemExit('symlink chain exceeds bound: '+origin)
root=os.open(root_path,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
try:
    info=os.fstat(root)
    if info.st_uid!=owner or stat.S_IMODE(info.st_mode)!=0o700 or acl(root):
        raise SystemExit('unsafe sealed tree root')
    first=walk(root,'',True,info.st_dev); check_cycles(first)
    os.fchmod(root,root_mode); os.fsync(root)
    if barrier:
        ready=barrier+'.ready'; release=barrier+'.release'
        with open(ready,'xb') as output: output.write(b'ready'); output.flush(); os.fsync(output.fileno())
        deadline=time.monotonic()+10
        while not os.path.exists(release):
            if time.monotonic()>=deadline: raise SystemExit('seal test barrier timed out')
            time.sleep(0.01)
    second=walk(root,'',False,info.st_dev); check_cycles(second)
    if first!=second: raise SystemExit('sealed tree changed during verification')
    final=os.fstat(root)
    if (final.st_dev,final.st_ino)!=(info.st_dev,info.st_ino) or \
       stat.S_IMODE(final.st_mode)!=root_mode or acl(root):
        raise SystemExit('sealed tree root changed')
finally: os.close(root)
"""


def _seal_root_tree(root: Path, label: str) -> None:
    """Seal a root-owned tree by inode without following or chmodding symlinks."""
    result = subprocess.run(
        [
            "/usr/bin/sudo",
            "-n",
            "/usr/bin/python3",
            "-I",
            "-B",
            "-c",
            ROOT_SEAL_TREE_CODE,
            root,
            "0",
            "0555",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
        env={"PATH": "/usr/bin:/bin"},
    )
    if result.returncode != 0:
        raise ToolIdentityError(f"{label} sealing failed: {result.stderr.strip()}")


def _codesign_identity(path: Path) -> CodeIdentity:
    verified = subprocess.run(
        ["/usr/bin/codesign", "--verify", "--strict", "--all-architectures", path],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if verified.returncode != 0:
        raise ToolIdentityError(
            f"invalid code signature: {path}: {verified.stderr.strip()}"
        )
    details = subprocess.run(
        ["/usr/bin/codesign", "-d", "--verbose=4", path],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    fields: dict[str, str] = {}
    for line in details.stderr.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            fields[key] = value
    flags = fields.get("CodeDirectory", "")
    cdhash = fields.get("CDHash") or fields.get("CandidateCDHash")
    if details.returncode != 0 or "adhoc" in flags or not cdhash:
        raise ToolIdentityError(f"unusable macOS code identity: {path}")
    return CodeIdentity(
        fields.get("Identifier", ""), fields.get("TeamIdentifier", ""), cdhash
    )


def _require_code_authority(
    path: Path, *, identifier: str, team_identifier: str, label: str
) -> CodeIdentity:
    identity = _codesign_identity(path)
    if identity.identifier != identifier or identity.team_identifier != team_identifier:
        raise ToolIdentityError(
            f"{label} signer is not authorized: {identity.identifier}/{identity.team_identifier}"
        )
    return identity


def _valid_commit(value: str) -> bool:
    return len(value) == 40 and all(
        character in "0123456789abcdef" for character in value
    )


def _valid_transaction_token(value: str) -> bool:
    return len(value) == 32 and all(
        character in "0123456789abcdef" for character in value
    )


def _transaction_path(token: str) -> Path:
    if not _valid_transaction_token(token):
        raise ToolIdentityError(
            "transaction token must be 32 lowercase hexadecimal bytes"
        )
    return STAGING_PARENT / f"{STAGING_PREFIX}{token}"


def _git_result(
    git: ToolIdentity, repository_root: Path, *arguments: str
) -> subprocess.CompletedProcess[bytes]:
    current = _regular_executable(git.path, "Git")
    if current != git:
        raise ToolIdentityError("trusted Git identity changed before execution")
    if sys.platform == "darwin":
        if git.path != MACOS_SYSTEM_GIT:
            raise ToolIdentityError("trusted Git escaped the fixed system authority")
        _root_owned_path(git.path, "Git")
        _require_code_authority(
            git.path,
            identifier=APPLE_GIT_IDENTIFIER,
            team_identifier=APPLE_TEAM_ID,
            label="Git",
        )
    result = subprocess.run(
        [
            git.path,
            *ISOLATED_GIT_ARGUMENTS,
            "-C",
            repository_root,
            *arguments,
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        # GIT_CONFIG redirects only `git config`; safety for every other command
        # comes from the fixed plumbing set and Core byte/inventory verification.
        env={
            "GIT_ATTR_NOSYSTEM": "1",
            "GIT_CEILING_DIRECTORIES": os.fspath(repository_root),
            "GIT_CONFIG": os.devnull,
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_SYSTEM": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_EXEC_PATH": os.fspath(ISOLATED_GIT_EXEC_PATH),
            "GIT_OPTIONAL_LOCKS": "0",
            "GIT_PAGER": "cat",
            "GIT_TERMINAL_PROMPT": "0",
            "HOME": os.fspath(ISOLATED_GIT_EXEC_PATH),
            "LC_ALL": "C",
            "PATH": "/usr/bin:/bin",
            "PAGER": "cat",
            "XDG_CONFIG_HOME": os.fspath(ISOLATED_GIT_EXEC_PATH),
        },
    )
    return result


def _git_output(git: ToolIdentity, repository_root: Path, *arguments: str) -> bytes:
    result = _git_result(git, repository_root, *arguments)
    if result.returncode != 0:
        raise ToolIdentityError(
            f"trusted Git object read failed: {result.stderr.decode(errors='replace')}"
        )
    return result.stdout


def _verify_clean_checkout(
    git: ToolIdentity, repository_root: Path, commit: str
) -> None:
    """Verify index and worktree bytes without porcelain or conversion filters."""
    result = _git_result(
        git,
        repository_root,
        "diff-index",
        "--cached",
        "--quiet",
        "--no-ext-diff",
        "--no-textconv",
        "--ignore-submodules=none",
        commit,
        "--",
    )
    if result.returncode == 1:
        raise ToolIdentityError("trusted Git repository is not clean")
    if result.returncode != 0:
        raise ToolIdentityError(
            "trusted Git clean plumbing failed: "
            + result.stderr.decode(errors="replace")
        )
    tree = _git_output(
        git, repository_root, "ls-tree", "-r", "-z", "--full-tree", commit
    )
    for record in tree.split(b"\0"):
        if not record:
            continue
        try:
            header, encoded_path = record.split(b"\t", 1)
            mode, kind, expected = header.split(b" ", 2)
            relative = _safe_relative(encoded_path.decode("utf-8"), "Git tree path")
        except (UnicodeDecodeError, ValueError) as error:
            raise ToolIdentityError("trusted Git tree entry is malformed") from error
        if kind != b"blob" or mode not in {b"100644", b"100755", b"120000"}:
            raise ToolIdentityError("trusted Git tree contains an unsupported entry")
        path = repository_root.joinpath(*relative.parts)
        before = path.lstat()
        if mode == b"120000":
            if not stat.S_ISLNK(before.st_mode):
                raise ToolIdentityError(f"tracked symlink type changed: {relative}")
            payload = os.fsencode(os.readlink(path))
            after = path.lstat()
        else:
            if not stat.S_ISREG(before.st_mode) or path.is_symlink():
                raise ToolIdentityError(f"tracked file type changed: {relative}")
            executable = bool(before.st_mode & 0o111)
            if executable != (mode == b"100755"):
                raise ToolIdentityError(f"tracked executable mode changed: {relative}")
            descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
            try:
                opened = os.fstat(descriptor)
                chunks: list[bytes] = []
                while chunk := os.read(descriptor, 1024 * 1024):
                    chunks.append(chunk)
                payload = b"".join(chunks)
                after = os.fstat(descriptor)
            finally:
                os.close(descriptor)
            if _file_identity(before) != _file_identity(opened):
                raise ToolIdentityError(f"tracked file changed before read: {relative}")
        if _file_identity(before) != _file_identity(after):
            raise ToolIdentityError(f"tracked path changed while read: {relative}")
        framed = f"blob {len(payload)}\0".encode() + payload
        if len(expected) == 40:
            actual = hashlib.sha1(framed, usedforsecurity=True).hexdigest()
        elif len(expected) == 64:
            actual = hashlib.sha256(framed).hexdigest()
        else:
            raise ToolIdentityError("trusted Git blob object ID length is unsupported")
        if actual.encode() != expected:
            raise ToolIdentityError(f"tracked file bytes changed: {relative}")
    # This binder runs before Rust creates src-tauri/gen; its contract is zero
    # untracked paths. Only build.rs owns the later, type-checked gen allowlist.
    untracked = _git_output(
        git,
        repository_root,
        "ls-files",
        "--others",
        "-z",
        "--",
    )
    if untracked:
        raise ToolIdentityError("trusted Git repository has untracked paths")


def _committed_blob(
    git: ToolIdentity, repository_root: Path, commit: str, relative: PurePosixPath
) -> bytes:
    if not _valid_commit(commit):
        raise ToolIdentityError("source commit must be a full lowercase Git SHA")
    head = _git_output(git, repository_root, "rev-parse", "--verify", "HEAD^{commit}")
    if head != f"{commit}\n".encode():
        raise ToolIdentityError("source commit does not match checked-out HEAD")
    return _git_output(git, repository_root, "show", f"{commit}:{relative.as_posix()}")


def smoke_git_authority(
    git: ToolIdentity,
    repository_root: Path,
    commit: str,
    committed_path: PurePosixPath,
) -> None:
    """Exercise only built-in read operations under the isolated Git authority."""
    head = _git_output(git, repository_root, "rev-parse", "--verify", "HEAD^{commit}")
    if not _valid_commit(commit) or head != f"{commit}\n".encode():
        raise ToolIdentityError("trusted Git HEAD smoke mismatch")
    if not _git_output(git, repository_root, "show", f"{commit}:{committed_path}"):
        raise ToolIdentityError("trusted Git committed blob smoke returned no bytes")
    _verify_clean_checkout(git, repository_root, commit)


def _seal_root_bytes(path: Path, encoded: bytes) -> None:
    result = subprocess.run(
        ["/usr/bin/sudo", "/usr/bin/tee", path],
        input=encoded,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        raise ToolIdentityError(
            f"could not seal authority bytes: {result.stderr.decode()}"
        )
    subprocess.run(["/usr/bin/sudo", "/usr/sbin/chown", "root:wheel", path], check=True)
    subprocess.run(["/usr/bin/sudo", "/bin/chmod", "0444", path], check=True)


def seal_committed_authority(
    git: ToolIdentity,
    repository_root: Path,
    commit: str,
    provenance_relative: PurePosixPath,
    token: str,
) -> tuple[InstallerProvenance, Path]:
    """Seal exact HEAD blobs once; production never reopens checkout files."""
    staging = _transaction_path(token)
    subprocess.run(["/usr/bin/sudo", "/bin/mkdir", "-m", "0700", staging], check=True)
    try:
        provenance_bytes = _committed_blob(
            git, repository_root, commit, provenance_relative
        )
        preview = _strict_json_bytes(provenance_bytes, "trusted Git provenance blob")
        requirements_relative = _safe_relative(
            preview.get("requirements_path"), "requirements_path"
        )
        requirements_bytes = _committed_blob(
            git, repository_root, commit, requirements_relative
        )
        _seal_root_bytes(staging / SEALED_PROVENANCE_NAME, provenance_bytes)
        _seal_root_bytes(staging / SEALED_REQUIREMENTS_NAME, requirements_bytes)
        subprocess.run(["/usr/bin/sudo", "/bin/chmod", "0555", staging], check=True)
        _root_owned_path(staging, "sealed packaging authority", sticky=STAGING_PARENT)
        sealed_provenance = (staging / SEALED_PROVENANCE_NAME).read_bytes()
        sealed_requirements = (staging / SEALED_REQUIREMENTS_NAME).read_bytes()
        if (
            sealed_provenance != provenance_bytes
            or sealed_requirements != requirements_bytes
        ):
            raise ToolIdentityError(
                "sealed packaging authority changed during creation"
            )
        return (
            _parse_provenance(
                sealed_provenance,
                sealed_requirements,
                "sealed trusted Git provenance",
            ),
            staging,
        )
    except Exception:
        try:
            _remove_root_tree(staging)
        except Exception:
            pass
        raise


def load_sealed_authority(token: str) -> tuple[InstallerProvenance, Path]:
    staging = _transaction_path(token)
    _root_owned_path(staging, "sealed packaging authority", sticky=STAGING_PARENT)
    provenance_bytes = (staging / SEALED_PROVENANCE_NAME).read_bytes()
    requirements_bytes = (staging / SEALED_REQUIREMENTS_NAME).read_bytes()
    return (
        _parse_provenance(
            provenance_bytes, requirements_bytes, "sealed trusted Git provenance"
        ),
        staging,
    )


ROOT_REMOVE_CODE = r"""
import ctypes, errno, os, stat, sys
target = os.path.normpath(sys.argv[1])
owner = int(sys.argv[2])
caller_uid = int(sys.argv[3]); caller_groups = {int(value) for value in sys.argv[4].split(',') if value}
expected = None if len(sys.argv) == 5 else (int(sys.argv[5]), int(sys.argv[6]))
if not target.startswith('/') or target == '/': raise SystemExit('unsafe removal target')
def caller_can_write(info):
    mode = stat.S_IMODE(info.st_mode)
    if info.st_uid == caller_uid: return bool(mode & 0o200)
    if info.st_gid in caller_groups: return bool(mode & 0o020)
    return bool(mode & 0o002)
def nontrivial_acl(fd):
    if sys.platform != 'darwin': return False
    lib=ctypes.CDLL(None,use_errno=True); lib.acl_get_fd_np.argtypes=[ctypes.c_int,ctypes.c_int]; lib.acl_get_fd_np.restype=ctypes.c_void_p
    lib.acl_free.argtypes=[ctypes.c_void_p]; lib.acl_free.restype=ctypes.c_int
    ctypes.set_errno(0); acl=lib.acl_get_fd_np(fd,0x100)
    if not acl:
        if ctypes.get_errno()==errno.ENOENT: return False
        raise SystemExit('ACL inspection failed')
    if lib.acl_free(acl) != 0: raise SystemExit('ACL release failed')
    return True
parts = [part for part in target.split('/') if part]
parent = os.open('/', os.O_RDONLY | os.O_DIRECTORY)
try:
    root_info = os.fstat(parent)
    if root_info.st_uid != 0 or caller_can_write(root_info) or nontrivial_acl(parent):
        raise SystemExit('unsafe root authority or ACL')
    for part in parts[:-1]:
        child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
        info = os.fstat(child)
        sticky_root = info.st_uid == 0 and info.st_mode & stat.S_ISVTX
        if info.st_uid not in (0, owner) or nontrivial_acl(child) or \
           (caller_can_write(info) and not sticky_root):
            raise SystemExit('unsafe removal ancestor')
        os.close(parent); parent = child
    name = parts[-1]
    try: root = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
    except FileNotFoundError: raise SystemExit(0)
    before = os.fstat(root)
    if nontrivial_acl(root): raise SystemExit('removal target has nontrivial ACL')
    if expected is not None and (before.st_dev, before.st_ino) != expected:
        raise SystemExit('removal target does not match transaction journal')
    def empty(fd):
        os.fchown(fd, owner, -1); os.fchmod(fd, 0o700)
        for entry in os.listdir(fd):
            info = os.stat(entry, dir_fd=fd, follow_symlinks=False)
            if stat.S_ISDIR(info.st_mode):
                child = os.open(entry, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                empty(child); os.close(child); os.rmdir(entry, dir_fd=fd)
            else: os.unlink(entry, dir_fd=fd)
    empty(root); os.close(root)
    current = os.stat(name, dir_fd=parent, follow_symlinks=False)
    if (current.st_dev, current.st_ino) != (before.st_dev, before.st_ino):
        raise SystemExit('removal target identity changed')
    os.rmdir(name, dir_fd=parent)
finally: os.close(parent)
"""


def _remove_root_tree(path: Path, identity: tuple[int, int] | None = None) -> None:
    caller_uid, caller_groups = _caller_identity_arguments()
    arguments: list[object] = [
        "/usr/bin/sudo",
        "/usr/bin/python3",
        "-I",
        "-B",
        "-c",
        ROOT_REMOVE_CODE,
        path,
        "0",
        caller_uid,
        caller_groups,
    ]
    if identity is not None:
        arguments.extend(str(value) for value in identity)
    result = subprocess.run(
        arguments,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise ToolIdentityError(
            f"root cleanup failed for {path}: {result.stderr.strip()}"
        )


ROOT_ENSURE_PARENT_CODE = r"""
import ctypes, errno, json, os, signal, stat, sys
anchor_path, relative, staging_path, token, journal_schema, provisional_prefix = sys.argv[1:7]
owner = int(sys.argv[7]); group = int(sys.argv[8])
caller_uid = int(sys.argv[9]); caller_groups = {int(value) for value in sys.argv[10].split(',') if value}
failpoint = sys.argv[11] if len(sys.argv) > 11 else ''
parts = relative.split('/')
if not parts or any(not part or part in ('.', '..') or '/' in part for part in parts):
    raise SystemExit('unsafe ancestor path')
if len(token) != 32 or any(c not in '0123456789abcdef' for c in token):
    raise SystemExit('invalid transaction token')
def canonical(payload):
    return json.dumps(payload, sort_keys=True, separators=(',', ':')).encode() + b'\n'
def caller_can_write(info):
    mode = stat.S_IMODE(info.st_mode)
    if info.st_uid == caller_uid: return bool(mode & 0o200)
    if info.st_gid in caller_groups: return bool(mode & 0o020)
    return bool(mode & 0o002)
def nontrivial_acl(fd):
    if sys.platform != 'darwin': return False
    lib=ctypes.CDLL(None,use_errno=True); lib.acl_get_fd_np.argtypes=[ctypes.c_int,ctypes.c_int]; lib.acl_get_fd_np.restype=ctypes.c_void_p
    lib.acl_free.argtypes=[ctypes.c_void_p]; lib.acl_free.restype=ctypes.c_int
    ctypes.set_errno(0); acl=lib.acl_get_fd_np(fd,0x100)
    if not acl:
        if ctypes.get_errno()==errno.ENOENT: return False
        raise SystemExit('ACL inspection failed')
    if lib.acl_free(acl) != 0: raise SystemExit('ACL release failed')
    return True
def exclusive_rename(parent, source, destination):
    if sys.platform == 'darwin':
        function = ctypes.CDLL(None, use_errno=True).renameatx_np
        function.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int,
                             ctypes.c_char_p, ctypes.c_uint]
        if function(parent, os.fsencode(source), parent, os.fsencode(destination), 4):
            raise OSError(ctypes.get_errno(), 'exclusive rename failed')
    else:
        try: os.stat(destination, dir_fd=parent, follow_symlinks=False)
        except FileNotFoundError: pass
        else: raise FileExistsError(errno.EEXIST, 'ancestor already exists')
        os.rename(source, destination, src_dir_fd=parent, dst_dir_fd=parent)
def read_journal(staging, name):
    info = os.stat(name, dir_fd=staging, follow_symlinks=False)
    if not stat.S_ISREG(info.st_mode) or info.st_uid != owner or info.st_gid != group or \
       stat.S_IMODE(info.st_mode) != 0o400 or info.st_nlink != 1:
        raise SystemExit('invalid ancestor journal metadata')
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=staging)
    try: encoded = os.read(fd, 4097)
    finally: os.close(fd)
    try:
        pairs = json.loads(encoded, object_pairs_hook=lambda value: value)
        if not isinstance(pairs, list): raise ValueError()
        keys = [key for key, _ in pairs]
        if len(keys) != len(set(keys)): raise ValueError()
        payload = dict(pairs)
    except Exception: raise SystemExit('partial or invalid ancestor journal')
    if len(encoded) > 4096 or canonical(payload) != encoded or \
       set(payload) != {'dev','ino','schema','target','token'}:
        raise SystemExit('noncanonical ancestor journal')
    if payload['schema'] != journal_schema or payload['token'] != token:
        raise SystemExit('ancestor journal authority mismatch')
    return payload
anchor = os.open(anchor_path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
staging = os.open(staging_path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
current = anchor
try:
    for descriptor in (anchor, staging):
        info = os.fstat(descriptor)
        has_acl = nontrivial_acl(descriptor)
        if info.st_uid != owner or info.st_gid != group or caller_can_write(info) or has_acl:
            raise SystemExit('unsafe ancestor authority: uid=%d gid=%d mode=%#o acl=%d' %
                             (info.st_uid, info.st_gid, stat.S_IMODE(info.st_mode), has_acl))
    traversed = []
    for index, part in enumerate(parts):
        traversed.append(part)
        target = '/'.join(traversed)
        journal_name = f'ancestor-{index:04d}.json'
        provisional = f'{provisional_prefix}{token}-{index:04d}'
        try: payload = read_journal(staging, journal_name)
        except FileNotFoundError: payload = None
        try:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                            dir_fd=current)
        except FileNotFoundError:
            child = None
        if child is None and payload is not None:
            provisional_fd = os.open(provisional, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                                     dir_fd=current)
            info = os.fstat(provisional_fd); os.close(provisional_fd)
            if info.st_uid != owner or info.st_gid != group or \
               stat.S_IMODE(info.st_mode) != 0o555 or payload['target'] != target or \
               (payload['dev'], payload['ino']) != (info.st_dev, info.st_ino):
                raise SystemExit('ancestor provisional identity mismatch')
            exclusive_rename(current, provisional, part); os.fsync(current)
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                            dir_fd=current)
        elif child is None:
            try:
                stale = os.open(provisional, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                                dir_fd=current)
            except FileNotFoundError: stale = None
            if stale is not None:
                stale_info = os.fstat(stale); entries = os.listdir(stale); os.close(stale)
                if stale_info.st_uid != owner or stale_info.st_gid != group or \
                   stat.S_IMODE(stale_info.st_mode) != 0o700 or entries:
                    raise SystemExit('unsafe unjournaled ancestor provisional')
                os.rmdir(provisional, dir_fd=current); os.fsync(current)
            os.mkdir(provisional, 0o700, dir_fd=current)
            if failpoint == f'after_mkdir:{index}': os.kill(os.getpid(), signal.SIGKILL)
            provisional_fd = os.open(provisional, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                                     dir_fd=current)
            os.fchown(provisional_fd, owner, group); os.fchmod(provisional_fd, 0o700)
            info = os.fstat(provisional_fd)
            payload = {'dev': info.st_dev, 'ino': info.st_ino, 'schema': journal_schema,
                       'target': target, 'token': token}
            encoded = canonical(payload)
            journal = os.open(journal_name, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                              os.O_NOFOLLOW, 0o400, dir_fd=staging)
            try:
                os.fchown(journal, owner, group); os.fchmod(journal, 0o400)
                offset = 0
                while offset < len(encoded): offset += os.write(journal, encoded[offset:])
                os.fsync(journal)
            finally: os.close(journal)
            os.fchown(provisional_fd, owner, group); os.fchmod(provisional_fd, 0o555)
            os.fsync(provisional_fd); os.fsync(staging); os.fsync(current)
            if failpoint == f'after_publish_mode:{index}':
                os.kill(os.getpid(), signal.SIGKILL)
            exclusive_rename(current, provisional, part); os.fsync(current)
            os.close(provisional_fd)
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                            dir_fd=current)
        info = os.fstat(child)
        if info.st_uid != owner or caller_can_write(info) or nontrivial_acl(child):
            raise SystemExit('unsafe existing ancestor: component=%s uid=%d gid=%d mode=%#o' %
                             (target, info.st_uid, info.st_gid,
                              stat.S_IMODE(info.st_mode)))
        if payload is not None and (info.st_gid != group or
           stat.S_IMODE(info.st_mode) != 0o555 or payload['target'] != target or
           (payload['dev'], payload['ino']) != (info.st_dev, info.st_ino)):
            raise SystemExit('created ancestor identity changed')
        if current != anchor: os.close(current)
        current = child
finally:
    if current != anchor: os.close(current)
    os.close(anchor); os.close(staging)
"""


ROOT_CLEANUP_ANCESTORS_CODE = r"""
import ctypes, errno, json, os, stat, sys
anchor_path, relative, staging_path, token, journal_schema = sys.argv[1:6]
owner = int(sys.argv[6]); group = int(sys.argv[7])
caller_uid = int(sys.argv[8]); caller_groups = {int(value) for value in sys.argv[9].split(',') if value}
provisional_prefix = '.tobkiri-packaging-parent-'
def canonical(payload):
    return json.dumps(payload, sort_keys=True, separators=(',', ':')).encode() + b'\n'
def caller_can_write(info):
    mode = stat.S_IMODE(info.st_mode)
    if info.st_uid == caller_uid: return bool(mode & 0o200)
    if info.st_gid in caller_groups: return bool(mode & 0o020)
    return bool(mode & 0o002)
def nontrivial_acl(fd):
    if sys.platform != 'darwin': return False
    lib=ctypes.CDLL(None,use_errno=True); lib.acl_get_fd_np.argtypes=[ctypes.c_int,ctypes.c_int]; lib.acl_get_fd_np.restype=ctypes.c_void_p
    lib.acl_free.argtypes=[ctypes.c_void_p]; lib.acl_free.restype=ctypes.c_int
    ctypes.set_errno(0); acl=lib.acl_get_fd_np(fd,0x100)
    if not acl:
        if ctypes.get_errno()==errno.ENOENT: return False
        raise SystemExit('ACL inspection failed')
    if lib.acl_free(acl) != 0: raise SystemExit('ACL release failed')
    return True
def verify_ancestor(fd):
    info = os.fstat(fd)
    if info.st_uid != owner or caller_can_write(info) or nontrivial_acl(fd):
        raise SystemExit('unsafe cleanup ancestor authority')
staging = os.open(staging_path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
try:
    journals = sorted(name for name in os.listdir(staging)
                      if name.startswith('ancestor-') and name.endswith('.json'))
    payloads = []
    payload_by_index = {}
    for name in journals:
        suffix = name[len('ancestor-'):-len('.json')]
        if len(suffix) != 4 or not suffix.isdigit() or int(suffix) in payload_by_index:
            raise SystemExit('invalid ancestor journal name')
        info = os.stat(name, dir_fd=staging, follow_symlinks=False)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != owner or info.st_gid != group or \
           stat.S_IMODE(info.st_mode) != 0o400 or info.st_nlink != 1:
            raise SystemExit('invalid ancestor journal metadata')
        fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=staging)
        try: encoded = os.read(fd, 4097)
        finally: os.close(fd)
        try:
            pairs = json.loads(encoded, object_pairs_hook=lambda value: value)
            keys = [key for key, _ in pairs]
            if len(keys) != len(set(keys)): raise ValueError()
            payload = dict(pairs)
        except Exception: raise SystemExit('partial or invalid ancestor journal')
        if len(encoded) > 4096 or canonical(payload) != encoded or \
           set(payload) != {'dev','ino','schema','target','token'} or \
           payload['schema'] != journal_schema or payload['token'] != token:
            raise SystemExit('ancestor journal authority mismatch')
        payloads.append(payload)
        payload_by_index[int(suffix)] = payload
finally: os.close(staging)
parent = os.open(anchor_path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
try:
    verify_ancestor(parent)
    for index, part in enumerate(relative.split('/')):
        provisional = f'{provisional_prefix}{token}-{index:04d}'
        try:
            stale = os.open(provisional, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                            dir_fd=parent)
        except FileNotFoundError: stale = None
        if stale is not None:
            info = os.fstat(stale); entries = os.listdir(stale); os.close(stale)
            payload = payload_by_index.get(index)
            expected_mode = 0o555 if payload is not None else 0o700
            target = '/'.join(relative.split('/')[:index + 1])
            if info.st_uid != owner or info.st_gid != group or entries or \
               stat.S_IMODE(info.st_mode) != expected_mode or \
               (payload is not None and (payload['target'] != target or
                (payload['dev'], payload['ino']) != (info.st_dev, info.st_ino))):
                raise SystemExit('unsafe unjournaled ancestor provisional')
            os.rmdir(provisional, dir_fd=parent); os.fsync(parent)
        try:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                            dir_fd=parent)
        except FileNotFoundError: break
        verify_ancestor(child)
        os.close(parent); parent = child
finally: os.close(parent)
for payload in reversed(payloads):
    parts = payload['target'].split('/')
    if not parts or any(not part or part in ('.', '..') for part in parts):
        raise SystemExit('unsafe ancestor journal target')
    parent = os.open(anchor_path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        verify_ancestor(parent)
        for part in parts[:-1]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                            dir_fd=parent)
            verify_ancestor(child)
            os.close(parent); parent = child
        try:
            target = os.open(parts[-1], os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                             dir_fd=parent)
        except FileNotFoundError: continue
        info = os.fstat(target); os.close(target)
        if info.st_uid != owner or info.st_gid != group or \
           stat.S_IMODE(info.st_mode) != 0o555 or \
           (info.st_dev, info.st_ino) != (payload['dev'], payload['ino']):
            raise SystemExit('ancestor cleanup identity mismatch')
        current = os.stat(parts[-1], dir_fd=parent, follow_symlinks=False)
        if (current.st_dev, current.st_ino) != (info.st_dev, info.st_ino):
            raise SystemExit('ancestor cleanup name changed')
        try: os.rmdir(parts[-1], dir_fd=parent); os.fsync(parent)
        except OSError as error:
            if error.errno not in (errno.ENOTEMPTY, errno.EEXIST): raise
    finally: os.close(parent)
"""


def ensure_installation_parent(
    provenance: InstallerProvenance, staging: Path, token: str
) -> None:
    relative = provenance.install_root.parent.relative_to("/")
    caller_uid, caller_groups = _caller_identity_arguments()
    subprocess.run(
        [
            "/usr/bin/sudo",
            "-n",
            "/usr/bin/python3",
            "-I",
            "-B",
            "-c",
            ROOT_ENSURE_PARENT_CODE,
            "/",
            relative,
            staging,
            token,
            ANCESTOR_JOURNAL_SCHEMA,
            ANCESTOR_PROVISIONAL_PREFIX,
            "0",
            "0",
            caller_uid,
            caller_groups,
        ],
        check=True,
        env={"PATH": "/usr/bin:/bin"},
    )


def cleanup_created_ancestors(
    provenance: InstallerProvenance, staging: Path, token: str
) -> None:
    caller_uid, caller_groups = _caller_identity_arguments()
    subprocess.run(
        [
            "/usr/bin/sudo",
            "-n",
            "/usr/bin/python3",
            "-I",
            "-B",
            "-c",
            ROOT_CLEANUP_ANCESTORS_CODE,
            "/",
            provenance.install_root.parent.relative_to("/"),
            staging,
            token,
            ANCESTOR_JOURNAL_SCHEMA,
            "0",
            "0",
            caller_uid,
            caller_groups,
        ],
        check=True,
        env={"PATH": "/usr/bin:/bin"},
    )


ROOT_INSTALLATION_LOCK_CODE = r"""
import ctypes, errno, fcntl, json, os, stat, subprocess, sys
parent_path, lock_name, token = sys.argv[1:4]
owner = int(sys.argv[4]); caller_uid = int(sys.argv[5])
caller_groups = {int(value) for value in sys.argv[6].split(',') if value}
if len(token) != 32 or any(c not in '0123456789abcdef' for c in token):
    raise SystemExit('invalid lock token')
def caller_can_write(info):
    mode = stat.S_IMODE(info.st_mode)
    if info.st_uid == caller_uid: return bool(mode & 0o200)
    if info.st_gid in caller_groups: return bool(mode & 0o020)
    return bool(mode & 0o002)
def nontrivial_acl(fd):
    if sys.platform != 'darwin': return False
    lib=ctypes.CDLL(None,use_errno=True); lib.acl_get_fd_np.argtypes=[ctypes.c_int,ctypes.c_int]; lib.acl_get_fd_np.restype=ctypes.c_void_p
    lib.acl_free.argtypes=[ctypes.c_void_p]; lib.acl_free.restype=ctypes.c_int
    ctypes.set_errno(0); acl=lib.acl_get_fd_np(fd,0x100)
    if not acl:
        if ctypes.get_errno()==errno.ENOENT: return False
        raise SystemExit('ACL inspection failed')
    if lib.acl_free(acl) != 0: raise SystemExit('ACL release failed')
    return True
def process_start(pid):
    result = subprocess.run(['/bin/ps','-o','lstart=','-p',str(pid)],
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                            text=True, check=False,
                            env={'PATH':'/usr/bin:/bin','LC_ALL':'C'})
    value = result.stdout.strip()
    if result.returncode or not value or len(value) > 64:
        raise SystemExit('could not bind lock owner process start')
    return value
if not parent_path.startswith('/') or os.path.normpath(parent_path) != parent_path:
    raise SystemExit('unsafe lock parent path')
parts = [part for part in parent_path.split('/') if part]
current = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
try:
    root_info = os.fstat(current)
    if root_info.st_uid != owner or caller_can_write(root_info) or \
       nontrivial_acl(current):
        raise SystemExit('unsafe lock root authority')
    for index, part in enumerate(parts):
        child = os.open(
            part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=current
        )
        child_info = os.fstat(child)
        sticky_root = child_info.st_uid == owner and \
            bool(child_info.st_mode & stat.S_ISVTX)
        final = index == len(parts) - 1
        if child_info.st_uid != owner or \
           (caller_can_write(child_info) and (final or not sticky_root)) or \
           nontrivial_acl(child):
            os.close(child)
            raise SystemExit('unsafe lock parent authority')
        os.close(current); current = child
    try:
        lock = os.open(lock_name, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                       0o400, dir_fd=current)
        os.fchown(lock, owner, -1); os.fchmod(lock, 0o400); os.fsync(current)
    except FileExistsError:
        lock = os.open(lock_name, os.O_RDWR | os.O_NOFOLLOW, dir_fd=current)
    info = os.fstat(lock)
    if not stat.S_ISREG(info.st_mode) or info.st_uid != owner or \
       stat.S_IMODE(info.st_mode) != 0o400 or info.st_nlink != 1 or \
       nontrivial_acl(lock):
        raise SystemExit('unsafe installation lock authority')
    try: fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError: raise SystemExit('packaging installation transaction is active')
    payload = json.dumps({'pid':os.getpid(),'schema':'tobkiri.packaging-python-lock.v1',
                          'start':process_start(os.getpid()),'token':token},
                         sort_keys=True,separators=(',',':')).encode()+b'\n'
    os.ftruncate(lock,0); os.lseek(lock,0,os.SEEK_SET)
    offset=0
    while offset < len(payload): offset += os.write(lock,payload[offset:])
    os.fsync(lock); print('READY',flush=True)
    while os.read(0,4096): pass
finally:
    try: os.close(lock)
    except (NameError,OSError): pass
    os.close(current)
"""


@contextlib.contextmanager
def _installation_lock(provenance: InstallerProvenance, token: str) -> Any:
    """Hold the root-owned OS lock for one complete mutation transaction."""
    caller_uid, caller_groups = _caller_identity_arguments()
    holder = subprocess.Popen(
        [
            "/usr/bin/sudo",
            "-n",
            "/usr/bin/python3",
            "-I",
            "-B",
            "-c",
            ROOT_INSTALLATION_LOCK_CODE,
            provenance.install_root.parent,
            INSTALLATION_LOCK_NAME,
            token,
            "0",
            caller_uid,
            caller_groups,
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env={"PATH": "/usr/bin:/bin"},
    )
    readiness = selectors.DefaultSelector()
    if holder.stdout is not None:
        readiness.register(holder.stdout, selectors.EVENT_READ)
    events = readiness.select(timeout=10)
    readiness.close()
    ready = (
        "" if not events or holder.stdout is None else holder.stdout.readline().strip()
    )
    if ready != "READY":
        if holder.poll() is None:
            holder.kill()
        error = "" if holder.stderr is None else holder.stderr.read().strip()
        holder.wait(timeout=5)
        raise ToolIdentityError(
            f"could not acquire installation transaction lock: {error}"
        )
    primary: BaseException | None = None
    traceback = None
    try:
        yield
    except BaseException as error:
        primary = error
        traceback = error.__traceback__
    finally:
        release_error: BaseException | None = None
        if holder.stdin is not None:
            holder.stdin.close()
        try:
            status = holder.wait(timeout=5)
        except subprocess.TimeoutExpired:
            holder.kill()
            holder.wait(timeout=5)
            release_error = ToolIdentityError(
                "installation lock holder did not terminate"
            )
            status = holder.returncode
        if status != 0 and release_error is None:
            error = "" if holder.stderr is None else holder.stderr.read().strip()
            release_error = ToolIdentityError(
                f"installation lock holder failed: {error}"
            )
        if primary is not None:
            if release_error is not None:
                raise ToolIdentityError(
                    f"installation transaction failed: {primary}; "
                    f"lock release failed: {release_error}"
                ) from primary
            raise primary.with_traceback(traceback)
        if release_error is not None:
            raise release_error


ROOT_CREATE_INSTALLATION_CODE = r"""
import ctypes, errno, fcntl, json, os, signal, stat, subprocess, sys, time
parent_path, fixed, token, journal_name, schema, staging_path, displacement_prefix, displacement_schema, displaced_prefix, lock_name = sys.argv[1:11]
owner = int(sys.argv[11]); caller_uid = int(sys.argv[12])
caller_groups = {int(value) for value in sys.argv[13].split(',') if value}
failpoint = sys.argv[14] if len(sys.argv) > 14 else ''
provisional = '.tobkiri-packaging-python-' + token
displaced = displaced_prefix + token
displacement_name = displacement_prefix + token + '.json'
def nontrivial_acl(fd):
    if sys.platform != 'darwin': return False
    lib=ctypes.CDLL(None,use_errno=True); lib.acl_get_fd_np.argtypes=[ctypes.c_int,ctypes.c_int]; lib.acl_get_fd_np.restype=ctypes.c_void_p
    lib.acl_free.argtypes=[ctypes.c_void_p]; lib.acl_free.restype=ctypes.c_int
    ctypes.set_errno(0); acl=lib.acl_get_fd_np(fd,0x100)
    if not acl:
        if ctypes.get_errno()==errno.ENOENT: return False
        raise SystemExit('ACL inspection failed')
    if lib.acl_free(acl) != 0: raise SystemExit('ACL release failed')
    return True
if len(token) != 32 or any(c not in '0123456789abcdef' for c in token):
    raise SystemExit('invalid transaction token')
parent = os.open(parent_path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
staging = os.open(staging_path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
def canonical(payload):
    return json.dumps(payload, sort_keys=True, separators=(',', ':')).encode() + b'\n'
def strict(encoded, fields):
    try:
        pairs=json.loads(encoded,object_pairs_hook=lambda value:value)
        if not isinstance(pairs,list): raise ValueError()
        keys=[key for key,_ in pairs]
        if len(keys)!=len(set(keys)): raise ValueError()
        payload=dict(pairs)
    except Exception: raise SystemExit('invalid lock metadata')
    if len(encoded)>4096 or canonical(payload)!=encoded or set(payload)!=fields:
        raise SystemExit('noncanonical lock metadata')
    return payload
def process_start(pid):
    result=subprocess.run(['/bin/ps','-o','lstart=','-p',str(pid)],
                          stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,
                          check=False,env={'PATH':'/usr/bin:/bin','LC_ALL':'C'})
    return result.stdout.strip() if result.returncode==0 else ''
def caller_can_write(info):
    mode = stat.S_IMODE(info.st_mode)
    if info.st_uid == caller_uid: return bool(mode & 0o200)
    if info.st_gid in caller_groups: return bool(mode & 0o020)
    return bool(mode & 0o002)
def exclusive_rename(source, destination):
    if sys.platform == 'darwin':
        function = ctypes.CDLL(None, use_errno=True).renameatx_np
        function.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int,
                             ctypes.c_char_p, ctypes.c_uint]
        if function(parent, os.fsencode(source), parent, os.fsencode(destination), 4):
            raise OSError(ctypes.get_errno(), 'exclusive rename failed')
    else:
        try: os.stat(destination, dir_fd=parent, follow_symlinks=False)
        except FileNotFoundError: pass
        else: raise FileExistsError(errno.EEXIST, 'exclusive target exists')
        os.rename(source, destination, src_dir_fd=parent, dst_dir_fd=parent)
try:
    parent_info = os.fstat(parent)
    staging_info = os.fstat(staging)
    mode = stat.S_IMODE(parent_info.st_mode)
    if parent_info.st_uid != owner or caller_can_write(parent_info) or nontrivial_acl(parent):
        raise SystemExit('unsafe target parent: path=%s uid=%d gid=%d mode=%#o' %
                         (parent_path, parent_info.st_uid, parent_info.st_gid,
                          stat.S_IMODE(parent_info.st_mode)))
    if staging_info.st_uid != owner or caller_can_write(staging_info) or nontrivial_acl(staging):
        raise SystemExit('unsafe displacement journal authority')
    lock=os.open(lock_name,os.O_RDONLY|os.O_NOFOLLOW,dir_fd=parent)
    lock_info=os.fstat(lock)
    if not stat.S_ISREG(lock_info.st_mode) or lock_info.st_uid!=owner or \
       stat.S_IMODE(lock_info.st_mode)!=0o400 or lock_info.st_nlink!=1 or \
       nontrivial_acl(lock): raise SystemExit('invalid installation lock authority')
    try: fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError: pass
    else:
        fcntl.flock(lock,fcntl.LOCK_UN); raise SystemExit('installation lock is not held')
    os.lseek(lock,0,os.SEEK_SET); lock_bytes=os.read(lock,4097)
    lease=strict(lock_bytes,{'pid','schema','start','token'})
    if lease['schema']!='tobkiri.packaging-python-lock.v1' or lease['token']!=token or \
       not isinstance(lease['pid'],int) or lease['pid']<=0 or \
       process_start(lease['pid'])!=lease['start']:
        raise SystemExit('installation lock owner identity mismatch')
    os.close(lock)
    os.mkdir(provisional, 0o700, dir_fd=parent)
    if failpoint == 'after_mkdir': os.kill(os.getpid(), signal.SIGKILL)
    root = os.open(provisional, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
    info = os.fstat(root)
    if info.st_uid != owner or stat.S_IMODE(info.st_mode) != 0o700 or nontrivial_acl(root):
        raise SystemExit('unsafe provisional directory')
    target = os.path.join(parent_path, fixed)
    payload = canonical({'dev': info.st_dev, 'ino': info.st_ino,
                         'owner_pid':os.getpid(),
                         'owner_start':process_start(os.getpid()),'schema': schema,
                         'target': target, 'token': token})
    fd = os.open(journal_name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                 0o400, dir_fd=root)
    try:
        if failpoint == 'partial_journal':
            os.write(fd, payload[:len(payload) // 2]); os.fsync(fd)
            os.kill(os.getpid(), signal.SIGKILL)
        offset = 0
        while offset < len(payload): offset += os.write(fd, payload[offset:])
        os.fsync(fd)
    finally: os.close(fd)
    os.fsync(root); os.fsync(parent)
    try: previous = os.open(fixed, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                            dir_fd=parent)
    except FileNotFoundError: previous = None
    if previous is not None:
        previous_info = os.fstat(previous)
        previous_entries = os.listdir(previous)
        previous_mode = stat.S_IMODE(previous_info.st_mode)
        previous_acl = nontrivial_acl(previous)
        previous_caller_write = caller_can_write(previous_info)
        if previous_info.st_uid != owner or previous_info.st_uid == caller_uid or \
           previous_info.st_dev != parent_info.st_dev or previous_mode & 0o7002 or \
           previous_mode & 0o500 != 0o500 or previous_acl:
            raise SystemExit(
                'unsafe existing fixed prefix authority: '
                'path=%s uid=%d gid=%d mode=%#o dev=%d parent_dev=%d '
                'caller_write=%d acl=%d' %
                (target, previous_info.st_uid, previous_info.st_gid,
                 previous_mode, previous_info.st_dev, parent_info.st_dev,
                 previous_caller_write, previous_acl))
        if journal_name in previous_entries or \
           '.tobkiri-packaging-python.v1.json' in previous_entries:
            raise SystemExit('existing managed fixed prefix was not released')
        sealed_mode=0o500 if owner==0 else 0o700
        displacement = canonical({'dev': previous_info.st_dev, 'displaced': displaced,
                                  'ino': previous_info.st_ino,'owner_pid':os.getpid(),
                                  'owner_start':process_start(os.getpid()),
                                  'original_mode':previous_mode,
                                  'sealed_mode':sealed_mode,
                                  'schema': displacement_schema, 'target': target,
                                  'staging_dev':staging_info.st_dev,
                                  'staging_ino':staging_info.st_ino,'token': token})
        displacement_fd = os.open(displacement_name, os.O_WRONLY | os.O_CREAT |
                                  os.O_EXCL | os.O_NOFOLLOW, 0o400, dir_fd=parent)
        try:
            os.fchown(displacement_fd, owner, -1); os.fchmod(displacement_fd, 0o400)
            offset = 0
            while offset < len(displacement):
                offset += os.write(displacement_fd, displacement[offset:])
            os.fsync(displacement_fd)
        finally: os.close(displacement_fd)
        os.fsync(parent)
        if failpoint == 'after_displacement_journal': os.kill(os.getpid(), signal.SIGKILL)
        os.fchmod(previous, sealed_mode); os.fsync(previous)
        sealed_info=os.fstat(previous)
        if (sealed_info.st_dev,sealed_info.st_ino)!=(previous_info.st_dev,previous_info.st_ino) or \
           stat.S_IMODE(sealed_info.st_mode)!=sealed_mode or caller_can_write(sealed_info) or \
           nontrivial_acl(previous):
            raise SystemExit('existing fixed prefix seal verification failed')
        if failpoint == 'after_leaf_seal': os.kill(os.getpid(), signal.SIGKILL)
        if failpoint == 'barrier_after_displacement_journal':
            barrier=os.open('.barrier-ready',os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,
                            0o400,dir_fd=staging); os.fsync(barrier); os.close(barrier)
            os.fsync(staging); deadline=time.monotonic()+10
            while True:
                try: os.stat('.barrier-release',dir_fd=staging,follow_symlinks=False); break
                except FileNotFoundError:
                    if time.monotonic()>=deadline: raise SystemExit('barrier timed out')
                    time.sleep(0.01)
            os.unlink('.barrier-ready',dir_fd=staging)
            os.unlink('.barrier-release',dir_fd=staging); os.fsync(staging)
        exclusive_rename(fixed, displaced); os.fsync(parent)
        displaced_info=os.stat(displaced,dir_fd=parent,follow_symlinks=False)
        if (displaced_info.st_dev,displaced_info.st_ino)!=(previous_info.st_dev,previous_info.st_ino):
            raise SystemExit('displaced fixed prefix identity changed')
        os.close(previous)
        if failpoint == 'after_displacement': os.kill(os.getpid(), signal.SIGKILL)
    exclusive_rename(provisional, fixed)
    os.fsync(parent)
    if failpoint == 'after_rename': os.kill(os.getpid(), signal.SIGKILL)
    os.close(root)
finally:
    os.close(staging)
    os.close(parent)
"""


ROOT_RECOVER_INSTALLATIONS_CODE = r"""
import ctypes, errno, fcntl, json, os, stat, subprocess, sys
parent_path, fixed, token_filter, journal_name, schema, staging_path, displacement_prefix, displacement_schema, displaced_prefix, lock_name = sys.argv[1:11]
owner = int(sys.argv[11]); caller_uid = int(sys.argv[12])
caller_groups = {int(value) for value in sys.argv[13].split(',') if value}
prefix = '.tobkiri-packaging-python-'
def nontrivial_acl(fd):
    if sys.platform != 'darwin': return False
    lib=ctypes.CDLL(None,use_errno=True); lib.acl_get_fd_np.argtypes=[ctypes.c_int,ctypes.c_int]; lib.acl_get_fd_np.restype=ctypes.c_void_p
    lib.acl_free.argtypes=[ctypes.c_void_p]; lib.acl_free.restype=ctypes.c_int
    ctypes.set_errno(0); acl=lib.acl_get_fd_np(fd,0x100)
    if not acl:
        if ctypes.get_errno()==errno.ENOENT: return False
        raise SystemExit('ACL inspection failed')
    if lib.acl_free(acl) != 0: raise SystemExit('ACL release failed')
    return True
try: parent = os.open(parent_path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
except FileNotFoundError: raise SystemExit(0)
staging = os.open(staging_path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
def canonical(payload):
    return json.dumps(payload, sort_keys=True, separators=(',', ':')).encode() + b'\n'
def journal(directory, expected_token):
    info = os.stat(journal_name, dir_fd=directory, follow_symlinks=False)
    if not stat.S_ISREG(info.st_mode) or info.st_uid != owner or \
       stat.S_IMODE(info.st_mode) != 0o400 or info.st_nlink != 1:
        raise SystemExit('invalid transaction journal metadata')
    fd = os.open(journal_name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory)
    try: encoded = os.read(fd, 8193)
    finally: os.close(fd)
    if len(encoded) > 8192: raise SystemExit('oversized transaction journal')
    try:
        pairs = json.loads(encoded, object_pairs_hook=lambda value: value)
        if not isinstance(pairs, list): raise ValueError()
        keys = [key for key, _ in pairs]
        if len(keys) != len(set(keys)): raise ValueError()
        payload = dict(pairs)
    except Exception: raise SystemExit('partial or invalid transaction journal')
    if canonical(payload) != encoded or \
       set(payload) != {'dev','ino','owner_pid','owner_start','schema','target','token'}:
        raise SystemExit('noncanonical transaction journal')
    if payload['schema'] != schema or (expected_token and payload['token'] != expected_token):
        raise SystemExit('transaction journal authority mismatch')
    if not isinstance(payload['owner_pid'],int) or payload['owner_pid']<=0 or \
       not isinstance(payload['owner_start'],str) or len(payload['owner_start'])>64:
        raise SystemExit('transaction owner identity is invalid')
    return payload
def process_start(pid):
    result=subprocess.run(['/bin/ps','-o','lstart=','-p',str(pid)],
                          stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True,
                          check=False,env={'PATH':'/usr/bin:/bin','LC_ALL':'C'})
    return result.stdout.strip() if result.returncode==0 else ''
def displacement_journal(name):
    info = os.stat(name, dir_fd=parent, follow_symlinks=False)
    if not stat.S_ISREG(info.st_mode) or info.st_uid != owner or \
       stat.S_IMODE(info.st_mode) != 0o400 or info.st_nlink != 1:
        raise SystemExit('invalid displacement journal metadata')
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=parent)
    try: encoded = os.read(fd, 8193)
    finally: os.close(fd)
    if len(encoded) > 8192: raise SystemExit('oversized displacement journal')
    try:
        pairs = json.loads(encoded, object_pairs_hook=lambda value: value)
        if not isinstance(pairs, list): raise ValueError()
        keys = [key for key, _ in pairs]
        if len(keys) != len(set(keys)): raise ValueError()
        payload = dict(pairs)
    except Exception: raise SystemExit('partial or invalid displacement journal')
    if canonical(payload) != encoded or \
       set(payload) != {'dev','displaced','ino','original_mode','owner_pid','owner_start','schema','sealed_mode','staging_dev','staging_ino','target','token'} or \
       payload['schema'] != displacement_schema or \
       payload['target'] != os.path.join(parent_path, fixed) or \
       payload['displaced'] != displaced_prefix + payload['token'] or \
       name != displacement_prefix + payload['token'] + '.json' or \
       not isinstance(payload['original_mode'],int) or \
       payload['original_mode']<0 or payload['original_mode']>0o777 or \
       payload['sealed_mode']!=(0o500 if owner==0 else 0o700) or \
       not isinstance(payload['owner_pid'],int) or payload['owner_pid']<=0 or \
       not isinstance(payload['owner_start'],str) or len(payload['owner_start'])>64:
        raise SystemExit('displacement journal authority mismatch')
    return payload
def exclusive_rename(source, destination):
    if sys.platform == 'darwin':
        function = ctypes.CDLL(None, use_errno=True).renameatx_np
        function.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int,
                             ctypes.c_char_p, ctypes.c_uint]
        if function(parent, os.fsencode(source), parent, os.fsencode(destination), 4):
            raise OSError(ctypes.get_errno(), 'exclusive restore failed')
    else:
        try: os.stat(destination, dir_fd=parent, follow_symlinks=False)
        except FileNotFoundError: pass
        else: raise FileExistsError(errno.EEXIST, 'restore target exists')
        os.rename(source, destination, src_dir_fd=parent, dst_dir_fd=parent)
def empty(directory):
    os.fchmod(directory, 0o700)
    for name in os.listdir(directory):
        info = os.stat(name, dir_fd=directory, follow_symlinks=False)
        if stat.S_ISDIR(info.st_mode):
            child = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                            dir_fd=directory)
            empty(child); os.close(child); os.rmdir(name, dir_fd=directory)
        else: os.unlink(name, dir_fd=directory)
def remove_named(name, expected, exact_mode=None):
    directory = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
    info = os.fstat(directory)
    if info.st_uid != owner or nontrivial_acl(directory) or \
       (exact_mode is not None and stat.S_IMODE(info.st_mode) != exact_mode):
        raise SystemExit('stale transaction metadata mismatch')
    if expected is not None and (info.st_dev, info.st_ino) != expected:
        raise SystemExit('stale transaction identity mismatch')
    empty(directory); os.close(directory)
    current = os.stat(name, dir_fd=parent, follow_symlinks=False)
    if (current.st_dev, current.st_ino) != (info.st_dev, info.st_ino):
        raise SystemExit('stale transaction name changed')
    os.rmdir(name, dir_fd=parent); os.fsync(parent)
try:
    parent_info = os.fstat(parent)
    mode = stat.S_IMODE(parent_info.st_mode)
    caller_writable = (mode & 0o200 if parent_info.st_uid == caller_uid else
                       mode & 0o020 if parent_info.st_gid in caller_groups else mode & 0o002)
    if parent_info.st_uid != owner or caller_writable or nontrivial_acl(parent):
        raise SystemExit('unsafe transaction parent: path=%s uid=%d gid=%d mode=%#o' %
                         (parent_path, parent_info.st_uid, parent_info.st_gid,
                          stat.S_IMODE(parent_info.st_mode)))
    staging_info = os.fstat(staging)
    staging_mode = stat.S_IMODE(staging_info.st_mode)
    staging_writable = (staging_mode & 0o200 if staging_info.st_uid == caller_uid else
                        staging_mode & 0o020
                        if staging_info.st_gid in caller_groups else
                        staging_mode & 0o002)
    if staging_info.st_uid != owner or staging_writable or nontrivial_acl(staging):
        raise SystemExit('unsafe displacement recovery authority')
    lock=os.open(lock_name,os.O_RDONLY|os.O_NOFOLLOW,dir_fd=parent)
    lock_info=os.fstat(lock)
    if not stat.S_ISREG(lock_info.st_mode) or lock_info.st_uid!=owner or \
       stat.S_IMODE(lock_info.st_mode)!=0o400 or lock_info.st_nlink!=1 or \
       nontrivial_acl(lock): raise SystemExit('invalid installation lock authority')
    try: fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError: pass
    else:
        fcntl.flock(lock,fcntl.LOCK_UN); raise SystemExit('installation lock is not held')
    os.close(lock)
    displacement_names=[]
    for name in sorted(os.listdir(parent)):
        if not name.startswith(displacement_prefix): continue
        suffix=name[len(displacement_prefix):]
        if not suffix.endswith('.json') or len(suffix)!=37 or \
           any(c not in '0123456789abcdef' for c in suffix[:-5]):
            raise SystemExit('unknown displacement journal entry')
        displacement_names.append(name)
    if len(displacement_names)>1:
        raise SystemExit('multiple displacement journals are ambiguous')
    displacement = None if not displacement_names else \
        displacement_journal(displacement_names[0])
    if displacement is not None:
        staging_basename=os.path.basename(staging_path)
        if not staging_basename.endswith(token_filter):
            raise SystemExit('current staging name does not bind its token')
        staging_prefix=staging_basename[:-len(token_filter)]
        staging_parent=os.open(os.path.dirname(staging_path),os.O_RDONLY|
                               os.O_DIRECTORY|os.O_NOFOLLOW)
        try:
            recorded=os.open(staging_prefix+displacement['token'],os.O_RDONLY|
                             os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=staging_parent)
            recorded_info=os.fstat(recorded)
            if recorded_info.st_uid!=owner or nontrivial_acl(recorded) or \
               (recorded_info.st_dev,recorded_info.st_ino)!= \
               (displacement['staging_dev'],displacement['staging_ino']):
                raise SystemExit('recorded staging authority changed')
            os.close(recorded)
        finally: os.close(staging_parent)
    if displacement is not None and \
       process_start(displacement['owner_pid'])==displacement['owner_start']:
        raise SystemExit('displacement owner process is still live')
    for name in sorted(os.listdir(parent)):
        if not name.startswith(prefix): continue
        token = name[len(prefix):]
        if len(token) != 32 or any(c not in '0123456789abcdef' for c in token):
            raise SystemExit('invalid stale provisional name')
        directory = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
        info = os.fstat(directory)
        entries = os.listdir(directory)
        if journal_name not in entries:
            os.close(directory)
            if entries: raise SystemExit('unjournaled nonempty provisional transaction')
            remove_named(name, (info.st_dev, info.st_ino), 0o700); continue
        payload = journal(directory, token); os.close(directory)
        if process_start(payload['owner_pid'])==payload['owner_start']:
            raise SystemExit('provisional owner process is still live')
        if payload['target'] != os.path.join(parent_path, fixed) or \
           (payload['dev'], payload['ino']) != (info.st_dev, info.st_ino):
            raise SystemExit('provisional transaction journal mismatch')
        remove_named(name, (payload['dev'], payload['ino']), 0o700)
    try: fixed_dir = os.open(fixed, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
    except FileNotFoundError: fixed_dir = None
    if fixed_dir is not None:
        entries = os.listdir(fixed_dir)
        if '.tobkiri-packaging-python.v1.json' not in entries:
            if journal_name not in entries:
                info = os.fstat(fixed_dir)
                expected = None if displacement is None else \
                    (displacement['dev'], displacement['ino'])
                if expected != (info.st_dev, info.st_ino):
                    if displacement is None and token_filter:
                        os.close(fixed_dir); fixed_dir = None
                    else:
                        raise SystemExit('fixed prefix lacks a transaction journal')
                else:
                    os.close(fixed_dir); fixed_dir = None
            if fixed_dir is None: pass
            else:
                payload = journal(fixed_dir, '')
                info = os.fstat(fixed_dir); os.close(fixed_dir)
                if process_start(payload['owner_pid'])==payload['owner_start']:
                    raise SystemExit('fixed transaction owner process is still live')
                if payload['target'] != os.path.join(parent_path, fixed) or \
                   (payload['dev'], payload['ino']) != (info.st_dev, info.st_ino):
                    raise SystemExit('fixed transaction journal mismatch')
                remove_named(fixed, (payload['dev'], payload['ino']))
        else: os.close(fixed_dir)
    if displacement is not None:
        displaced_name = displacement['displaced']
        try: displaced = os.open(displaced_name, os.O_RDONLY | os.O_DIRECTORY |
                                 os.O_NOFOLLOW, dir_fd=parent)
        except FileNotFoundError: displaced = None
        try: current = os.open(fixed, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                               dir_fd=parent)
        except FileNotFoundError: current = None
        expected = (displacement['dev'], displacement['ino'])
        if displaced is None:
            current_info = None if current is None else os.fstat(current)
            if current_info is None or (current_info.st_dev, current_info.st_ino) != expected:
                raise SystemExit('displaced fixed prefix identity is lost')
            current_mode=stat.S_IMODE(current_info.st_mode)
            if current_mode not in (displacement['sealed_mode'],
                                    displacement['original_mode']):
                raise SystemExit('fixed prefix sealed mode changed')
            os.fchmod(current,displacement['original_mode']); os.fsync(current)
        else:
            displaced_info = os.fstat(displaced)
            if displaced_info.st_uid != owner or nontrivial_acl(displaced) or \
               stat.S_IMODE(displaced_info.st_mode)!=displacement['sealed_mode'] or \
               (displaced_info.st_dev, displaced_info.st_ino) != expected:
                raise SystemExit('displaced fixed prefix authority changed')
            if current is not None:
                raise SystemExit('fixed prefix blocks displaced restoration')
            os.close(displaced); displaced = None
            exclusive_rename(displaced_name, fixed); os.fsync(parent)
            restored=os.open(fixed,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,
                             dir_fd=parent)
            restored_info=os.fstat(restored)
            if (restored_info.st_dev,restored_info.st_ino)!=expected:
                raise SystemExit('restored fixed prefix identity changed')
            os.fchmod(restored,displacement['original_mode']); os.fsync(restored)
            os.close(restored)
        if current is not None: os.close(current)
        if displaced is not None: os.close(displaced)
        journal_entry=displacement_prefix+displacement['token']+'.json'
        os.unlink(journal_entry, dir_fd=parent); os.fsync(parent)
    displaced_entries=[name for name in os.listdir(parent)
                       if name.startswith(displaced_prefix)]
    if displaced_entries:
        raise SystemExit('displaced prefix lacks a unique authority journal')
finally:
    os.close(staging)
    os.close(parent)
"""


def _create_installation_root(
    provenance: InstallerProvenance, staging: Path, token: str
) -> None:
    parent = provenance.install_root.parent
    caller_uid, caller_groups = _caller_identity_arguments()
    subprocess.run(
        [
            "/usr/bin/sudo",
            "/usr/bin/python3",
            "-I",
            "-B",
            "-c",
            ROOT_CREATE_INSTALLATION_CODE,
            parent,
            provenance.install_root.name,
            token,
            INSTALLATION_JOURNAL_NAME,
            INSTALLATION_JOURNAL_SCHEMA,
            staging,
            DISPLACEMENT_JOURNAL_PREFIX,
            DISPLACEMENT_JOURNAL_SCHEMA,
            DISPLACED_PREFIX,
            INSTALLATION_LOCK_NAME,
            "0",
            caller_uid,
            caller_groups,
        ],
        check=True,
        env={"PATH": "/usr/bin:/bin"},
    )


def recover_stale_installations(
    provenance: InstallerProvenance, staging: Path, token: str
) -> None:
    caller_uid, caller_groups = _caller_identity_arguments()
    subprocess.run(
        [
            "/usr/bin/sudo",
            "/usr/bin/python3",
            "-I",
            "-B",
            "-c",
            ROOT_RECOVER_INSTALLATIONS_CODE,
            provenance.install_root.parent,
            provenance.install_root.name,
            token,
            INSTALLATION_JOURNAL_NAME,
            INSTALLATION_JOURNAL_SCHEMA,
            staging,
            DISPLACEMENT_JOURNAL_PREFIX,
            DISPLACEMENT_JOURNAL_SCHEMA,
            DISPLACED_PREFIX,
            INSTALLATION_LOCK_NAME,
            "0",
            caller_uid,
            caller_groups,
        ],
        check=True,
        env={"PATH": "/usr/bin:/bin"},
    )


def cleanup_transaction(token: str) -> None:
    """Recover only recorded inodes while holding the installation OS lock."""
    staging = _transaction_path(token)
    try:
        _root_owned_path(staging, "packaging transaction", sticky=STAGING_PARENT)
    except FileNotFoundError:
        return
    provenance_path = staging / SEALED_PROVENANCE_NAME
    requirements_path = staging / SEALED_REQUIREMENTS_NAME
    if not provenance_path.exists() or not requirements_path.exists():
        _remove_root_tree(staging)
        return
    provenance_bytes = provenance_path.read_bytes()
    requirements_bytes = requirements_path.read_bytes()
    provenance = _parse_provenance(
        provenance_bytes, requirements_bytes, "sealed trusted Git provenance"
    )
    with _installation_lock(provenance, token):
        recover_stale_installations(provenance, staging, token)
        cleanup_created_ancestors(provenance, staging, token)
        _remove_root_tree(staging)


def _transaction_is_absent(token: str) -> bool:
    """Return true only when the exact transaction name has no directory entry."""
    try:
        _transaction_path(token).lstat()
    except FileNotFoundError:
        return True
    return False


def _remove_verified_installation(
    root: Path, provenance: InstallerProvenance, inventory_sha256: str
) -> None:
    """Remove a completed installation only after re-establishing its authority."""
    if root != provenance.install_root or not _valid_sha256(inventory_sha256):
        raise ToolIdentityError("refusing to remove an unbound Python installation")
    installation = MacOSPythonInstallation(
        root, root / provenance.executable, inventory_sha256
    )
    verify_macos_installation(installation, provenance)
    identity, _token = _installation_receipt(root, provenance)
    _remove_root_tree(root, identity)


def _installation_receipt(
    root: Path, provenance: InstallerProvenance
) -> tuple[tuple[int, int], str]:
    """Bind the leaf inode to its canonical root-owned transaction receipt."""
    root_metadata = root.lstat()
    journal = root / INSTALLATION_JOURNAL_NAME
    metadata = journal.lstat()
    payload = _strict_json(journal)
    encoded = journal.read_bytes()
    token = payload.get("token")
    if (
        not stat.S_ISDIR(root_metadata.st_mode)
        or root_metadata.st_uid != 0
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != 0
        or stat.S_IMODE(metadata.st_mode) != 0o400
        or metadata.st_nlink != 1
        or _canonical_json(payload) != encoded
        or set(payload)
        != {"dev", "ino", "owner_pid", "owner_start", "schema", "target", "token"}
        or payload.get("schema") != INSTALLATION_JOURNAL_SCHEMA
        or payload.get("target") != os.fspath(provenance.install_root)
        or (payload.get("dev"), payload.get("ino"))
        != (root_metadata.st_dev, root_metadata.st_ino)
        or not isinstance(payload.get("owner_pid"), int)
        or payload["owner_pid"] <= 0
        or not isinstance(payload.get("owner_start"), str)
        or len(payload["owner_start"]) > 64
        or not isinstance(token, str)
        or len(token) != 32
        or any(character not in "0123456789abcdef" for character in token)
    ):
        raise ToolIdentityError("existing Python installation receipt is invalid")
    return (root_metadata.st_dev, root_metadata.st_ino), token


def _remove_previous_installation(provenance: InstallerProvenance) -> None:
    """Permit reruns only when the existing fixed root is a verified prior result."""
    try:
        root_metadata = provenance.install_root.lstat()
    except FileNotFoundError:
        return
    if not stat.S_ISDIR(root_metadata.st_mode):
        raise ToolIdentityError("fixed Python installation path has unknown authority")
    inventory = provenance.install_root / INVENTORY_NAME
    try:
        inventory_sha256 = _sha256_file(inventory)
    except FileNotFoundError:
        # The root helper will quarantine this untrusted host leaf by inode.  It
        # is never read, executed, adopted, or deleted by the formal closure.
        return
    except OSError as error:
        raise ToolIdentityError(
            "existing fixed Python inventory is unreadable"
        ) from error
    installation = MacOSPythonInstallation(
        provenance.install_root,
        provenance.install_root / provenance.executable,
        inventory_sha256,
    )
    verify_macos_installation(installation, provenance)
    identity, token = _installation_receipt(provenance.install_root, provenance)
    active_staging = _transaction_path(token)
    try:
        _root_owned_path(
            active_staging, "active packaging transaction", sticky=STAGING_PARENT
        )
    except FileNotFoundError:
        pass
    else:
        raise ToolIdentityError("existing Python installation has an active lease")
    _remove_root_tree(provenance.install_root, identity)


def _verify_installer(path: Path, provenance: InstallerProvenance) -> None:
    if _sha256_file(path) != provenance.installer_sha256:
        raise ToolIdentityError("python.org installer digest mismatch")
    signature = subprocess.run(
        ["/usr/sbin/pkgutil", "--check-signature", path],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
    )
    if signature.returncode != 0 or provenance.installer_signer not in signature.stdout:
        raise ToolIdentityError("python.org installer signer mismatch")
    notarization = subprocess.run(
        ["/usr/sbin/spctl", "-a", "-vv", "-t", "install", path],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
    )
    if (
        notarization.returncode != 0
        or "source=Notarized Developer ID" not in notarization.stdout
        or provenance.installer_signer not in notarization.stdout
    ):
        raise ToolIdentityError(
            "python.org installer is not notarized by the pinned signer"
        )


def _inventory_entries(root: Path) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    symlinks: dict[str, str] = {}
    root_device = root.lstat().st_dev
    for path in sorted(root.rglob("*"), key=lambda item: item.as_posix()):
        relative = path.relative_to(root).as_posix()
        if relative == INVENTORY_NAME:
            continue
        metadata = path.lstat()
        if metadata.st_dev != root_device:
            raise ToolIdentityError(
                f"mount boundary in Python installation: {relative}"
            )
        if stat.S_ISREG(metadata.st_mode) or stat.S_ISDIR(metadata.st_mode):
            flags = os.O_RDONLY | os.O_NOFOLLOW
            if stat.S_ISDIR(metadata.st_mode):
                flags |= os.O_DIRECTORY
            descriptor = os.open(path, flags)
            try:
                opened = os.fstat(descriptor)
                if (opened.st_dev, opened.st_ino) != (
                    metadata.st_dev,
                    metadata.st_ino,
                ) or _fd_has_nontrivial_acl(descriptor):
                    raise ToolIdentityError(
                        f"Python entry identity changed or has ACL: {relative}"
                    )
            finally:
                os.close(descriptor)
        entry: dict[str, Any] = {
            "gid": metadata.st_gid,
            "mode": stat.S_IMODE(metadata.st_mode),
            "nlink": metadata.st_nlink,
            "path": relative,
            "uid": metadata.st_uid,
        }
        if stat.S_ISREG(metadata.st_mode):
            entry.update(type="file", size=metadata.st_size, sha256=_sha256_file(path))
        elif stat.S_ISDIR(metadata.st_mode):
            entry["type"] = "directory"
        elif stat.S_ISLNK(metadata.st_mode):
            if metadata.st_nlink != 1:
                raise ToolIdentityError(f"hardlinked Python symlink: {relative}")
            # The fully sealed parent directories deny caller rename authority,
            # so lstat/readlink/lstat binds the link without opening its target.
            target = os.readlink(path)
            after = path.lstat()
            if _file_identity(metadata) != _file_identity(after):
                raise ToolIdentityError(f"Python symlink changed: {relative}")
            if not target or "\x00" in target or target.startswith("/"):
                raise ToolIdentityError(
                    f"Python symlink is absolute or empty: {relative}"
                )
            normalized = posixpath.normpath(
                posixpath.join(posixpath.dirname(relative), target)
            )
            if normalized in {"", ".", ".."} or normalized.startswith("../"):
                raise ToolIdentityError(
                    f"Python symlink escapes installation: {relative}"
                )
            symlinks[relative] = normalized
            entry.update(type="symlink", target=target)
        else:
            raise ToolIdentityError(f"special file in Python installation: {relative}")
        entries.append(entry)
    for origin, target in symlinks.items():
        value = target
        seen = {origin}
        for _ in range(129):
            parts = value.split("/")
            match = next(
                (
                    ("/".join(parts[:index]), index)
                    for index in range(1, len(parts) + 1)
                    if "/".join(parts[:index]) in symlinks
                ),
                None,
            )
            if match is None:
                break
            candidate, index = match
            if candidate in seen:
                raise ToolIdentityError(f"Python symlink cycle: {origin}")
            seen.add(candidate)
            suffix = "/".join(parts[index:])
            value = posixpath.normpath(posixpath.join(symlinks[candidate], suffix))
            if value == ".." or value.startswith("../") or value.startswith("/"):
                raise ToolIdentityError(f"Python symlink chain escapes: {origin}")
        else:
            raise ToolIdentityError(f"Python symlink chain is too deep: {origin}")
    return entries


def _canonical_json(payload: Any) -> bytes:
    return (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode()


def _write_inventory(
    installation: MacOSPythonInstallation,
    provenance: InstallerProvenance,
    code_identity: CodeIdentity,
) -> str:
    payload = {
        "code_identity": {
            "cdhash": code_identity.cdhash,
            "identifier": code_identity.identifier,
            "team_identifier": code_identity.team_identifier,
        },
        "entries": _inventory_entries(installation.root),
        "executable": installation.executable.relative_to(installation.root).as_posix(),
        "installer_sha256": provenance.installer_sha256,
        "installer_signer": provenance.installer_signer,
        "installer_team_id": provenance.installer_team_id,
        "installer_url": provenance.installer_url,
        "requirements_sha256": provenance.requirements_sha256,
        "schema": INVENTORY_SCHEMA,
        "version": provenance.version,
    }
    encoded = _canonical_json(payload)
    with tempfile.NamedTemporaryFile(delete=False) as output:
        temporary = Path(output.name)
        output.write(encoded)
        output.flush()
        os.fsync(output.fileno())
    try:
        subprocess.run(
            [
                "/usr/bin/sudo",
                "/usr/bin/install",
                "-o",
                "root",
                "-g",
                "wheel",
                "-m",
                "0444",
                temporary,
                installation.root / INVENTORY_NAME,
            ],
            check=True,
        )
    finally:
        temporary.unlink(missing_ok=True)
    return hashlib.sha256(encoded).hexdigest()


def _require_inventory_metadata(manifest: Path) -> None:
    metadata = manifest.lstat()
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != 0
        or stat.S_IMODE(metadata.st_mode) != 0o444
        or metadata.st_nlink != 1
    ):
        raise ToolIdentityError("packaging Python inventory metadata mismatch")
    descriptor = os.open(manifest, os.O_RDONLY | os.O_NOFOLLOW)
    try:
        opened = os.fstat(descriptor)
        if (opened.st_dev, opened.st_ino) != (
            metadata.st_dev,
            metadata.st_ino,
        ) or _fd_has_nontrivial_acl(descriptor):
            raise ToolIdentityError("packaging Python inventory has ACL or changed")
    finally:
        os.close(descriptor)


def verify_macos_installation(
    installation: MacOSPythonInstallation, provenance: InstallerProvenance
) -> ToolIdentity:
    """Verify exact sealed bytes without executing the installed Python."""
    _root_owned_path(installation.root, "packaging Python installation")
    manifest = installation.root / INVENTORY_NAME
    _require_inventory_metadata(manifest)
    encoded = manifest.read_bytes()
    payload = _strict_json(manifest)
    if _canonical_json(payload) != encoded or payload.get("schema") != INVENTORY_SCHEMA:
        raise ToolIdentityError("packaging Python inventory is not canonical v1")
    if hashlib.sha256(encoded).hexdigest() != installation.inventory_sha256:
        raise ToolIdentityError("packaging Python inventory digest mismatch")
    if payload.get("entries") != _inventory_entries(installation.root):
        raise ToolIdentityError(
            "packaging Python inventory does not match exact installation"
        )
    for entry in payload["entries"]:
        if entry.get("uid") != 0:
            raise ToolIdentityError("packaging Python contains non-root-owned content")
        if entry.get("type") in {"file", "directory"} and entry.get("mode", 0) & 0o022:
            raise ToolIdentityError("packaging Python contains writable content")
    expected = {
        "installer_sha256": provenance.installer_sha256,
        "installer_signer": provenance.installer_signer,
        "installer_team_id": provenance.installer_team_id,
        "installer_url": provenance.installer_url,
        "requirements_sha256": provenance.requirements_sha256,
        "version": provenance.version,
    }
    if any(payload.get(key) != value for key, value in expected.items()):
        raise ToolIdentityError("packaging Python provenance binding mismatch")
    relative = _safe_relative(payload.get("executable"), "inventory executable")
    if installation.executable != installation.root / relative:
        raise ToolIdentityError("packaging Python executable binding mismatch")
    identity = _require_code_authority(
        installation.executable,
        identifier=provenance.code_identifier,
        team_identifier=provenance.installer_team_id,
        label="Python",
    )
    if payload.get("code_identity") != {
        "cdhash": identity.cdhash,
        "identifier": identity.identifier,
        "team_identifier": identity.team_identifier,
    }:
        raise ToolIdentityError("packaging Python code identity changed")
    return _regular_executable(installation.executable, "Python")


def _inside(path: Path, root: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(root.resolve(strict=True))
    except (OSError, RuntimeError, ValueError):
        return False
    return True


_MACHO_MAGICS = frozenset(
    {
        b"\xca\xfe\xba\xbe",
        b"\xca\xfe\xba\xbf",
        b"\xbe\xba\xfe\xca",
        b"\xbf\xba\xfe\xca",
        b"\xce\xfa\xed\xfe",
        b"\xcf\xfa\xed\xfe",
        b"\xfe\xed\xfa\xce",
        b"\xfe\xed\xfa\xcf",
    }
)


@dataclass(frozen=True)
class _MachOSliceCommands:
    identifier: str | None
    dependencies: tuple[str, ...]
    rpaths: tuple[str, ...]


_DYLIB_LOAD_COMMANDS = frozenset(
    {
        "LC_LAZY_LOAD_DYLIB",
        "LC_LOAD_DYLIB",
        "LC_LOAD_UPWARD_DYLIB",
        "LC_LOAD_WEAK_DYLIB",
        "LC_REEXPORT_DYLIB",
    }
)


def _macho_load_commands(path: Path, architecture: str) -> str:
    result = subprocess.run(
        ["/usr/bin/otool", "-arch", architecture, "-l", path],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
        env={"PATH": "/usr/bin:/bin"},
    )
    if result.returncode != 0:
        raise ToolIdentityError(
            f"otool -l rejected packaging Mach-O {path} ({architecture})"
        )
    return result.stdout


def _macho_architectures(path: Path) -> tuple[str, ...]:
    result = subprocess.run(
        ["/usr/bin/lipo", "-archs", path],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
        env={"PATH": "/usr/bin:/bin"},
    )
    architectures = tuple(result.stdout.split())
    if (
        result.returncode != 0
        or not architectures
        or len(architectures) != len(set(architectures))
        or any(not value.replace("_", "").isalnum() for value in architectures)
    ):
        raise ToolIdentityError(f"could not enumerate Mach-O architectures: {path}")
    return architectures


def _load_command_value(block: tuple[str, ...], field: str) -> str:
    prefix = f"{field} "
    values = [
        line.strip()[len(prefix) :].split(" (offset ", 1)[0]
        for line in block
        if line.strip().startswith(prefix) and " (offset " in line.strip()
    ]
    if len(values) != 1 or not values[0] or "\x00" in values[0]:
        raise ToolIdentityError(f"Mach-O load command has invalid {field}")
    return values[0]


def _parse_macho_load_commands(output: str) -> _MachOSliceCommands:
    """Parse one architecture's ordered otool load-command records."""
    lines = output.splitlines()
    starts = [
        index for index, line in enumerate(lines) if line.startswith("Load command ")
    ]
    if not starts:
        raise ToolIdentityError("Mach-O has no structured load commands")
    dependencies: list[str] = []
    rpaths: list[str] = []
    identifiers: list[str] = []
    for ordinal, start in enumerate(starts):
        if lines[start] != f"Load command {ordinal}":
            raise ToolIdentityError("Mach-O load command numbering is not canonical")
        end = starts[ordinal + 1] if ordinal + 1 < len(starts) else len(lines)
        block = tuple(lines[start + 1 : end])
        commands = [
            line.strip().removeprefix("cmd ")
            for line in block
            if line.strip().startswith("cmd ")
        ]
        if len(commands) != 1:
            raise ToolIdentityError("Mach-O load command lacks one command type")
        command = commands[0]
        if command == "LC_RPATH":
            rpaths.append(_load_command_value(block, "path"))
        elif command == "LC_ID_DYLIB":
            identifiers.append(_load_command_value(block, "name"))
        elif command in _DYLIB_LOAD_COMMANDS:
            dependencies.append(_load_command_value(block, "name"))
        elif "DYLIB" in command and command.startswith("LC_"):
            raise ToolIdentityError(f"unsupported Mach-O dylib command: {command}")
    if len(identifiers) > 1:
        raise ToolIdentityError("Mach-O has multiple LC_ID_DYLIB commands")
    if len(dependencies) != len(set(dependencies)):
        raise ToolIdentityError("Mach-O dependency commands are duplicated")
    if len(rpaths) != len(set(rpaths)):
        raise ToolIdentityError("Mach-O LC_RPATH entries are duplicated")
    return _MachOSliceCommands(
        identifiers[0] if identifiers else None,
        tuple(dependencies),
        tuple(rpaths),
    )


def _system_dyld_path(path: Path) -> bool:
    value = path.as_posix()
    return value.startswith(("/usr/lib/", "/System/Library/"))


def _expand_dyld_path(value: str, image: Path, executable: Path) -> Path:
    if "\x00" in value:
        raise ToolIdentityError("Mach-O path contains NUL")
    if value.startswith("@loader_path/"):
        expanded = image.parent / value.removeprefix("@loader_path/")
    elif value.startswith("@executable_path/"):
        expanded = executable.parent / value.removeprefix("@executable_path/")
    elif value.startswith("/"):
        expanded = Path(value)
    else:
        raise ToolIdentityError(f"relative or unsupported Mach-O path: {value}")
    normalized = Path(os.path.normpath(expanded))
    if not normalized.is_absolute():
        raise ToolIdentityError(f"Mach-O path is not absolute after expansion: {value}")
    return normalized


def _require_dyld_candidate(candidate: Path, root: Path, dependency: str) -> Path:
    if _system_dyld_path(candidate):
        return candidate
    try:
        resolved = candidate.resolve(strict=True)
    except (OSError, RuntimeError) as error:
        raise ToolIdentityError(
            f"unresolved Mach-O dependency: {dependency} -> {candidate}"
        ) from error
    if not _inside(resolved, root):
        raise ToolIdentityError(
            f"packaging Python Mach-O dependency escapes closure: {dependency}"
        )
    return resolved


def _resolve_macho_dependency(
    dependency: str,
    run_path_stack: tuple[Path, ...],
    image: Path,
    executable: Path,
    root: Path,
) -> Path:
    if dependency.startswith("@rpath/"):
        if not run_path_stack:
            raise ToolIdentityError(f"@rpath dependency has no LC_RPATH: {dependency}")
        suffix = dependency.removeprefix("@rpath/")
        if not suffix or suffix.startswith("/"):
            raise ToolIdentityError(f"unsafe @rpath dependency: {dependency}")
        candidates: list[Path] = []
        for run_path in run_path_stack:
            candidate = run_path / suffix
            if candidate.exists():
                candidates.append(_require_dyld_candidate(candidate, root, dependency))
        unique = tuple(dict.fromkeys(candidates))
        if len(unique) != 1:
            raise ToolIdentityError(
                f"unresolved or ambiguous @rpath dependency: {dependency}"
            )
        return unique[0]
    expanded = _expand_dyld_path(dependency, image, executable)
    return _require_dyld_candidate(expanded, root, dependency)


def _extend_run_path_stack(
    inherited: tuple[Path, ...],
    commands: _MachOSliceCommands,
    image: Path,
    executable: Path,
    root: Path,
) -> tuple[Path, ...]:
    expanded: list[Path] = []
    for raw_rpath in commands.rpaths:
        candidate = _expand_dyld_path(raw_rpath, image, executable)
        if not (_system_dyld_path(candidate) or _inside(candidate, root)):
            raise ToolIdentityError(f"external LC_RPATH: {raw_rpath}")
        expanded.append(candidate)
    return (*inherited, *expanded)


def _verify_macho_dependency_closure(installation: MacOSPythonInstallation) -> None:
    """Resolve every architecture's dependencies with exact dyld semantics."""
    base_python = installation.root / "bin" / f"python{installation.root.name}"
    executables = (base_python, installation.executable)
    macho_paths: list[Path] = []
    for path in sorted(installation.root.rglob("*")):
        metadata = path.lstat()
        if not stat.S_ISREG(metadata.st_mode):
            continue
        with path.open("rb") as source:
            if source.read(4) not in _MACHO_MAGICS:
                continue
        macho_paths.append(path)
    architecture_cache: dict[Path, tuple[str, ...]] = {}
    command_cache: dict[tuple[Path, str], _MachOSliceCommands] = {}

    def architectures(path: Path) -> tuple[str, ...]:
        if path not in architecture_cache:
            architecture_cache[path] = _macho_architectures(path)
        return architecture_cache[path]

    def commands(path: Path, architecture: str) -> _MachOSliceCommands:
        key = (path, architecture)
        if key not in command_cache:
            if architecture not in architectures(path):
                raise ToolIdentityError(
                    f"Mach-O dependency lacks {architecture} slice: {path}"
                )
            command_cache[key] = _parse_macho_load_commands(
                _macho_load_commands(path, architecture)
            )
        return command_cache[key]

    def verify_image(
        path: Path,
        architecture: str,
        executable: Path,
        inherited: tuple[Path, ...],
        active: frozenset[Path],
    ) -> None:
        if path in active:
            return
        image_commands = commands(path, architecture)
        run_paths = _extend_run_path_stack(
            inherited, image_commands, path, executable, installation.root
        )
        for dependency in image_commands.dependencies:
            resolved = _resolve_macho_dependency(
                dependency, run_paths, path, executable, installation.root
            )
            if _system_dyld_path(resolved):
                continue
            with resolved.open("rb") as source:
                if source.read(4) not in _MACHO_MAGICS:
                    raise ToolIdentityError(
                        f"Mach-O dependency is not a Mach-O image: {resolved}"
                    )
            verify_image(
                resolved,
                architecture,
                executable,
                run_paths,
                active | {path},
            )

    for path in macho_paths:
        for architecture in architectures(path):
            for executable in executables:
                if architecture not in architectures(executable):
                    raise ToolIdentityError(
                        f"Mach-O executable lacks {architecture} slice: {executable}"
                    )
                executable_commands = commands(executable, architecture)
                inherited = ()
                if path != executable:
                    inherited = _extend_run_path_stack(
                        (),
                        executable_commands,
                        executable,
                        executable,
                        installation.root,
                    )
                verify_image(path, architecture, executable, inherited, frozenset())


def smoke_macos_installation(installation: MacOSPythonInstallation) -> None:
    """Execute only the already-verified interpreter and prove its closure."""
    _verify_macho_dependency_closure(installation)
    probe = (
        "import json,sys;print(json.dumps({'executable':sys.executable,"
        "'prefix':sys.prefix,'base_prefix':sys.base_prefix,'path':sys.path},sort_keys=True))"
    )
    base_python = installation.root / "bin" / f"python{installation.root.name}"
    probes = (
        (base_python, False),
        (installation.executable, False),
        (installation.executable, True),
    )
    for interpreter, include_site in probes:
        arguments = [os.fspath(interpreter), "-I", "-B"]
        if not include_site:
            arguments.append("-S")
        code = probe
        if include_site:
            code = "import packaging,jsonschema;" + code
        arguments.extend(["-c", code])
        environment = {"PATH": "/usr/bin:/bin", "PYTHONDONTWRITEBYTECODE": "1"}
        if include_site:
            environment["DYLD_PRINT_LIBRARIES"] = "1"
        result = subprocess.run(
            arguments,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
            env=environment,
        )
        if result.returncode != 0:
            raise ToolIdentityError(
                f"packaging Python closure smoke failed: {result.stderr}"
            )
        report = json.loads(result.stdout)
        for field in ("executable", "prefix", "base_prefix"):
            if not _inside(Path(report[field]), installation.root):
                raise ToolIdentityError(f"packaging Python {field} escapes closure")
        for raw_path in report["path"]:
            if raw_path and not _inside(Path(raw_path), installation.root):
                raise ToolIdentityError(
                    f"packaging Python sys.path escapes closure: {raw_path}"
                )
        if include_site:
            for line in result.stderr.splitlines():
                if not line.startswith("dyld[") or "> /" not in line:
                    continue
                loaded = Path(line.rsplit(" ", 1)[1])
                if loaded.as_posix().startswith(("/usr/lib/", "/System/Library/")):
                    continue
                if not _inside(loaded, installation.root):
                    raise ToolIdentityError(
                        f"packaging Python dylib escapes closure: {loaded}"
                    )


def _prepare_macos_installation_locked(
    provenance: InstallerProvenance, staging: Path, token: str
) -> MacOSPythonInstallation:
    """Install official Python and hash-locked dependencies into root authority."""
    package = staging / f"python-{provenance.version}.pkg"
    try:
        recover_stale_installations(provenance, staging, token)
        _remove_previous_installation(provenance)
        _create_installation_root(provenance, staging, token)
        subprocess.run(["/usr/bin/sudo", "/bin/chmod", "0700", staging], check=True)
        subprocess.run(
            [
                "/usr/bin/sudo",
                "/usr/bin/curl",
                "--proto",
                "=https",
                "--tlsv1.2",
                "--fail",
                "--location",
                "--silent",
                "--show-error",
                "--output",
                package,
                provenance.installer_url,
            ],
            check=True,
            env={"PATH": "/usr/bin:/bin"},
        )
        subprocess.run(["/usr/bin/sudo", "/bin/chmod", "0555", staging], check=True)
        subprocess.run(["/usr/bin/sudo", "/bin/chmod", "0444", package], check=True)
        _root_owned_path(staging, "installer staging", sticky=STAGING_PARENT)
        _verify_installer(package, provenance)
        subprocess.run(["/usr/bin/sudo", "/bin/chmod", "0700", staging], check=True)
        expanded = staging / "expanded"
        subprocess.run(
            ["/usr/bin/sudo", "/usr/sbin/pkgutil", "--expand-full", package, expanded],
            check=True,
            env={"PATH": "/usr/bin:/bin"},
        )
        _seal_root_tree(staging, "expanded official installer")
        payload_executable_suffix = (
            Path("Payload/Library/Frameworks/Python.framework/Versions")
            / ".".join(provenance.version.split(".")[:2])
            / "bin"
            / f"python{'.'.join(provenance.version.split('.')[:2])}"
        )
        payload_executables = [
            candidate
            for candidate in expanded.rglob(payload_executable_suffix.name)
            if candidate.as_posix().endswith(payload_executable_suffix.as_posix())
            and candidate.is_file()
            and not candidate.is_symlink()
        ]
        if len(payload_executables) != 1:
            raise ToolIdentityError("official installer Framework payload is ambiguous")
        payload_root = payload_executables[0].parents[1]
        _root_owned_path(
            payload_root, "official installer payload", sticky=STAGING_PARENT
        )
        _require_code_authority(
            payload_executables[0],
            identifier=provenance.code_identifier,
            team_identifier=provenance.installer_team_id,
            label="official installer Python payload",
        )
        subprocess.run(
            [
                "/usr/bin/sudo",
                "/usr/bin/ditto",
                "--noqtn",
                payload_root,
                provenance.install_root,
            ],
            check=True,
            env={"PATH": "/usr/bin:/bin"},
        )
        base_python = (
            provenance.install_root
            / "bin"
            / f"python{'.'.join(provenance.version.split('.')[:2])}"
        )
        _root_owned_path(provenance.install_root, "official Python installation")
        _require_code_authority(
            base_python,
            identifier=provenance.code_identifier,
            team_identifier=provenance.installer_team_id,
            label="official Python",
        )
        venv = provenance.install_root / "tobkiri-packaging-venv"
        subprocess.run(
            ["/usr/bin/sudo", base_python, "-I", "-B", "-m", "venv", "--copies", venv],
            check=True,
            env={"PATH": "/usr/bin:/bin", "PYTHONDONTWRITEBYTECODE": "1"},
        )
        locked_copy = provenance.install_root / ".tobkiri-requirements.lock"
        copied = subprocess.run(
            ["/usr/bin/sudo", "/usr/bin/tee", locked_copy],
            input=provenance.requirements_bytes,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            check=True,
        )
        if copied.stderr:
            raise ToolIdentityError("could not stage hash-locked requirements")
        subprocess.run(
            ["/usr/bin/sudo", "/usr/sbin/chown", "root:wheel", locked_copy],
            check=True,
        )
        subprocess.run(["/usr/bin/sudo", "/bin/chmod", "0444", locked_copy], check=True)
        executable = provenance.install_root / provenance.executable
        subprocess.run(
            [
                "/usr/bin/sudo",
                executable,
                "-I",
                "-B",
                "-m",
                "pip",
                "install",
                "--require-hashes",
                "--only-binary=:all:",
                "--no-cache-dir",
                "--no-compile",
                "-r",
                locked_copy,
            ],
            check=True,
            env={"PATH": "/usr/bin:/bin", "PYTHONDONTWRITEBYTECODE": "1"},
        )
        _seal_root_tree(provenance.install_root, "packaging Python installation")
        code_identity = _require_code_authority(
            executable,
            identifier=provenance.code_identifier,
            team_identifier=provenance.installer_team_id,
            label="packaging Python",
        )
        installation = MacOSPythonInstallation(provenance.install_root, executable, "")
        inventory_sha256 = _write_inventory(installation, provenance, code_identity)
        installation = MacOSPythonInstallation(
            provenance.install_root, executable, inventory_sha256
        )
        verify_macos_installation(installation, provenance)
        smoke_macos_installation(installation)
        return installation
    except Exception as primary:
        cleanup_errors: list[str] = []
        try:
            recover_stale_installations(provenance, staging, token)
            cleanup_created_ancestors(provenance, staging, token)
            _remove_root_tree(staging)
        except Exception as cleanup:
            cleanup_errors.append(str(cleanup))
        if cleanup_errors:
            raise ToolIdentityError(
                f"packaging Python construction failed: {primary}; cleanup failed: "
                + "; ".join(cleanup_errors)
            ) from primary
        raise


def prepare_macos_installation(
    provenance: InstallerProvenance, staging: Path, token: str
) -> MacOSPythonInstallation:
    """Create and seal the installation under one root-owned OS lock lease."""
    ensure_installation_parent(provenance, staging, token)
    with _installation_lock(provenance, token):
        return _prepare_macos_installation_locked(provenance, staging, token)


def cleanup_macos_installation(
    root: Path, provenance: InstallerProvenance, inventory_sha256: str
) -> None:
    """Remove only a reverified formal installation."""
    _remove_verified_installation(root, provenance, inventory_sha256)


def _resolve_git(value: str | None) -> Path:
    if value:
        return Path(value)
    if sys.platform == "darwin":
        return MACOS_SYSTEM_GIT
    discovered = shutil.which("git")
    if discovered is None:
        raise ToolIdentityError("git is unavailable for explicit binding")
    return Path(discovered)


def bind_git(path: str | None = None) -> ToolIdentity:
    git = _canonical_absolute(_resolve_git(path), "Git")
    if sys.platform == "darwin":
        if git != MACOS_SYSTEM_GIT:
            raise ToolIdentityError(
                "formal macOS Git must be the fixed Command Line Tools executable"
            )
        _root_owned_path(git, "Git")
        _root_owned_path(ISOLATED_GIT_EXEC_PATH, "isolated Git environment")
        _require_code_authority(
            git,
            identifier=APPLE_GIT_IDENTIFIER,
            team_identifier=APPLE_TEAM_ID,
            label="Git",
        )
    return _regular_executable(git, "Git")


def bind_toolchain(
    *, python: str | None = None, git: str | None = None
) -> dict[str, ToolIdentity]:
    """Generic explicit binder retained for non-macOS tests and callers."""
    python_path = Path(python) if python else Path(sys.executable)
    git_path = Path(git) if git else _resolve_git(None)
    return {
        "python": _regular_executable(python_path, "Python"),
        "git": _regular_executable(git_path, "Git"),
    }


def environment_lines(
    identities: dict[str, ToolIdentity],
    installation: MacOSPythonInstallation | None = None,
) -> str:
    if set(identities) != {"python", "git"}:
        raise ToolIdentityError("toolchain identity set is incomplete")
    output = (
        f"TOBKIRI_PACKAGING_PYTHON={identities['python'].path}\n"
        f"TOBKIRI_PACKAGING_PYTHON_SHA256={identities['python'].sha256}\n"
        f"TOBKIRI_PACKAGING_GIT={identities['git'].path}\n"
        f"TOBKIRI_PACKAGING_GIT_SHA256={identities['git'].sha256}\n"
    )
    if installation is not None:
        output += (
            f"TOBKIRI_PACKAGING_PYTHON_SNAPSHOT={installation.root}\n"
            f"TOBKIRI_PACKAGING_PYTHON_INVENTORY_SHA256={installation.inventory_sha256}\n"
        )
    return output


def write_environment_file(path: Path, payload: str) -> None:
    if path.exists() or path.is_symlink():
        metadata = path.lstat()
        if path.is_symlink() or not stat.S_ISREG(metadata.st_mode):
            raise ToolIdentityError(f"unsafe environment output: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            delete=False,
        ) as output:
            temporary = Path(output.name)
            output.write(payload)
            output.flush()
            os.fsync(output.fileno())
        temporary.chmod(0o600)
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    parser.add_argument("--provenance", type=Path)
    parser.add_argument("--source-commit")
    parser.add_argument("--transaction-token")
    parser.add_argument("--git")
    parser.add_argument("--git-sha256")
    parser.add_argument("--smoke-git-authority", action="store_true")
    parser.add_argument("--env-output", type=Path)
    parser.add_argument("--prepare-macos-installation", action="store_true")
    parser.add_argument("--verify-macos-installation", type=Path)
    parser.add_argument("--inventory-sha256")
    parser.add_argument("--cleanup-macos-installation", type=Path)
    parser.add_argument("--cleanup-transaction", action="store_true")
    args = parser.parse_args()
    installation: MacOSPythonInstallation | None = None
    provenance: InstallerProvenance | None = None
    try:
        repository_root = args.repository_root.resolve(strict=True)
        if args.smoke_git_authority:
            if args.git is None or not _valid_sha256(args.git_sha256):
                raise ToolIdentityError(
                    "--git and --git-sha256 are required for the Git smoke"
                )
            if args.source_commit is None or args.provenance is None:
                raise ToolIdentityError(
                    "--source-commit and --provenance are required for the Git smoke"
                )
            git_identity = bind_git(args.git)
            if git_identity.sha256 != args.git_sha256:
                raise ToolIdentityError("Git smoke digest differs from formal binding")
            smoke_git_authority(
                git_identity,
                repository_root,
                args.source_commit,
                _safe_relative(args.provenance.as_posix(), "provenance"),
            )
            return 0
        if args.transaction_token is None:
            raise ToolIdentityError("--transaction-token is required")
        transaction_absent = _transaction_is_absent(args.transaction_token)
        if (
            args.cleanup_transaction
            and args.cleanup_macos_installation is None
            and transaction_absent
        ):
            sys.stderr.write(
                "packaging transaction is already absent; cleanup is a no-op\n"
            )
            return 0
        if args.cleanup_macos_installation is not None and transaction_absent:
            raise ToolIdentityError(
                "packaging installation authority transaction is absent; "
                "installation residue retained fail-closed"
            )
        if args.cleanup_transaction and args.cleanup_macos_installation is None:
            cleanup_transaction(args.transaction_token)
            return 0
        if args.prepare_macos_installation:
            if args.provenance is None or args.source_commit is None:
                raise ToolIdentityError(
                    "--provenance and --source-commit are required for preparation"
                )
            provenance_relative = _safe_relative(
                args.provenance.as_posix(), "provenance"
            )
            git_identity = bind_git(args.git)
            smoke_git_authority(
                git_identity,
                repository_root,
                args.source_commit,
                provenance_relative,
            )
            provenance, staging = seal_committed_authority(
                git_identity,
                repository_root,
                args.source_commit,
                provenance_relative,
                args.transaction_token,
            )
        else:
            provenance, staging = load_sealed_authority(args.transaction_token)
        if args.cleanup_macos_installation is not None:
            if not _valid_sha256(args.inventory_sha256):
                raise ToolIdentityError("--inventory-sha256 is required")
            cleanup_macos_installation(
                args.cleanup_macos_installation,
                provenance,
                args.inventory_sha256,
            )
        if args.cleanup_transaction:
            cleanup_transaction(args.transaction_token)
            return 0
        if args.cleanup_macos_installation is not None:
            return 0
        if args.verify_macos_installation is not None:
            if not _valid_sha256(args.inventory_sha256):
                raise ToolIdentityError("--inventory-sha256 is required")
            executable = args.verify_macos_installation / provenance.executable
            installation = MacOSPythonInstallation(
                args.verify_macos_installation, executable, args.inventory_sha256
            )
            verify_macos_installation(installation, provenance)
            smoke_macos_installation(installation)
            return 0
        if sys.platform != "darwin" or not args.prepare_macos_installation:
            raise ToolIdentityError(
                "formal macOS binding requires --prepare-macos-installation"
            )
        installation = prepare_macos_installation(
            provenance, staging, args.transaction_token
        )
        identities = {
            "python": verify_macos_installation(installation, provenance),
            "git": git_identity,
        }
        payload = environment_lines(identities, installation)
        if args.env_output is None:
            sys.stdout.write(payload)
        else:
            write_environment_file(args.env_output, payload)
    except (OSError, subprocess.SubprocessError, ToolIdentityError) as error:
        if installation is not None and provenance is not None:
            try:
                cleanup_macos_installation(
                    installation.root,
                    provenance,
                    installation.inventory_sha256,
                )
                if args.transaction_token is not None:
                    cleanup_transaction(args.transaction_token)
            except Exception as cleanup:
                parser.error(f"{error}; cleanup failed: {cleanup}")
        parser.error(str(error))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
