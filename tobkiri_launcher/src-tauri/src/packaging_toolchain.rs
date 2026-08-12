//! Formal, digest-bound tool inputs for production packaging.
//!
//! Release build code must never resolve Python or Git through PATH, nor
//! trust the ambient PYTHON variable. CI binds these values from a checked
//! toolchain-resolution step; every caller revalidates the absolute file and
//! its raw SHA-256 before spawning it.

use std::env;
use std::fs;
use std::io::{self, Read};
use std::path::{Path, PathBuf};

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

fn hash_regular_executable(path: &Path) -> io::Result<String> {
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
    let mut input = fs::File::open(path)?;
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
    Ok(format!("{:x}", digest.finalize()))
}

fn binding(kind: &str) -> (&'static str, &'static str) {
    match kind {
        "python" => (PYTHON_PATH_ENV, PYTHON_SHA256_ENV),
        "git" => (GIT_PATH_ENV, GIT_SHA256_ENV),
        _ => ("", ""),
    }
}

/// Resolve and verify one formally bound packaging executable.
pub fn verified_tool_executable(kind: &str) -> io::Result<PathBuf> {
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
    verify_tool_binding(kind, &path, &expected)
}

fn verify_tool_binding(kind: &str, path: &Path, expected: &str) -> io::Result<PathBuf> {
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
    let actual = hash_regular_executable(path)?;
    if actual != expected {
        return Err(invalid(format!(
            "{kind} executable digest mismatch: expected {expected}, got {actual}"
        )));
    }
    Ok(path.to_path_buf())
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
}
