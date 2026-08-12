//! Formal, digest-bound tool inputs for production packaging.
//!
//! Release build code must never resolve Python or Git through PATH, nor
//! trust the ambient PYTHON variable. CI binds these values from a checked
//! toolchain-resolution step; every caller revalidates the absolute file and
//! its raw SHA-256 before spawning it.

use std::env;
use std::fs::{self, File};
use std::io::{self, Read, Seek, SeekFrom};
use std::path::{Path, PathBuf};
use std::process::Command;

use sha2::{Digest, Sha256};

pub const PYTHON_PATH_ENV: &str = "TOBKIRI_PACKAGING_PYTHON";
pub const PYTHON_SHA256_ENV: &str = "TOBKIRI_PACKAGING_PYTHON_SHA256";
pub const GIT_PATH_ENV: &str = "TOBKIRI_PACKAGING_GIT";
pub const GIT_SHA256_ENV: &str = "TOBKIRI_PACKAGING_GIT_SHA256";

fn invalid(message: impl Into<String>) -> io::Error {
    io::Error::new(io::ErrorKind::InvalidInput, message.into())
}

fn valid_raw_sha256(value: &str) -> bool {
    value.len() == 64
        && value
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
}

fn file_identity(metadata: &fs::Metadata) -> (u64, u64, u64, u64, u64) {
    #[cfg(unix)]
    {
        use std::os::unix::fs::MetadataExt;

        return (
            metadata.dev(),
            metadata.ino(),
            metadata.len(),
            metadata.mtime_nsec() as u64,
            metadata.ctime_nsec() as u64,
        );
    }
    #[cfg(not(unix))]
    {
        let modified = metadata
            .modified()
            .ok()
            .and_then(|value| value.duration_since(std::time::UNIX_EPOCH).ok())
            .map_or(0, |value| value.as_nanos() as u64);
        let created = metadata
            .created()
            .ok()
            .and_then(|value| value.duration_since(std::time::UNIX_EPOCH).ok())
            .map_or(0, |value| value.as_nanos() as u64);
        (0, 0, metadata.len(), modified, created)
    }
}

fn validate_parent_path(path: &Path) -> io::Result<()> {
    let parent = path
        .parent()
        .ok_or_else(|| invalid("packaging tool has no parent directory"))?;
    let canonical = parent.canonicalize()?;
    if canonical != parent {
        return Err(invalid(format!(
            "packaging tool parent path is not canonical: {}",
            parent.display()
        )));
    }
    let metadata = fs::symlink_metadata(parent)?;
    if metadata.file_type().is_symlink() || !metadata.is_dir() {
        return Err(invalid("packaging tool parent is not a real directory"));
    }
    Ok(())
}

fn open_hashed_regular_executable(path: &Path) -> io::Result<(File, fs::Metadata, String)> {
    validate_parent_path(path)?;
    let before = fs::symlink_metadata(path)?;
    if before.file_type().is_symlink() || !before.is_file() {
        return Err(invalid(format!(
            "packaging tool is not a regular file: {}",
            path.display()
        )));
    }
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;

        let mode = before.permissions().mode();
        if mode & 0o111 == 0 {
            return Err(invalid(format!(
                "packaging tool is not executable: {}",
                path.display()
            )));
        }
        if mode & 0o022 != 0 {
            return Err(invalid(format!(
                "packaging tool is writable: {}",
                path.display()
            )));
        }
    }
    let canonical = path.canonicalize()?;
    if canonical != path {
        return Err(invalid(format!(
            "packaging tool path is not canonical: {}",
            path.display()
        )));
    }
    let mut digest = Sha256::new();
    let mut input = File::open(path)?;
    let opened = input.metadata()?;
    if file_identity(&opened) != file_identity(&before) {
        return Err(invalid(format!(
            "packaging tool changed while opened: {}",
            path.display()
        )));
    }
    let mut buffer = [0_u8; 1024 * 1024];
    loop {
        let count = input.read(&mut buffer)?;
        if count == 0 {
            break;
        }
        digest.update(&buffer[..count]);
    }
    let after = fs::symlink_metadata(path)?;
    if after.file_type().is_symlink()
        || !after.is_file()
        || file_identity(&before) != file_identity(&after)
    {
        return Err(invalid(format!(
            "packaging tool changed while hashed: {}",
            path.display()
        )));
    }
    Ok((input, before, format!("{:x}", digest.finalize())))
}

#[allow(dead_code)]
pub struct VerifiedTool {
    kind: String,
    original_path: PathBuf,
    identity: (u64, u64, u64, u64, u64),
    #[cfg(unix)]
    execution_path: PathBuf,
    #[cfg(unix)]
    execution_identity: (u64, u64, u64, u64, u64),
    #[cfg(unix)]
    owns_execution_copy: bool,
    #[cfg(not(unix))]
    lock: File,
}

impl VerifiedTool {
    pub fn command(&self) -> io::Result<Command> {
        #[cfg(not(unix))]
        {
            let current = fs::symlink_metadata(&self.original_path)?;
            if current.file_type().is_symlink()
                || !current.is_file()
                || file_identity(&current) != self.identity
            {
                return Err(invalid(format!(
                    "{} executable path changed before spawn",
                    self.kind
                )));
            }
        }
        #[cfg(unix)]
        {
            let execution = fs::symlink_metadata(&self.execution_path)?;
            if execution.file_type().is_symlink()
                || !execution.is_file()
                || file_identity(&execution) != self.execution_identity
            {
                return Err(invalid("sealed packaging tool copy was replaced"));
            }
            return Ok(Command::new(&self.execution_path));
        }
        #[cfg(not(unix))]
        {
            let _ = &self.lock;
            Ok(Command::new(&self.original_path))
        }
    }

    #[cfg(test)]
    pub fn original_path(&self) -> &Path {
        &self.original_path
    }
}

impl Drop for VerifiedTool {
    fn drop(&mut self) {
        #[cfg(unix)]
        {
            if self.owns_execution_copy {
                if let Ok(metadata) = fs::symlink_metadata(&self.execution_path) {
                    if metadata.is_file()
                        && !metadata.file_type().is_symlink()
                        && file_identity(&metadata) == self.execution_identity
                    {
                        let _ = fs::remove_file(&self.execution_path);
                    }
                }
            }
        }
    }
}

#[cfg(unix)]
fn sealed_executable_copy(
    mut source: File,
    original: &Path,
    expected: &str,
) -> io::Result<(PathBuf, fs::Metadata, bool)> {
    use std::ffi::CString;
    use std::os::unix::ffi::OsStrExt;
    use std::os::unix::fs::PermissionsExt;
    use std::time::{SystemTime, UNIX_EPOCH};

    let parent = original.parent().unwrap();
    for attempt in 0..128_u32 {
        let nonce = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .map_err(io::Error::other)?
            .as_nanos();
        let name = original
            .file_name()
            .and_then(|name| name.to_str())
            .ok_or_else(|| invalid("packaging tool has no UTF-8 file name"))?;
        let target = parent.join(format!(
            ".{name}.tobkiri-verified-{}-{nonce}-{attempt}",
            std::process::id()
        ));
        match fs::OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&target)
        {
            Ok(mut output) => {
                source.seek(SeekFrom::Start(0))?;
                io::copy(&mut source, &mut output)?;
                output.sync_all()?;
                fs::set_permissions(&target, fs::Permissions::from_mode(0o500))?;
                let metadata = fs::symlink_metadata(&target)?;
                let copied = fs::read(&target)?;
                if format!("{:x}", Sha256::digest(&copied)) != expected {
                    let _ = fs::remove_file(&target);
                    return Err(invalid("sealed packaging tool copy digest mismatch"));
                }
                return Ok((target, metadata, true));
            }
            Err(error) if error.kind() == io::ErrorKind::AlreadyExists => continue,
            Err(error) if error.kind() == io::ErrorKind::PermissionDenied => {
                let path = CString::new(parent.as_os_str().as_bytes())
                    .map_err(|_| invalid("packaging tool parent contains NUL"))?;
                if unsafe { libc::access(path.as_ptr(), libc::W_OK) } == 0 {
                    return Err(invalid(
                        "writable packaging tool parent refused sealed copy",
                    ));
                }
                let executable = CString::new(original.as_os_str().as_bytes())
                    .map_err(|_| invalid("packaging tool path contains NUL"))?;
                if unsafe { libc::access(executable.as_ptr(), libc::W_OK) } == 0 {
                    return Err(invalid(
                        "writable packaging tool cannot be sealed in its protected parent",
                    ));
                }
                let metadata = fs::symlink_metadata(original)?;
                return Ok((original.to_path_buf(), metadata, false));
            }
            Err(error) => return Err(error),
        }
    }
    Err(invalid("could not create sealed packaging tool copy"))
}

#[cfg(windows)]
fn locked_windows_executable(path: &Path, expected: &str) -> io::Result<File> {
    use std::os::windows::ffi::OsStrExt;
    use std::os::windows::io::FromRawHandle;
    use windows_sys::Win32::Foundation::{GENERIC_READ, INVALID_HANDLE_VALUE};
    use windows_sys::Win32::Storage::FileSystem::{
        CreateFileW, FILE_ATTRIBUTE_NORMAL, FILE_FLAG_OPEN_REPARSE_POINT, FILE_SHARE_READ,
        OPEN_EXISTING,
    };

    let wide = path
        .as_os_str()
        .encode_wide()
        .chain(std::iter::once(0))
        .collect::<Vec<_>>();
    let handle = unsafe {
        CreateFileW(
            wide.as_ptr(),
            GENERIC_READ,
            FILE_SHARE_READ,
            std::ptr::null(),
            OPEN_EXISTING,
            FILE_ATTRIBUTE_NORMAL | FILE_FLAG_OPEN_REPARSE_POINT,
            std::ptr::null_mut(),
        )
    };
    if handle == INVALID_HANDLE_VALUE {
        return Err(io::Error::last_os_error());
    }
    let mut file = unsafe { File::from_raw_handle(handle) };
    let mut digest = Sha256::new();
    let mut buffer = [0_u8; 1024 * 1024];
    loop {
        let count = file.read(&mut buffer)?;
        if count == 0 {
            break;
        }
        digest.update(&buffer[..count]);
    }
    file.seek(SeekFrom::Start(0))?;
    if format!("{:x}", digest.finalize()) != expected {
        return Err(invalid(
            "packaging tool changed before Windows lock acquisition",
        ));
    }
    Ok(file)
}

fn binding(kind: &str) -> (&'static str, &'static str) {
    match kind {
        "python" => (PYTHON_PATH_ENV, PYTHON_SHA256_ENV),
        "git" => (GIT_PATH_ENV, GIT_SHA256_ENV),
        _ => ("", ""),
    }
}

/// Resolve and verify one formally bound packaging executable.
pub fn verified_tool(kind: &str) -> io::Result<VerifiedTool> {
    let (path_key, digest_key) = binding(kind);
    if path_key.is_empty() {
        return Err(invalid(format!("unknown packaging tool: {kind}")));
    }
    let raw_path = env::var_os(path_key)
        .ok_or_else(|| invalid(format!("{path_key} is required; PATH lookup is forbidden")))?;
    let path = PathBuf::from(raw_path);
    if !path.is_absolute() {
        return Err(invalid(format!("{path_key} must be an absolute path")));
    }
    let expected = env::var(digest_key)
        .map_err(|_| invalid(format!("{digest_key} is required for {path_key}")))?;
    if !valid_raw_sha256(&expected) {
        return Err(invalid(format!(
            "{digest_key} must be lowercase raw SHA-256"
        )));
    }
    verify_tool_binding_guard(kind, &path, &expected)
}

#[cfg(test)]
pub fn verified_tool_executable(kind: &str) -> io::Result<PathBuf> {
    Ok(verified_tool(kind)?.original_path().to_path_buf())
}

#[cfg(test)]
fn verify_tool_binding(kind: &str, path: &Path, expected: &str) -> io::Result<PathBuf> {
    Ok(verify_tool_binding_guard(kind, path, expected)?
        .original_path()
        .to_path_buf())
}

fn verify_tool_binding_guard(kind: &str, path: &Path, expected: &str) -> io::Result<VerifiedTool> {
    let (_, digest_key) = binding(kind);
    if digest_key.is_empty() {
        return Err(invalid(format!("unknown packaging tool: {kind}")));
    }
    if !path.is_absolute() {
        return Err(invalid(format!("{kind} executable path must be absolute")));
    }
    if !valid_raw_sha256(expected) {
        return Err(invalid(format!(
            "{digest_key} must be lowercase raw SHA-256"
        )));
    }
    let (file, metadata, actual) = open_hashed_regular_executable(path)?;
    if actual != expected {
        return Err(invalid(format!(
            "{kind} executable digest mismatch: expected {expected}, got {actual}"
        )));
    }
    #[cfg(unix)]
    let (execution_path, execution_metadata, owns_execution_copy) =
        sealed_executable_copy(file, path, expected)?;
    #[cfg(windows)]
    let locked_file = {
        drop(file);
        locked_windows_executable(path, expected)?
    };
    #[cfg(all(not(unix), not(windows)))]
    let locked_file = file;
    Ok(VerifiedTool {
        kind: kind.to_owned(),
        original_path: path.to_path_buf(),
        identity: file_identity(&metadata),
        #[cfg(unix)]
        execution_path,
        #[cfg(unix)]
        execution_identity: file_identity(&execution_metadata),
        #[cfg(unix)]
        owns_execution_copy,
        #[cfg(not(unix))]
        lock: locked_file,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::time::{SystemTime, UNIX_EPOCH};

    struct TestFile {
        path: PathBuf,
    }

    impl TestFile {
        fn new(label: &str, payload: &[u8]) -> Self {
            let nonce = SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .expect("system clock should be valid")
                .as_nanos();
            let root = env::temp_dir()
                .canonicalize()
                .expect("system temporary directory should canonicalize")
                .join(format!(
                    "tobkiri-packaging-tool-{label}-{}-{nonce}",
                    std::process::id()
                ));
            fs::create_dir_all(&root).expect("tool fixture root should be creatable");
            let path = root.join("tool");
            fs::write(&path, payload).expect("tool fixture should be writable");
            #[cfg(unix)]
            {
                use std::os::unix::fs::PermissionsExt;

                fs::set_permissions(&path, fs::Permissions::from_mode(0o555))
                    .expect("tool fixture should be executable");
            }
            Self { path }
        }

        fn digest(&self) -> String {
            format!(
                "{:x}",
                Sha256::digest(fs::read(&self.path).expect("tool fixture should be readable"))
            )
        }
    }

    impl Drop for TestFile {
        fn drop(&mut self) {
            if let Some(root) = self.path.parent() {
                let _ = fs::remove_dir_all(root);
            }
        }
    }

    #[test]
    fn missing_and_nonabsolute_bindings_fail_before_any_spawn() {
        let missing = verify_tool_binding("python", Path::new("/missing"), "")
            .expect_err("missing digest input must fail");
        assert!(missing.to_string().contains(PYTHON_SHA256_ENV));

        let relative = verify_tool_binding("python", Path::new("python"), &"0".repeat(64))
            .expect_err("relative input must fail");
        assert!(relative.to_string().contains("absolute"));
    }

    #[test]
    fn fake_path_tools_are_never_selected_or_executed() {
        let fake = TestFile::new(
            "fake-path",
            b"#!/bin/sh\nprintf executed > \"$TOBKIRI_FAKE_MARKER\"\n",
        );
        let marker = fake.path.with_file_name("marker");
        let error = verify_tool_binding("python", &fake.path, &"0".repeat(64))
            .expect_err("fake tool digest must fail");
        assert!(error.to_string().contains("digest mismatch"));
        assert!(!marker.exists(), "untrusted PATH executable was spawned");
    }

    #[test]
    fn mismatch_and_tamper_fail_closed_after_exact_binding() {
        let tool = TestFile::new("tamper", b"trusted fixture executable");
        let mismatch = verify_tool_binding("python", &tool.path, &"0".repeat(64))
            .expect_err("digest mismatch must fail");
        assert!(mismatch.to_string().contains("digest mismatch"));

        let expected = tool.digest();
        assert_eq!(
            verify_tool_binding("python", &tool.path, &expected)
                .expect("exact tool identity should pass"),
            tool.path
        );
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;

            fs::set_permissions(&tool.path, fs::Permissions::from_mode(0o755))
                .expect("fixture should become writable");
        }
        fs::write(&tool.path, b"tampered fixture executable")
            .expect("fixture tamper should be writable");
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;

            fs::set_permissions(&tool.path, fs::Permissions::from_mode(0o555))
                .expect("fixture should become immutable again");
        }
        let tampered =
            verify_tool_binding("python", &tool.path, &expected).expect_err("tamper must fail");
        assert!(tampered.to_string().contains("digest mismatch"));
    }

    #[cfg(unix)]
    #[test]
    fn replaced_python_and_git_paths_never_execute_replacement() {
        use std::os::unix::fs::PermissionsExt;

        for kind in ["python", "git"] {
            let tool = TestFile::new(
                &format!("{kind}-replace"),
                b"#!/bin/sh\nprintf trusted > \"$TOBKIRI_TRUSTED_MARKER\"\n",
            );
            let trusted_marker = tool.path.with_file_name(format!("{kind}-trusted"));
            let evil_marker = tool.path.with_file_name(format!("{kind}-evil"));
            let guard = verify_tool_binding_guard(kind, &tool.path, &tool.digest()).unwrap();
            fs::remove_file(&tool.path).unwrap();
            fs::write(
                &tool.path,
                b"#!/bin/sh\nprintf evil > \"$TOBKIRI_EVIL_MARKER\"\n",
            )
            .unwrap();
            fs::set_permissions(&tool.path, fs::Permissions::from_mode(0o555)).unwrap();
            let status = guard
                .command()
                .unwrap()
                .env("TOBKIRI_TRUSTED_MARKER", &trusted_marker)
                .env("TOBKIRI_EVIL_MARKER", &evil_marker)
                .status()
                .unwrap();
            assert!(status.success());
            assert!(trusted_marker.exists(), "trusted {kind} bytes must execute");
            assert!(
                !evil_marker.exists(),
                "replacement {kind} must never execute"
            );
        }
    }

    #[test]
    fn bound_real_python_and_git_remain_executable() {
        for (kind, argument) in [("python", "--version"), ("git", "--version")] {
            let tool = verified_tool(kind).unwrap();
            let output = tool.command().unwrap().arg(argument).output().unwrap();
            assert!(
                output.status.success(),
                "sealed {kind} must remain compatible"
            );
        }
    }
}
