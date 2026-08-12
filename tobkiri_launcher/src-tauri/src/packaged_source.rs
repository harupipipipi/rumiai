//! Trusted verifier and snapshotter for the packaged Defaults Python source closure.
//!
//! No Python code is imported until every declared source has been copied from
//! a digest-verified file handle into a private, link-free snapshot.

use std::collections::{BTreeMap, BTreeSet};
use std::fs::{self, File, OpenOptions};
use std::io::{self, Read, Write};
use std::path::{Component, Path, PathBuf};
use std::time::{SystemTime, UNIX_EPOCH};

use serde_json::Value;
use sha2::{Digest, Sha256};

const SCHEMA: &str = "io.tobkiri.packaged-defaultspack-source.v1";
const ROOTS: &[&str] = &[
    "scripts",
    "tobkiri_protocol",
    "ecosystem/defaultspack/domain/runtime_v4",
    "ecosystem/defaultspack/v4",
    "ecosystem/defaultspack/runtime",
    "ecosystem/defaultspack/defaultspack",
];
const FILES: &[&str] = &[
    "ecosystem/defaultspack/pack.v4.json",
    "ecosystem/defaultspack/contracts.v4.json",
    "ecosystem/defaultspack/artifact-index.v4.json",
];
const MAX_MANIFEST_BYTES: u64 = 4 * 1024 * 1024;
const MAX_SOURCE_BYTES: u64 = 256 * 1024 * 1024;
const PROVENANCE_FILENAME: &str = "packaging-source-provenance.v1.json";
const MAX_PROVENANCE_BYTES: usize = 64 * 1024;

fn invalid(message: impl Into<String>) -> io::Error {
    io::Error::new(io::ErrorKind::InvalidData, message.into())
}

#[derive(Debug, Clone)]
struct ExpectedFile {
    size: u64,
    sha256: String,
    executable: bool,
}

/// A verified source tree. Its directory is removed when the value is dropped.
#[derive(Debug)]
pub struct VerifiedSourceSnapshot {
    owner: PathBuf,
    root: PathBuf,
    owner_identity: (u64, u64, u64, i64, i64),
    root_identity: (u64, u64, u64, i64, i64),
    root_handle: File,
    trusted_manifest: Vec<u8>,
    provenance: Option<Vec<u8>>,
    cleaned: bool,
}

impl VerifiedSourceSnapshot {
    pub fn root(&self) -> &Path {
        &self.root
    }
}

impl Drop for VerifiedSourceSnapshot {
    fn drop(&mut self) {
        if !self.cleaned {
            let _ = self.cleanup_inner();
        }
    }
}

impl VerifiedSourceSnapshot {
    pub fn verify_unchanged(&self) -> io::Result<()> {
        if identity(&self.root_handle.metadata()?) != self.root_identity
            || identity(&fs::symlink_metadata(&self.root)?) != self.root_identity
            || identity(&fs::symlink_metadata(&self.owner)?) != self.owner_identity
        {
            return Err(invalid("verified source snapshot root identity changed"));
        }
        verify_snapshot(&self.root, &self.trusted_manifest)?;
        if let Some(expected) = &self.provenance {
            let actual = read_manifest(&self.root.join(PROVENANCE_FILENAME))?;
            if &actual != expected {
                return Err(invalid("verified source provenance changed"));
            }
        }
        Ok(())
    }

    pub fn bind_provenance(&mut self, bytes: &[u8]) -> io::Result<PathBuf> {
        if self.provenance.is_some() || bytes.is_empty() || bytes.len() > MAX_PROVENANCE_BYTES {
            return Err(invalid("source provenance binding is invalid"));
        }
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            fs::set_permissions(&self.root, fs::Permissions::from_mode(0o700))?;
        }
        let path = self.root.join(PROVENANCE_FILENAME);
        let result = (|| {
            let mut output = OpenOptions::new()
                .write(true)
                .create_new(true)
                .open(&path)?;
            output.write_all(bytes)?;
            output.sync_all()?;
            #[cfg(unix)]
            {
                use std::os::unix::fs::PermissionsExt;
                fs::set_permissions(&path, fs::Permissions::from_mode(0o400))?;
                fs::set_permissions(&self.root, fs::Permissions::from_mode(0o500))?;
            }
            Ok::<_, io::Error>(())
        })();
        if result.is_err() {
            #[cfg(unix)]
            {
                use std::os::unix::fs::PermissionsExt;
                let _ = fs::set_permissions(&self.root, fs::Permissions::from_mode(0o500));
            }
            return result.map(|_| path);
        }
        self.provenance = Some(bytes.to_vec());
        self.root_identity = identity(&self.root_handle.metadata()?);
        self.verify_unchanged()?;
        Ok(path)
    }

    pub fn cleanup(mut self) -> io::Result<()> {
        let result = self.cleanup_inner();
        if result.is_ok() {
            self.cleaned = true;
        }
        result
    }

    fn cleanup_inner(&mut self) -> io::Result<()> {
        if identity(&self.root_handle.metadata()?) != self.root_identity
            || identity(&fs::symlink_metadata(&self.root)?) != self.root_identity
            || identity(&fs::symlink_metadata(&self.owner)?) != self.owner_identity
        {
            return Err(invalid(
                "refusing to clean a replaced verified source snapshot",
            ));
        }
        make_tree_owner_writable(&self.root)?;
        fs::remove_dir_all(&self.root)?;
        fs::remove_dir(&self.owner)?;
        Ok(())
    }
}

fn exact_keys(value: &serde_json::Map<String, Value>, expected: &[&str]) -> bool {
    value.keys().map(String::as_str).collect::<BTreeSet<_>>()
        == expected.iter().copied().collect::<BTreeSet<_>>()
}

fn safe_relative(value: &str) -> bool {
    !value.is_empty()
        && !value.contains(['\\', '\0'])
        && !value.starts_with('~')
        && !Path::new(value).is_absolute()
        && Path::new(value)
            .components()
            .all(|component| matches!(component, Component::Normal(_)))
        && Path::new(value).to_string_lossy().replace('\\', "/") == value
}

fn parse_manifest(bytes: &[u8]) -> io::Result<BTreeMap<String, ExpectedFile>> {
    let value: Value = serde_json::from_slice(bytes)
        .map_err(|error| invalid(format!("source manifest is malformed: {error}")))?;
    let object = value
        .as_object()
        .ok_or_else(|| invalid("source manifest must be an object"))?;
    if !exact_keys(object, &["schema", "roots", "files"]) {
        return Err(invalid("source manifest has unknown or missing fields"));
    }
    if object.get("schema").and_then(Value::as_str) != Some(SCHEMA) {
        return Err(invalid("source manifest schema marker is unknown"));
    }
    let roots = object
        .get("roots")
        .and_then(Value::as_array)
        .ok_or_else(|| invalid("source manifest roots must be an array"))?;
    if roots.len() != ROOTS.len()
        || roots
            .iter()
            .zip(ROOTS)
            .any(|(actual, expected)| actual.as_str() != Some(expected))
    {
        return Err(invalid(
            "source manifest roots differ from the trusted closure",
        ));
    }
    let files = object
        .get("files")
        .and_then(Value::as_array)
        .filter(|files| !files.is_empty())
        .ok_or_else(|| invalid("source manifest files must be a non-empty array"))?;
    let mut expected = BTreeMap::new();
    let mut previous: Option<&str> = None;
    for value in files {
        let entry = value
            .as_object()
            .ok_or_else(|| invalid("source manifest file entry must be an object"))?;
        if !exact_keys(entry, &["path", "type", "size", "sha256", "executable"]) {
            return Err(invalid(
                "source manifest file entry has unknown or missing fields",
            ));
        }
        let path = entry
            .get("path")
            .and_then(Value::as_str)
            .ok_or_else(|| invalid("source manifest path must be a string"))?;
        if !safe_relative(path)
            || !ROOTS
                .iter()
                .any(|root| path.starts_with(&format!("{root}/")))
                && !FILES.contains(&path)
        {
            return Err(invalid(format!(
                "source manifest path is outside the closure: {path:?}"
            )));
        }
        if previous.is_some_and(|value| value >= path) {
            return Err(invalid("source manifest paths must be unique and sorted"));
        }
        previous = Some(path);
        if entry.get("type").and_then(Value::as_str) != Some("regular-file") {
            return Err(invalid(format!(
                "source manifest type is not regular-file: {path}"
            )));
        }
        let size = entry
            .get("size")
            .and_then(Value::as_u64)
            .filter(|size| *size <= MAX_SOURCE_BYTES)
            .ok_or_else(|| invalid(format!("source manifest size is invalid: {path}")))?;
        let sha256 = entry
            .get("sha256")
            .and_then(Value::as_str)
            .filter(|digest| {
                digest.len() == 64
                    && digest
                        .bytes()
                        .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
            })
            .ok_or_else(|| invalid(format!("source manifest SHA-256 is invalid: {path}")))?;
        let executable = entry
            .get("executable")
            .and_then(Value::as_bool)
            .ok_or_else(|| {
                invalid(format!(
                    "source manifest executable flag is invalid: {path}"
                ))
            })?;
        expected.insert(
            path.to_owned(),
            ExpectedFile {
                size,
                sha256: sha256.to_owned(),
                executable,
            },
        );
    }
    Ok(expected)
}

#[cfg(unix)]
fn identity(metadata: &fs::Metadata) -> (u64, u64, u64, i64, i64) {
    use std::os::unix::fs::MetadataExt;
    (
        metadata.dev(),
        metadata.ino(),
        metadata.len(),
        metadata.mtime_nsec(),
        metadata.ctime_nsec(),
    )
}

#[cfg(not(unix))]
fn identity(metadata: &fs::Metadata) -> (u64, u64, u64, i64, i64) {
    let modified = metadata
        .modified()
        .ok()
        .and_then(|time| time.duration_since(UNIX_EPOCH).ok())
        .map_or(0, |time| time.as_nanos() as i64);
    (0, 0, metadata.len(), modified, 0)
}

#[cfg(unix)]
fn reject_hardlink(metadata: &fs::Metadata, path: &Path) -> io::Result<()> {
    use std::os::unix::fs::MetadataExt;
    if metadata.nlink() != 1 {
        return Err(invalid(format!(
            "source closure contains a hardlink: {}",
            path.display()
        )));
    }
    Ok(())
}

#[cfg(windows)]
fn reject_hardlink(metadata: &fs::Metadata, path: &Path) -> io::Result<()> {
    use std::mem::MaybeUninit;
    use std::os::windows::io::AsRawHandle;
    use windows_sys::Win32::Storage::FileSystem::{
        GetFileInformationByHandle, BY_HANDLE_FILE_INFORMATION,
    };

    if !metadata.is_file() {
        return Ok(());
    }
    let file = File::open(path)?;
    let mut information = MaybeUninit::<BY_HANDLE_FILE_INFORMATION>::zeroed();
    if unsafe { GetFileInformationByHandle(file.as_raw_handle(), information.as_mut_ptr()) } == 0 {
        return Err(invalid(format!(
            "failed to inspect source closure links at {}: {}",
            path.display(),
            io::Error::last_os_error()
        )));
    }
    if unsafe { information.assume_init() }.nNumberOfLinks != 1 {
        return Err(invalid(format!(
            "source closure contains a hardlink: {}",
            path.display()
        )));
    }
    Ok(())
}

#[cfg(not(any(unix, windows)))]
fn reject_hardlink(_metadata: &fs::Metadata, _path: &Path) -> io::Result<()> {
    Ok(())
}

#[cfg(unix)]
fn executable(metadata: &fs::Metadata) -> bool {
    use std::os::unix::fs::PermissionsExt;
    metadata.permissions().mode() & 0o111 != 0
}

#[cfg(not(unix))]
fn executable(_metadata: &fs::Metadata) -> bool {
    false
}

fn collect_actual(root: &Path, current: &Path, actual: &mut BTreeSet<String>) -> io::Result<()> {
    let metadata = fs::symlink_metadata(current)?;
    if metadata.file_type().is_symlink() || !metadata.is_dir() {
        return Err(invalid(format!(
            "source closure root is not a real directory: {}",
            current.display()
        )));
    }
    let mut entries = fs::read_dir(current)?.collect::<Result<Vec<_>, _>>()?;
    entries.sort_by_key(fs::DirEntry::file_name);
    for entry in entries {
        let path = entry.path();
        let metadata = fs::symlink_metadata(&path)?;
        if metadata.file_type().is_symlink() {
            return Err(invalid(format!(
                "source closure contains a symlink: {}",
                path.display()
            )));
        }
        if metadata.is_dir() {
            collect_actual(root, &path, actual)?;
        } else if metadata.is_file() {
            reject_hardlink(&metadata, &path)?;
            let relative = path
                .strip_prefix(root)
                .map_err(|_| invalid("source closure path escaped its root"))?
                .to_string_lossy()
                .replace('\\', "/");
            if !actual.insert(relative) {
                return Err(invalid("source closure contains a duplicate path"));
            }
        } else {
            return Err(invalid(format!(
                "source closure contains a special entry: {}",
                path.display()
            )));
        }
    }
    Ok(())
}

fn create_snapshot(parent: &Path) -> io::Result<(PathBuf, PathBuf)> {
    fs::create_dir_all(parent)?;
    let parent_metadata = fs::symlink_metadata(parent)?;
    if parent_metadata.file_type().is_symlink() || !parent_metadata.is_dir() {
        return Err(invalid("source snapshot parent is not a real directory"));
    }
    let canonical_parent = parent.canonicalize()?;
    for attempt in 0..128_u32 {
        let nonce = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .map_err(io::Error::other)?
            .as_nanos();
        let owner = canonical_parent.join(format!(
            "packaged-source-snapshot-{}-{nonce}-{attempt}",
            std::process::id()
        ));
        match fs::create_dir(&owner) {
            Ok(()) => {
                #[cfg(unix)]
                {
                    use std::os::unix::fs::MetadataExt;
                    use std::os::unix::fs::PermissionsExt;
                    fs::set_permissions(&owner, fs::Permissions::from_mode(0o700))?;
                    if fs::symlink_metadata(&owner)?.uid() != unsafe { libc::geteuid() } {
                        return Err(invalid("source snapshot owner has the wrong user"));
                    }
                }
                let root = owner.join("source");
                fs::create_dir(&root)?;
                #[cfg(unix)]
                {
                    use std::os::unix::fs::PermissionsExt;
                    fs::set_permissions(&root, fs::Permissions::from_mode(0o700))?;
                }
                return Ok((owner, root));
            }
            Err(error) if error.kind() == io::ErrorKind::AlreadyExists => continue,
            Err(error) => return Err(error),
        }
    }
    Err(invalid("could not create a unique source snapshot"))
}

fn write_trusted_manifest(root: &Path, bytes: &[u8]) -> io::Result<()> {
    let path = root.join("packaged_defaultspack_source_manifest.v1.json");
    let mut output = OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(&path)?;
    output.write_all(bytes)?;
    output.sync_all()?;
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        fs::set_permissions(path, fs::Permissions::from_mode(0o400))?;
    }
    Ok(())
}

fn verify_snapshot(root: &Path, trusted_manifest: &[u8]) -> io::Result<()> {
    let expected = parse_manifest(trusted_manifest)?;
    if read_manifest(&root.join("packaged_defaultspack_source_manifest.v1.json"))?
        != trusted_manifest
    {
        return Err(invalid("verified snapshot manifest changed"));
    }
    let mut actual = BTreeSet::new();
    for relative in ROOTS {
        collect_actual(root, &root.join(relative), &mut actual)?;
    }
    for relative in FILES {
        let path = root.join(relative);
        let metadata = fs::symlink_metadata(&path)?;
        if metadata.file_type().is_symlink() || !metadata.is_file() {
            return Err(invalid("verified snapshot file type changed"));
        }
        actual.insert((*relative).to_owned());
    }
    if actual != expected.keys().cloned().collect() {
        return Err(invalid("verified snapshot inventory changed"));
    }
    for (relative, record) in expected {
        let path = root.join(relative);
        verify_snapshot_file(&path, &record)?;
    }
    Ok(())
}

fn verify_snapshot_file(path: &Path, expected: &ExpectedFile) -> io::Result<()> {
    let before = fs::symlink_metadata(path)?;
    if before.file_type().is_symlink()
        || !before.is_file()
        || before.len() != expected.size
        || executable(&before) != expected.executable
    {
        return Err(invalid("verified snapshot metadata changed"));
    }
    let mut input = File::open(path)?;
    if identity(&input.metadata()?) != identity(&before) {
        return Err(invalid("verified snapshot changed while opened"));
    }
    let mut digest = Sha256::new();
    let mut size = 0_u64;
    let mut buffer = [0_u8; 1024 * 1024];
    loop {
        let count = input.read(&mut buffer)?;
        if count == 0 {
            break;
        }
        size = size
            .checked_add(count as u64)
            .ok_or_else(|| invalid("verified snapshot size overflow"))?;
        if size > expected.size {
            return Err(invalid("verified snapshot grew while read"));
        }
        digest.update(&buffer[..count]);
    }
    let after = fs::symlink_metadata(path)?;
    if identity(&after) != identity(&before)
        || size != expected.size
        || format!("{:x}", digest.finalize()) != expected.sha256
    {
        return Err(invalid("verified snapshot digest or identity changed"));
    }
    Ok(())
}

fn seal_directories(path: &Path) -> io::Result<()> {
    for entry in fs::read_dir(path)? {
        let entry = entry?;
        let metadata = fs::symlink_metadata(entry.path())?;
        if metadata.is_dir() && !metadata.file_type().is_symlink() {
            seal_directories(&entry.path())?;
        }
    }
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        fs::set_permissions(path, fs::Permissions::from_mode(0o500))?;
    }
    Ok(())
}

fn make_tree_owner_writable(path: &Path) -> io::Result<()> {
    let metadata = fs::symlink_metadata(path)?;
    if metadata.file_type().is_symlink() || !metadata.is_dir() {
        return Err(invalid("snapshot cleanup encountered a replaced directory"));
    }
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        fs::set_permissions(path, fs::Permissions::from_mode(0o700))?;
    }
    for entry in fs::read_dir(path)? {
        let entry = entry?;
        let metadata = fs::symlink_metadata(entry.path())?;
        if metadata.file_type().is_symlink() {
            return Err(invalid("snapshot cleanup encountered a symlink"));
        }
        if metadata.is_dir() {
            make_tree_owner_writable(&entry.path())?;
        }
    }
    Ok(())
}

fn copy_verified(source: &Path, target: &Path, expected: &ExpectedFile) -> io::Result<()> {
    let before = fs::symlink_metadata(source)?;
    if before.file_type().is_symlink() || !before.is_file() {
        return Err(invalid(format!(
            "source is not a regular file: {}",
            source.display()
        )));
    }
    reject_hardlink(&before, source)?;
    if before.len() != expected.size || executable(&before) != expected.executable {
        return Err(invalid(format!(
            "source metadata differs from manifest: {}",
            source.display()
        )));
    }
    let mut input = File::open(source)?;
    let opened = input.metadata()?;
    if identity(&opened) != identity(&before) {
        return Err(invalid(format!(
            "source changed while opened: {}",
            source.display()
        )));
    }
    if let Some(parent) = target.parent() {
        fs::create_dir_all(parent)?;
    }
    let mut output = OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(target)?;
    let mut digest = Sha256::new();
    let mut count = 0_u64;
    let mut buffer = [0_u8; 1024 * 1024];
    loop {
        let read = input.read(&mut buffer)?;
        if read == 0 {
            break;
        }
        count = count
            .checked_add(read as u64)
            .ok_or_else(|| invalid("source size overflow"))?;
        if count > expected.size {
            return Err(invalid(format!(
                "source grew while copied: {}",
                source.display()
            )));
        }
        digest.update(&buffer[..read]);
        output.write_all(&buffer[..read])?;
    }
    output.sync_all()?;
    let after = fs::symlink_metadata(source)?;
    if after.file_type().is_symlink()
        || !after.is_file()
        || identity(&after) != identity(&before)
        || count != expected.size
        || format!("{:x}", digest.finalize()) != expected.sha256
    {
        return Err(invalid(format!(
            "source content changed or mismatched: {}",
            source.display()
        )));
    }
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        fs::set_permissions(
            target,
            fs::Permissions::from_mode(if expected.executable { 0o500 } else { 0o400 }),
        )?;
    }
    Ok(())
}

fn read_manifest(path: &Path) -> io::Result<Vec<u8>> {
    let metadata = fs::symlink_metadata(path)?;
    if metadata.file_type().is_symlink()
        || !metadata.is_file()
        || metadata.len() > MAX_MANIFEST_BYTES
    {
        return Err(invalid(
            "source manifest must be a bounded regular non-symlink file",
        ));
    }
    reject_hardlink(&metadata, path)?;
    let input = File::open(path)?;
    if identity(&input.metadata()?) != identity(&metadata) {
        return Err(invalid("source manifest changed while opened"));
    }
    let mut bytes = Vec::with_capacity(metadata.len() as usize);
    input.take(MAX_MANIFEST_BYTES + 1).read_to_end(&mut bytes)?;
    if bytes.len() as u64 != metadata.len() {
        return Err(invalid("source manifest size changed while read"));
    }
    let after = fs::symlink_metadata(path)?;
    if identity(&metadata) != identity(&after) {
        return Err(invalid("source manifest changed while read"));
    }
    Ok(bytes)
}

/// Verify the complete source closure and return an immutable-by-construction copy.
#[cfg(test)]
pub fn verify_and_snapshot(
    runtime_root: &Path,
    snapshot_parent: &Path,
) -> io::Result<VerifiedSourceSnapshot> {
    let manifest =
        read_manifest(&runtime_root.join("packaged_defaultspack_source_manifest.v1.json"))?;
    verify_and_snapshot_against_manifest_with_hook(runtime_root, snapshot_parent, &manifest, || {})
}

/// Verify against manifest bytes obtained from a separate trusted authority.
pub fn verify_and_snapshot_against_manifest(
    runtime_root: &Path,
    snapshot_parent: &Path,
    trusted_manifest: &[u8],
) -> io::Result<VerifiedSourceSnapshot> {
    verify_and_snapshot_against_manifest_with_hook(
        runtime_root,
        snapshot_parent,
        trusted_manifest,
        || {},
    )
}

fn verify_and_snapshot_against_manifest_with_hook(
    runtime_root: &Path,
    snapshot_parent: &Path,
    trusted_manifest: &[u8],
    before_copy: impl FnOnce(),
) -> io::Result<VerifiedSourceSnapshot> {
    let root_metadata = fs::symlink_metadata(runtime_root)?;
    if root_metadata.file_type().is_symlink() || !root_metadata.is_dir() {
        return Err(invalid("packaged source root must be a real directory"));
    }
    if trusted_manifest.len() as u64 > MAX_MANIFEST_BYTES {
        return Err(invalid("trusted source manifest exceeds its size bound"));
    }
    let actual_manifest =
        read_manifest(&runtime_root.join("packaged_defaultspack_source_manifest.v1.json"))?;
    if actual_manifest != trusted_manifest {
        return Err(invalid(
            "working source manifest differs from the trusted authority",
        ));
    }
    let manifest = parse_manifest(trusted_manifest)?;
    let mut actual = BTreeSet::new();
    for relative in ROOTS {
        collect_actual(runtime_root, &runtime_root.join(relative), &mut actual)?;
    }
    for relative in FILES {
        let path = runtime_root.join(relative);
        let metadata = fs::symlink_metadata(&path)?;
        if metadata.file_type().is_symlink() || !metadata.is_file() {
            return Err(invalid(format!(
                "source closure file is not regular: {relative}"
            )));
        }
        reject_hardlink(&metadata, &path)?;
        actual.insert((*relative).to_owned());
    }
    if actual != manifest.keys().cloned().collect() {
        return Err(invalid(
            "actual source paths differ from the strict manifest",
        ));
    }
    before_copy();
    let (snapshot_owner, snapshot_root) = create_snapshot(snapshot_parent)?;
    let result = (|| {
        for (relative, expected) in &manifest {
            copy_verified(
                &runtime_root.join(relative),
                &snapshot_root.join(relative),
                expected,
            )?;
        }
        write_trusted_manifest(&snapshot_root, trusted_manifest)?;
        verify_snapshot(&snapshot_root, trusted_manifest)?;
        seal_directories(&snapshot_root)?;
        if identity(&fs::symlink_metadata(runtime_root)?) != identity(&root_metadata) {
            return Err(invalid("packaged source root changed during verification"));
        }
        let root_handle = File::open(&snapshot_root)?;
        Ok(VerifiedSourceSnapshot {
            owner_identity: identity(&fs::symlink_metadata(&snapshot_owner)?),
            root_identity: identity(&root_handle.metadata()?),
            owner: snapshot_owner.clone(),
            root: snapshot_root.clone(),
            root_handle,
            trusted_manifest: trusted_manifest.to_vec(),
            provenance: None,
            cleaned: false,
        })
    })();
    if result.is_err() {
        let _ = make_tree_owner_writable(&snapshot_root);
        let _ = fs::remove_dir_all(&snapshot_root);
        let _ = fs::remove_dir(&snapshot_owner);
    }
    result
}

#[cfg(test)]
mod tests {
    use super::*;

    struct Tree(PathBuf);
    impl Tree {
        fn new(label: &str) -> Self {
            let root = std::env::temp_dir().join(format!(
                "tobkiri-source-{label}-{}-{}",
                std::process::id(),
                SystemTime::now()
                    .duration_since(UNIX_EPOCH)
                    .unwrap()
                    .as_nanos()
            ));
            fs::create_dir_all(&root).unwrap();
            Self(root)
        }
    }
    impl Drop for Tree {
        fn drop(&mut self) {
            let _ = fs::remove_dir_all(&self.0);
        }
    }

    fn fixture(tree: &Tree) -> PathBuf {
        let root = tree.0.join("runtime");
        if root.exists() {
            fs::remove_dir_all(&root).unwrap();
        }
        for relative in ROOTS {
            fs::create_dir_all(root.join(relative)).unwrap();
        }
        let mut records = Vec::new();
        let mut paths = ROOTS
            .iter()
            .map(|root| format!("{root}/fixture.py"))
            .collect::<Vec<_>>();
        paths.extend(FILES.iter().map(|path| (*path).to_owned()));
        paths.sort();
        for relative in paths {
            let path = root.join(&relative);
            fs::create_dir_all(path.parent().unwrap()).unwrap();
            let payload = format!("safe:{relative}\n");
            fs::write(&path, payload.as_bytes()).unwrap();
            records.push(serde_json::json!({
                "path": relative, "type": "regular-file", "size": payload.len(),
                "sha256": format!("{:x}", Sha256::digest(payload.as_bytes())), "executable": false
            }));
        }
        fs::write(
            root.join("packaged_defaultspack_source_manifest.v1.json"),
            serde_json::to_vec(&serde_json::json!({
                "schema": SCHEMA, "roots": ROOTS, "files": records
            }))
            .unwrap(),
        )
        .unwrap();
        root
    }

    fn mutate_first_manifest_entry(root: &Path, mutate: impl FnOnce(&mut Value)) {
        let path = root.join("packaged_defaultspack_source_manifest.v1.json");
        let mut manifest: Value = serde_json::from_slice(&fs::read(&path).unwrap()).unwrap();
        mutate(&mut manifest["files"][0]);
        fs::write(path, serde_json::to_vec(&manifest).unwrap()).unwrap();
    }

    #[test]
    fn verified_snapshot_contains_only_manifest_bytes() {
        let tree = Tree::new("valid");
        let root = fixture(&tree);
        let snapshot = verify_and_snapshot(&root, &tree.0.join("snapshots")).unwrap();
        assert_eq!(
            fs::read(snapshot.root().join("scripts/fixture.py")).unwrap(),
            b"safe:scripts/fixture.py\n"
        );
        assert_eq!(
            fs::read(
                snapshot
                    .root()
                    .join("packaged_defaultspack_source_manifest.v1.json")
            )
            .unwrap(),
            fs::read(root.join("packaged_defaultspack_source_manifest.v1.json")).unwrap()
        );
    }

    #[test]
    fn repository_manifest_produces_a_verified_snapshot_without_python() {
        let tree = Tree::new("repository");
        let runtime_root = Path::new(env!("CARGO_MANIFEST_DIR"))
            .parent()
            .and_then(Path::parent)
            .unwrap()
            .join("tobkiri_runtime");
        let snapshot = verify_and_snapshot(&runtime_root, &tree.0).unwrap();
        assert!(snapshot
            .root()
            .join("scripts/generate_packaged_defaultspack_v4_bundle.py")
            .is_file());
        assert!(!snapshot.root().join("scripts/__pycache__").exists());
    }

    #[test]
    fn actual_isolated_generator_imports_from_verified_snapshot() {
        let tree = Tree::new("generator-integration");
        let runtime_root = Path::new(env!("CARGO_MANIFEST_DIR"))
            .parent()
            .and_then(Path::parent)
            .unwrap()
            .join("tobkiri_runtime");
        let mut snapshot = verify_and_snapshot(&runtime_root, &tree.0).unwrap();
        let provenance = br#"{"schema":"io.tobkiri.packaging-source-provenance.v1","source_commit":"fixture","source_tree":"fixture","source_clean":true}"#;
        let provenance_path = snapshot.bind_provenance(provenance).unwrap();
        let python = super::super::packaging_toolchain::verified_tool("python").unwrap();
        if !python
            .command()
            .unwrap()
            .args(["-I", "-B", "-c", "import packaging"])
            .status()
            .unwrap()
            .success()
        {
            eprintln!("skipping generator integration: packaging dependency is unavailable");
            snapshot.cleanup().unwrap();
            return;
        }
        let mut command = super::super::isolated_python_module_command(
            &python,
            snapshot.root(),
            "scripts.generate_packaged_defaultspack_v4_bundle",
        )
        .unwrap();
        super::super::bind_source_provenance_command(&mut command, &provenance_path);
        command.arg("--help");
        assert!(command
            .get_args()
            .any(|arg| arg == std::ffi::OsStr::new("--source-provenance-file")));
        assert!(command
            .get_envs()
            .all(|(key, _)| key != std::ffi::OsStr::new("PATH")));
        let status = command.status().unwrap();
        assert!(
            status.success(),
            "actual isolated generator import must pass"
        );
        snapshot.verify_unchanged().unwrap();
        snapshot.cleanup().unwrap();
    }

    #[test]
    fn tampered_source_fails_closed() {
        let tree = Tree::new("tamper");
        let root = fixture(&tree);
        fs::write(root.join("scripts/fixture.py"), b"tampered\n").unwrap();
        assert!(verify_and_snapshot(&root, &tree.0.join("snapshots")).is_err());
    }

    #[test]
    fn manifest_type_size_digest_and_executable_are_strict() {
        let tree = Tree::new("manifest-metadata");
        for field in ["type", "size", "sha256", "executable"] {
            let root = fixture(&tree);
            mutate_first_manifest_entry(&root, |entry| match field {
                "type" => entry["type"] = Value::String("device".to_owned()),
                "size" => entry["size"] = Value::from(1_000_000_u64),
                "sha256" => entry["sha256"] = Value::String("0".repeat(64)),
                "executable" => entry["executable"] = Value::Bool(true),
                _ => unreachable!(),
            });
            assert!(
                verify_and_snapshot(&root, &tree.0.join(format!("snapshot-{field}"))).is_err(),
                "manifest {field} drift must fail closed"
            );
        }
    }

    #[test]
    fn extra_pyc_fails_closed() {
        let tree = Tree::new("pyc");
        let root = fixture(&tree);
        fs::create_dir_all(root.join("scripts/__pycache__")).unwrap();
        fs::write(root.join("scripts/__pycache__/fixture.pyc"), b"code").unwrap();
        assert!(verify_and_snapshot(&root, &tree.0.join("snapshots")).is_err());
    }

    #[cfg(unix)]
    #[test]
    fn symlink_fails_closed() {
        let tree = Tree::new("symlink");
        let root = fixture(&tree);
        let source = root.join("scripts/fixture.py");
        fs::remove_file(&source).unwrap();
        std::os::unix::fs::symlink("../tobkiri_protocol/fixture.py", &source).unwrap();
        assert!(verify_and_snapshot(&root, &tree.0.join("snapshots")).is_err());
    }

    #[cfg(unix)]
    #[test]
    fn hardlink_fails_closed() {
        let tree = Tree::new("hardlink");
        let root = fixture(&tree);
        let source = root.join("scripts/fixture.py");
        let outside = tree.0.join("outside");
        fs::rename(&source, &outside).unwrap();
        fs::hard_link(&outside, &source).unwrap();
        assert!(verify_and_snapshot(&root, &tree.0.join("snapshots")).is_err());
    }

    #[test]
    fn unknown_manifest_marker_fails_before_source_can_execute() {
        let tree = Tree::new("marker");
        let root = fixture(&tree);
        fs::write(
            root.join("scripts/__init__.py"),
            b"raise SystemExit('EXECUTED')\n",
        )
        .unwrap();
        let manifest_path = root.join("packaged_defaultspack_source_manifest.v1.json");
        let mut manifest: Value =
            serde_json::from_slice(&fs::read(&manifest_path).unwrap()).unwrap();
        manifest["execute_verifier"] = Value::Bool(true);
        fs::write(&manifest_path, serde_json::to_vec(&manifest).unwrap()).unwrap();
        assert!(verify_and_snapshot(&root, &tree.0.join("snapshots")).is_err());
        assert!(!tree.0.join("EXECUTED").exists());
    }

    #[test]
    fn working_manifest_must_match_trusted_git_authority() {
        let tree = Tree::new("manifest-authority");
        let root = fixture(&tree);
        let manifest_path = root.join("packaged_defaultspack_source_manifest.v1.json");
        let trusted = fs::read(&manifest_path).unwrap();
        let mut tampered: Value = serde_json::from_slice(&trusted).unwrap();
        tampered["files"][0]["sha256"] = Value::String("0".repeat(64));
        fs::write(manifest_path, serde_json::to_vec(&tampered).unwrap()).unwrap();
        let error =
            verify_and_snapshot_against_manifest(&root, &tree.0.join("snapshots"), &trusted)
                .unwrap_err();
        assert!(error.to_string().contains("trusted authority"));
    }

    #[test]
    fn file_swap_fails_closed() {
        let tree = Tree::new("file-swap");
        let root = fixture(&tree);
        let swapped = root.join("scripts/fixture.py");
        let manifest =
            read_manifest(&root.join("packaged_defaultspack_source_manifest.v1.json")).unwrap();
        let error = verify_and_snapshot_against_manifest_with_hook(
            &root,
            &tree.0.join("snapshots"),
            &manifest,
            || fs::write(&swapped, b"swapped\n").unwrap(),
        )
        .unwrap_err();
        assert_eq!(error.kind(), io::ErrorKind::InvalidData);
        assert!(fs::read_dir(tree.0.join("snapshots"))
            .unwrap()
            .all(|entry| !entry
                .unwrap()
                .file_name()
                .to_string_lossy()
                .starts_with("packaged-source-snapshot-")));
    }

    #[test]
    fn root_swap_fails_closed() {
        let tree = Tree::new("root-swap");
        let root = fixture(&tree);
        let moved = tree.0.join("moved-runtime");
        let replacement = tree.0.join("runtime");
        let manifest =
            read_manifest(&root.join("packaged_defaultspack_source_manifest.v1.json")).unwrap();
        let error = verify_and_snapshot_against_manifest_with_hook(
            &root,
            &tree.0.join("snapshots"),
            &manifest,
            || {
                fs::rename(&root, &moved).unwrap();
                fs::create_dir(&replacement).unwrap();
            },
        )
        .unwrap_err();
        assert!(error.to_string().contains("source") || error.kind() == io::ErrorKind::NotFound);
    }

    #[cfg(unix)]
    #[test]
    fn umask_zero_still_produces_private_sealed_snapshot() {
        use std::os::unix::fs::PermissionsExt;
        use std::sync::Mutex;

        static UMASK_LOCK: Mutex<()> = Mutex::new(());
        let _lock = UMASK_LOCK.lock().unwrap();
        let previous = unsafe { libc::umask(0) };
        struct Restore(libc::mode_t);
        impl Drop for Restore {
            fn drop(&mut self) {
                unsafe { libc::umask(self.0) };
            }
        }
        let _restore = Restore(previous);
        let tree = Tree::new("umask-zero");
        let root = fixture(&tree);
        let snapshot = verify_and_snapshot(&root, &tree.0).unwrap();
        assert_eq!(
            fs::metadata(&snapshot.owner).unwrap().permissions().mode() & 0o777,
            0o700
        );
        assert_eq!(
            fs::metadata(snapshot.root()).unwrap().permissions().mode() & 0o777,
            0o500
        );
        assert_eq!(
            fs::metadata(snapshot.root().join("scripts"))
                .unwrap()
                .permissions()
                .mode()
                & 0o777,
            0o500
        );
    }

    #[cfg(unix)]
    #[test]
    fn postverify_replace_and_extra_are_detected() {
        use std::os::unix::fs::PermissionsExt;

        for mutation in ["replace", "extra"] {
            let tree = Tree::new(mutation);
            let root = fixture(&tree);
            let snapshot = verify_and_snapshot(&root, &tree.0).unwrap();
            let scripts = snapshot.root().join("scripts");
            fs::set_permissions(&scripts, fs::Permissions::from_mode(0o700)).unwrap();
            if mutation == "replace" {
                fs::remove_file(scripts.join("fixture.py")).unwrap();
                fs::write(scripts.join("fixture.py"), b"replacement\n").unwrap();
            } else {
                fs::write(scripts.join("extra.pyc"), b"extra").unwrap();
            }
            assert!(snapshot.verify_unchanged().is_err());
        }
    }

    #[test]
    fn failed_child_is_followed_by_explicit_snapshot_cleanup() {
        let tree = Tree::new("spawn-cleanup");
        let root = fixture(&tree);
        let snapshot = verify_and_snapshot(&root, &tree.0).unwrap();
        let owner = snapshot.owner.clone();
        let python = super::super::packaging_toolchain::verified_tool("python").unwrap();
        let status = super::super::isolated_python_module_command(
            &python,
            snapshot.root(),
            "scripts.module_that_does_not_exist",
        )
        .unwrap()
        .status()
        .unwrap();
        assert!(!status.success());
        snapshot.cleanup().unwrap();
        assert!(!owner.exists());
    }

    #[test]
    fn cleanup_refuses_root_swap_and_preserves_replacement() {
        let tree = Tree::new("cleanup-root-swap");
        let root = fixture(&tree);
        let snapshot = verify_and_snapshot(&root, &tree.0).unwrap();
        let snapshot_root = snapshot.root.clone();
        let moved = snapshot.owner.join("original-source");
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            fs::set_permissions(&snapshot.owner, fs::Permissions::from_mode(0o700)).unwrap();
            fs::set_permissions(&snapshot_root, fs::Permissions::from_mode(0o700)).unwrap();
        }
        fs::rename(&snapshot_root, &moved).unwrap();
        fs::create_dir(&snapshot_root).unwrap();
        fs::write(snapshot_root.join("replacement"), b"preserve").unwrap();
        let error = snapshot.cleanup().unwrap_err();
        assert!(error.to_string().contains("refusing"));
        assert_eq!(
            fs::read(snapshot_root.join("replacement")).unwrap(),
            b"preserve"
        );
    }
}
