//! Python environment bootstrap via **uv**.
//!
//! Flow:
//! 1. Ensure a trusted `uv` binary is available (bundled/dev/PATH only)
//! 2. `uv python install 3.13.13`      (into a temp dir, then rename)
//! 3. `uv venv`                         (create virtual-environment)
//! 4. `uv pip install -r requirements.txt`
//!
//! Each step is idempotent — if the artefact already exists the step is
//! skipped.

use std::collections::hash_map::DefaultHasher;
use std::fs;
use std::hash::{Hash, Hasher};
use std::io;
use std::path::{Path, PathBuf};

use anyhow::{bail, Context, Result};
use log::{info, warn};

use crate::config::AppConfig;
use crate::process_utils;

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

/// Pinned CPython patch version. Avoid resolving a mutable latest patch at startup.
const PYTHON_VERSION: &str = "3.13.13";
const PYTHON_MINOR: &str = "3.13";

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/// Ensure that a working Python venv with all dependencies is present.
///
/// Steps (each is idempotent):
/// 1. Ensure uv binary        → bundled/dev/PATH only
/// 2. uv python install 3.13.13 → `config.python_dir`
/// 3. uv venv                 → `config.venv_dir`
/// 4. uv pip install           → into the venv
pub fn ensure_python_env(config: &AppConfig) -> Result<()> {
    ensure_uv(config).context("uv setup failed")?;
    ensure_python(config).context("Python setup failed")?;
    ensure_venv(config).context("venv creation failed")?;
    install_requirements(config).context("pip install failed")?;
    Ok(())
}

// ---------------------------------------------------------------------------
// Step 1 — uv binary
// ---------------------------------------------------------------------------

fn trusted_uv_path(config: &AppConfig) -> Result<PathBuf> {
    config.trusted_uv_path().with_context(|| {
        format!(
            "no trusted uv binary found; bundle {} with the app, set RUMI_UV_PATH to a user-managed uv binary, or install uv on PATH",
            config.bundled_uv_path().display()
        )
    })
}

fn ensure_uv(config: &AppConfig) -> Result<()> {
    let uv = trusted_uv_path(config)?;
    info!("Using trusted uv at {}", uv.display());
    Ok(())
}

// ---------------------------------------------------------------------------
// Step 2 — Python via `uv python install`
// ---------------------------------------------------------------------------

fn ensure_python(config: &AppConfig) -> Result<()> {
    let python_bin = config.python_bin();
    if python_bin.exists() {
        info!("Python already present at {}", python_bin.display());
        return Ok(());
    }

    if path_exists_or_reparse_point(&config.python_dir) {
        info!(
            "Python directory exists but {} is missing; recreating Python",
            python_bin.display()
        );
        remove_path_or_reparse_point(&config.python_dir).with_context(|| {
            format!(
                "failed to remove incomplete Python directory at {}",
                config.python_dir.display()
            )
        })?;
    }

    info!("Installing Python {PYTHON_VERSION} via uv ...");
    let uv = trusted_uv_path(config)?;

    // Install into a temporary directory under app_data_dir (writable),
    // then move the versioned sub-directory to `config.python_dir`.
    let tmp_dir = config.python_dir.with_file_name("_python_tmp");
    if path_exists_or_reparse_point(&tmp_dir) {
        remove_path_or_reparse_point(&tmp_dir)?;
    }
    fs::create_dir_all(&tmp_dir)?;

    let status = process_utils::command(&uv)
        .args([
            "python",
            "install",
            PYTHON_VERSION,
            "--install-dir",
            &tmp_dir.to_string_lossy(),
        ])
        .status()
        .context("failed to run uv python install")?;

    if !status.success() {
        remove_path_or_reparse_point(&tmp_dir).ok();
        bail!("uv python install exited with {status}");
    }

    // `uv python install --install-dir {tmp}` creates a versioned directory
    // like `cpython-3.13.13-windows-x86_64-none/` and may also create a
    // minor-version alias like `cpython-3.13-windows-x86_64-none`. On Windows
    // that alias is a junction to the versioned directory, so moving it out of
    // the temp dir would leave a broken junction after the temp dir is removed.
    let extracted = find_installed_python_dir(&tmp_dir)?;

    if path_exists_or_reparse_point(&config.python_dir) {
        remove_path_or_reparse_point(&config.python_dir)?;
    }
    fs::rename(&extracted, &config.python_dir)?;
    remove_path_or_reparse_point(&tmp_dir).ok();

    info!("Python installed at {}", config.python_dir.display());
    Ok(())
}

fn path_exists_or_reparse_point(path: &Path) -> bool {
    path.exists() || fs::symlink_metadata(path).is_ok()
}

fn remove_path_or_reparse_point(path: &Path) -> Result<()> {
    let metadata = fs::symlink_metadata(path)
        .with_context(|| format!("failed to inspect {}", path.display()))?;
    if metadata_is_removable_link(path, &metadata) {
        if metadata_is_directory_like(&metadata) {
            remove_reparse_dir(path)
        } else {
            fs::remove_file(path)
        }
    } else if metadata.is_dir() {
        remove_dir_all_reparse_safe(path)
    } else {
        fs::remove_file(path)
    }
    .with_context(|| format!("failed to remove {}", path.display()))
}

fn remove_dir_all_reparse_safe(path: &Path) -> io::Result<()> {
    for entry in fs::read_dir(path)? {
        let entry = entry?;
        let child_path = entry.path();
        let child_metadata = fs::symlink_metadata(&child_path)?;
        if metadata_is_removable_link(&child_path, &child_metadata) {
            if metadata_is_directory_like(&child_metadata) {
                remove_reparse_dir(&child_path)?;
            } else {
                fs::remove_file(&child_path)?;
            }
        } else if child_metadata.is_dir() {
            remove_dir_all_reparse_safe(&child_path)?;
        } else {
            fs::remove_file(&child_path)?;
        }
    }
    fs::remove_dir(path)
}

fn remove_reparse_dir(path: &Path) -> io::Result<()> {
    match fs::remove_dir(path) {
        Ok(()) => Ok(()),
        Err(first_error) => {
            #[cfg(windows)]
            {
                let status = process_utils::command("cmd")
                    .args(["/C", "rmdir", &path.to_string_lossy()])
                    .status();
                if status.is_ok_and(|status| status.success()) {
                    return Ok(());
                }
            }
            Err(first_error)
        }
    }
}

fn metadata_is_removable_link(path: &Path, metadata: &fs::Metadata) -> bool {
    metadata.file_type().is_symlink()
        || metadata_is_reparse_point(metadata)
        || (metadata.is_dir() && !path.exists())
}

fn metadata_is_directory_like(metadata: &fs::Metadata) -> bool {
    #[cfg(windows)]
    {
        use std::os::windows::fs::MetadataExt;
        const FILE_ATTRIBUTE_DIRECTORY: u32 = 0x10;
        metadata.file_attributes() & FILE_ATTRIBUTE_DIRECTORY != 0
    }

    #[cfg(not(windows))]
    {
        metadata.is_dir()
    }
}

fn metadata_is_reparse_point(metadata: &fs::Metadata) -> bool {
    #[cfg(windows)]
    {
        use std::os::windows::fs::MetadataExt;
        const FILE_ATTRIBUTE_REPARSE_POINT: u32 = 0x400;
        metadata.file_attributes() & FILE_ATTRIBUTE_REPARSE_POINT != 0
    }

    #[cfg(not(windows))]
    {
        let _ = metadata;
        false
    }
}

fn python_bin_under(root: &Path) -> PathBuf {
    if cfg!(target_os = "windows") {
        root.join("python.exe")
    } else {
        root.join("bin").join("python3")
    }
}

fn find_installed_python_dir(tmp_dir: &Path) -> Result<PathBuf> {
    let prefix = format!("cpython-{PYTHON_MINOR}");
    let versioned_prefix = format!("cpython-{PYTHON_MINOR}.");
    let mut candidates: Vec<PathBuf> = fs::read_dir(tmp_dir)?
        .filter_map(|entry| entry.ok())
        .filter_map(|entry| {
            let name = entry.file_name().to_string_lossy().into_owned();
            if !name.starts_with(&prefix) {
                return None;
            }
            let path = entry.path();
            python_bin_under(&path).exists().then_some(path)
        })
        .collect();

    candidates.sort_by(|left, right| {
        let left_name = left
            .file_name()
            .and_then(|name| name.to_str())
            .unwrap_or("");
        let right_name = right
            .file_name()
            .and_then(|name| name.to_str())
            .unwrap_or("");
        let left_versioned = left_name.starts_with(&versioned_prefix);
        let right_versioned = right_name.starts_with(&versioned_prefix);
        right_versioned
            .cmp(&left_versioned)
            .then_with(|| right_name.cmp(left_name))
    });

    if let Some(path) = candidates.into_iter().next() {
        return Ok(path);
    }

    let contents: Vec<String> = fs::read_dir(tmp_dir)?
        .filter_map(|entry| {
            entry
                .ok()
                .map(|entry| entry.file_name().to_string_lossy().into_owned())
        })
        .collect();
    remove_path_or_reparse_point(tmp_dir).ok();
    bail!(
        "uv python install succeeded but no usable directory matching \
         `{prefix}*` was found in the install dir.\n\
         Contents of {}: {:?}\n\
         This may indicate a change in uv's directory naming scheme.",
        tmp_dir.display(),
        contents,
    );
}

// ---------------------------------------------------------------------------
// Step 3 — venv
// ---------------------------------------------------------------------------

fn ensure_venv(config: &AppConfig) -> Result<()> {
    let venv_python = config.venv_python();
    if venv_python.exists() {
        info!("venv already present at {}", config.venv_dir.display());
        return Ok(());
    }

    if config.venv_dir.exists() {
        info!(
            "venv directory exists but {} is missing; recreating the venv",
            venv_python.display()
        );
        fs::remove_dir_all(&config.venv_dir)
            .with_context(|| format!("failed to remove {}", config.venv_dir.display()))?;
    }

    info!("Creating venv ...");
    let uv = trusted_uv_path(config)?;
    let python_bin = config.python_bin();
    let status = process_utils::command(&uv)
        .args([
            "venv",
            "--python",
            &python_bin.to_string_lossy(),
            &config.venv_dir.to_string_lossy(),
        ])
        .status()
        .context("failed to run uv venv")?;

    if !status.success() {
        bail!("uv venv exited with {status}");
    }

    info!("venv created at {}", config.venv_dir.display());
    Ok(())
}

// ---------------------------------------------------------------------------
// Step 4 — requirements
// ---------------------------------------------------------------------------

fn compute_requirements_hash(req_path: &Path) -> Result<String> {
    let contents = fs::read_to_string(req_path)
        .with_context(|| format!("failed to read {}", req_path.display()))?;

    let mut hasher = DefaultHasher::new();
    contents.hash(&mut hasher);
    PYTHON_VERSION.hash(&mut hasher);
    let hash = hasher.finish();
    Ok(format!("{:x}", hash))
}

fn validate_hashed_requirements(req_path: &Path) -> Result<()> {
    let contents = fs::read_to_string(req_path)
        .with_context(|| format!("failed to read {}", req_path.display()))?;

    for (line_number, logical_line) in logical_requirement_lines(&contents)? {
        let trimmed = strip_inline_comment(&logical_line).trim();
        if trimmed.is_empty() || trimmed.starts_with('#') {
            continue;
        }
        let tokens: Vec<&str> = trimmed.split_whitespace().collect();
        if tokens.is_empty() {
            continue;
        }
        if tokens[0].starts_with("--") {
            if tokens.as_slice() == ["--only-binary", ":all:"]
                || tokens.as_slice() == ["--only-binary=:all:"]
            {
                continue;
            }
            bail!(
                "{}:{} contains unsupported pip option {trimmed:?}; automatic installation only permits --only-binary :all:",
                req_path.display(),
                line_number
            );
        }

        validate_requirement_tokens(req_path, line_number, &tokens)?;
    }

    Ok(())
}

fn logical_requirement_lines(contents: &str) -> Result<Vec<(usize, String)>> {
    let mut result = Vec::new();
    let mut current = String::new();
    let mut start_line = 0usize;

    for (index, line) in contents.lines().enumerate() {
        let line_number = index + 1;
        let trimmed = line.trim();
        if current.is_empty() && (trimmed.is_empty() || trimmed.starts_with('#')) {
            continue;
        }

        if current.is_empty() {
            start_line = line_number;
        } else {
            current.push(' ');
        }

        let continued = trimmed.ends_with('\\');
        let segment = if continued {
            trimmed.trim_end_matches('\\').trim_end()
        } else {
            trimmed
        };
        current.push_str(segment);

        if !continued {
            result.push((start_line, current.trim().to_string()));
            current.clear();
        }
    }

    if !current.trim().is_empty() {
        bail!(
            "requirements.txt:{} has an unterminated line continuation",
            start_line
        );
    }

    Ok(result)
}

fn strip_inline_comment(line: &str) -> &str {
    line.find(" #").map_or(line, |index| &line[..index])
}

fn validate_requirement_tokens(req_path: &Path, line_number: usize, tokens: &[&str]) -> Result<()> {
    let package = tokens.first().copied().unwrap_or_default();
    if !is_exact_package_pin(package) {
        bail!(
            "{}:{} must start with an exact name==version package pin before automatic installation",
            req_path.display(),
            line_number
        );
    }

    let hash_start = if tokens.get(1) == Some(&";") {
        let hash_start = tokens
            .iter()
            .position(|token| token.starts_with("--hash=sha256:"))
            .unwrap_or(tokens.len());
        let marker = tokens.get(1..hash_start).unwrap_or_default();
        if !is_supported_environment_marker(marker) {
            bail!(
                "{}:{} contains an unsupported environment marker; automatic installation only permits safe interpreter-version or implementation comparisons joined by 'and'",
                req_path.display(),
                line_number
            );
        }
        hash_start
    } else {
        1
    };

    let mut hash_count = 0usize;
    for token in &tokens[hash_start..] {
        if !token.starts_with("--hash=sha256:") {
            bail!(
                "{}:{} contains unsupported requirement token {token:?}; only --hash=sha256:<64hex> is permitted after the package pin",
                req_path.display(),
                line_number
            );
        }
        let digest = token.trim_start_matches("--hash=sha256:");
        if !is_sha256_hex(digest) {
            bail!(
                "{}:{} contains an invalid SHA-256 hash {digest:?}",
                req_path.display(),
                line_number
            );
        }
        hash_count += 1;
    }

    if hash_count == 0 {
        bail!(
            "{}:{} must include at least one SHA-256 hash before automatic installation",
            req_path.display(),
            line_number
        );
    }

    Ok(())
}

fn is_supported_environment_marker(tokens: &[&str]) -> bool {
    if tokens.first() != Some(&";") {
        return false;
    }
    let mut index = 1usize;
    while index < tokens.len() {
        let Some(variable) = tokens.get(index) else {
            return false;
        };
        if !matches!(
            *variable,
            "python_version"
                | "python_full_version"
                | "platform_python_implementation"
                | "implementation_name"
        ) {
            return false;
        }
        let Some(operator) = tokens.get(index + 1) else {
            return false;
        };
        if !matches!(*operator, "<" | "<=" | "==" | "!=" | ">=" | ">") {
            return false;
        }
        let Some(quoted_value) = tokens.get(index + 2) else {
            return false;
        };
        if !is_safe_quoted_marker_value(quoted_value) {
            return false;
        }
        index += 3;
        if index == tokens.len() {
            return true;
        }
        if tokens.get(index) != Some(&"and") {
            return false;
        }
        index += 1;
    }
    false
}

fn is_safe_quoted_marker_value(value: &str) -> bool {
    if value.len() < 3 {
        return false;
    }
    let quote = value.as_bytes()[0];
    if !matches!(quote, b'\'' | b'"') || value.as_bytes().last() != Some(&quote) {
        return false;
    }
    let inner = &value[1..value.len() - 1];
    !inner.is_empty()
        && inner
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'.' | b'_' | b'+' | b'-'))
}

fn is_exact_package_pin(token: &str) -> bool {
    let Some((name, version)) = token.split_once("==") else {
        return false;
    };
    !name.is_empty()
        && !version.is_empty()
        && is_valid_package_name(name)
        && is_valid_version_token(version)
}

fn is_valid_package_name(name: &str) -> bool {
    name.as_bytes()
        .iter()
        .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'.' | b'_' | b'-'))
}

fn is_valid_version_token(version: &str) -> bool {
    version.as_bytes().iter().all(|byte| {
        byte.is_ascii_alphanumeric() || matches!(byte, b'.' | b'_' | b'!' | b'+' | b'-')
    })
}

fn is_sha256_hex(value: &str) -> bool {
    value.len() == 64 && value.as_bytes().iter().all(|byte| byte.is_ascii_hexdigit())
}

fn install_requirements(config: &AppConfig) -> Result<()> {
    let req_path = config.requirements_txt();
    if !req_path.exists() {
        info!("No requirements.txt found, skipping pip install");
        return Ok(());
    }

    validate_hashed_requirements(&req_path)?;

    let stamp_path = config.venv_dir.join(".rumi_requirements_stamp");
    let venv_python = config.venv_python();

    // If venv Python exists and stamp matches, skip installation.
    if venv_python.exists() && stamp_path.exists() {
        let stamp_content = fs::read_to_string(&stamp_path).unwrap_or_default();
        match compute_requirements_hash(&req_path) {
            Ok(current_hash) => {
                if stamp_content.trim() == current_hash {
                    info!("Requirements stamp matches, skipping pip install");
                    return Ok(());
                }
                info!("Requirements stamp mismatch, re-installing dependencies");
            }
            Err(e) => {
                warn!("Failed to compute requirements hash: {e}, re-installing");
            }
        }
    }

    info!("Installing requirements ...");
    let uv = trusted_uv_path(config)?;
    let status = process_utils::command(&uv)
        .args([
            "pip",
            "install",
            "--require-hashes",
            "--only-binary",
            ":all:",
            "--python",
            &venv_python.to_string_lossy(),
            "-r",
            &req_path.to_string_lossy(),
        ])
        .status()
        .context("failed to run uv pip install")?;

    if !status.success() {
        bail!("uv pip install exited with {status}");
    }

    // Write stamp after successful installation.
    match compute_requirements_hash(&req_path) {
        Ok(hash) => {
            if let Err(e) = fs::write(&stamp_path, hash) {
                warn!("Failed to write requirements stamp: {e}");
            }
        }
        Err(e) => {
            warn!("Failed to compute requirements hash after install: {e}");
        }
    }

    info!("Requirements installed");
    Ok(())
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;
    use std::time::{SystemTime, UNIX_EPOCH};

    #[test]
    fn ensure_uv_fails_closed_without_trusted_uv() {
        let unique = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let root = std::env::temp_dir().join(format!("rumi_no_trusted_uv_{unique}"));
        let config =
            AppConfig::detect_for_tauri(root.join("resources"), root.join("appdata")).unwrap();

        let old_path = std::env::var_os("PATH");
        let old_uv_path = std::env::var_os("RUMI_UV_PATH");
        std::env::set_var("PATH", "");
        std::env::remove_var("RUMI_UV_PATH");
        let err = ensure_uv(&config).unwrap_err().to_string();
        if let Some(path) = old_path {
            std::env::set_var("PATH", path);
        } else {
            std::env::remove_var("PATH");
        }
        if let Some(path) = old_uv_path {
            std::env::set_var("RUMI_UV_PATH", path);
        } else {
            std::env::remove_var("RUMI_UV_PATH");
        }

        assert!(err.contains("no trusted uv binary found"));
        fs::remove_dir_all(root).ok();
    }

    #[test]
    fn validate_hashed_requirements_rejects_unpinned_lines() {
        let unique = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let root = std::env::temp_dir().join(format!("rumi_unhashed_requirements_{unique}"));
        let req_path = root.join("requirements.txt");
        fs::create_dir_all(&root).unwrap();
        fs::write(&req_path, format!("pyyaml{}6.0\n", ">=")).unwrap();

        let err = validate_hashed_requirements(&req_path)
            .unwrap_err()
            .to_string();

        assert!(err.contains("must start with an exact name==version package pin"));
        fs::remove_dir_all(root).ok();
    }

    #[test]
    fn validate_hashed_requirements_accepts_pinned_hashes() {
        let unique = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let root = std::env::temp_dir().join(format!("rumi_hashed_requirements_{unique}"));
        let req_path = root.join("requirements.txt");
        fs::create_dir_all(&root).unwrap();
        fs::write(
            &req_path,
            "--only-binary :all:\npyyaml==6.0.2 --hash=sha256:70b189594dbe54f75ab3a1acec5f1e3faa7e8cf2f1e08d9b561cb41b845f69d5\n",
        )
        .unwrap();

        validate_hashed_requirements(&req_path).unwrap();
        fs::remove_dir_all(root).ok();
    }

    #[test]
    fn validate_hashed_requirements_accepts_continued_multi_hash_lines() {
        let unique = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let root = std::env::temp_dir().join(format!("rumi_multi_hash_requirements_{unique}"));
        let req_path = root.join("requirements.txt");
        fs::create_dir_all(&root).unwrap();
        fs::write(
            &req_path,
            concat!(
                "--only-binary=:all:\n",
                "pyyaml==6.0.2 \\\n",
                "  --hash=sha256:70b189594dbe54f75ab3a1acec5f1e3faa7e8cf2f1e08d9b561cb41b845f69d5 \\\n",
                "  --hash=sha256:8388ee1976c416731879ac16da0aff3f63b286ffdd57cdeb95f3f2e085687563\n",
            ),
        )
        .unwrap();

        validate_hashed_requirements(&req_path).unwrap();
        fs::remove_dir_all(root).ok();
    }

    #[test]
    fn validate_hashed_requirements_accepts_python_version_markers() {
        let unique = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let root = std::env::temp_dir().join(format!("rumi_marker_requirements_{unique}"));
        let req_path = root.join("requirements.txt");
        fs::create_dir_all(&root).unwrap();
        fs::write(
            &req_path,
            concat!(
                "rpds-py==2026.6.3 ; python_version >= \"3.11\" ",
                "--hash=sha256:0be972be84cfcaf46c8c6edf690ca0f154ac17babf1f6a955a51579b34ad2dc5\n",
            ),
        )
        .unwrap();

        validate_hashed_requirements(&req_path).unwrap();
        fs::remove_dir_all(root).ok();
    }

    #[test]
    fn validate_hashed_requirements_accepts_generated_interpreter_markers() {
        let unique = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let root = std::env::temp_dir().join(format!("rumi_generated_marker_{unique}"));
        let req_path = root.join("requirements.txt");
        fs::create_dir_all(&root).unwrap();
        fs::write(
            &req_path,
            concat!(
                "cffi==2.1.0 ; platform_python_implementation != 'PyPy' ",
                "--hash=sha256:02cb7ff33ded4f1532476731f89ede53e2e488a8e6205515a82144246ffa7dcc\n",
                "pycparser==3.0 ; implementation_name != 'PyPy' and ",
                "platform_python_implementation != 'PyPy' ",
                "--hash=sha256:70b189594dbe54f75ab3a1acec5f1e3faa7e8cf2f1e08d9b561cb41b845f69d5\n",
                "rpds-py==2026.6.3 ; python_full_version >= '3.11' ",
                "--hash=sha256:0be972be84cfcaf46c8c6edf690ca0f154ac17babf1f6a955a51579b34ad2dc5\n",
            ),
        )
        .unwrap();

        validate_hashed_requirements(&req_path).unwrap();
        fs::remove_dir_all(root).ok();
    }

    #[test]
    fn bundled_runtime_requirements_pass_launcher_validation() {
        let requirements =
            Path::new(env!("CARGO_MANIFEST_DIR")).join("../../tobkiri_runtime/requirements.txt");
        validate_hashed_requirements(&requirements).unwrap();
    }

    #[test]
    fn validate_hashed_requirements_rejects_arbitrary_environment_markers() {
        let unique = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let root = std::env::temp_dir().join(format!("rumi_bad_marker_requirements_{unique}"));
        let req_path = root.join("requirements.txt");
        fs::create_dir_all(&root).unwrap();
        fs::write(
            &req_path,
            concat!(
                "pyyaml==6.0.2 ; sys_platform == \"darwin\" ",
                "--hash=sha256:70b189594dbe54f75ab3a1acec5f1e3faa7e8cf2f1e08d9b561cb41b845f69d5\n",
            ),
        )
        .unwrap();

        let err = validate_hashed_requirements(&req_path)
            .unwrap_err()
            .to_string();

        assert!(err.contains("unsupported environment marker"));
        fs::remove_dir_all(root).ok();
    }

    #[test]
    fn validate_hashed_requirements_rejects_extra_package_options() {
        let unique = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let root = std::env::temp_dir().join(format!("rumi_extra_option_requirements_{unique}"));
        let req_path = root.join("requirements.txt");
        fs::create_dir_all(&root).unwrap();
        fs::write(
            &req_path,
            concat!(
                "pyyaml==6.0.2 ",
                "--hash=sha256:70b189594dbe54f75ab3a1acec5f1e3faa7e8cf2f1e08d9b561cb41b845f69d5 ",
                "--index-url https://example.invalid/simple\n",
            ),
        )
        .unwrap();

        let err = validate_hashed_requirements(&req_path)
            .unwrap_err()
            .to_string();

        assert!(err.contains("unsupported requirement token"));
        fs::remove_dir_all(root).ok();
    }

    #[test]
    fn validate_hashed_requirements_rejects_invalid_hashes() {
        let unique = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let root = std::env::temp_dir().join(format!("rumi_bad_hash_requirements_{unique}"));
        let req_path = root.join("requirements.txt");
        fs::create_dir_all(&root).unwrap();
        fs::write(&req_path, "pyyaml==6.0.2 --hash=sha256:not-a-real-hash\n").unwrap();

        let err = validate_hashed_requirements(&req_path)
            .unwrap_err()
            .to_string();

        assert!(err.contains("invalid SHA-256 hash"));
        fs::remove_dir_all(root).ok();
    }

    #[test]
    fn validate_hashed_requirements_rejects_source_build_options() {
        let unique = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let root = std::env::temp_dir().join(format!("rumi_source_build_requirements_{unique}"));
        let req_path = root.join("requirements.txt");
        fs::create_dir_all(&root).unwrap();
        fs::write(
            &req_path,
            "--no-binary :all:\npyyaml==6.0.2 --hash=sha256:70b189594dbe54f75ab3a1acec5f1e3faa7e8cf2f1e08d9b561cb41b845f69d5\n",
        )
        .unwrap();

        let err = validate_hashed_requirements(&req_path)
            .unwrap_err()
            .to_string();

        assert!(err.contains("unsupported pip option"));
        fs::remove_dir_all(root).ok();
    }

    #[test]
    fn python_install_dir_prefers_patch_version_over_minor_alias() {
        let unique = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let root = std::env::temp_dir().join(format!("rumi_python_install_dir_{unique}"));
        let alias = root.join("cpython-3.13-windows-x86_64-none");
        let patch = root.join("cpython-3.13.13-windows-x86_64-none");

        fs::create_dir_all(python_bin_under(&alias).parent().unwrap()).unwrap();
        fs::create_dir_all(python_bin_under(&patch).parent().unwrap()).unwrap();
        fs::write(python_bin_under(&alias), b"alias").unwrap();
        fs::write(python_bin_under(&patch), b"patch").unwrap();

        let selected = find_installed_python_dir(&root).unwrap();

        assert_eq!(selected, patch);
        fs::remove_dir_all(root).ok();
    }

    #[test]
    #[cfg(windows)]
    fn remove_path_handles_broken_junction() {
        let unique = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let root = std::env::temp_dir().join(format!("rumi_broken_junction_{unique}"));
        let target = root.join("target");
        let link = root.join("link");
        fs::create_dir_all(&target).unwrap();

        let status = process_utils::command("cmd")
            .args([
                "/C",
                "mklink",
                "/J",
                &link.to_string_lossy(),
                &target.to_string_lossy(),
            ])
            .status()
            .unwrap();
        assert!(status.success());

        fs::remove_dir_all(&target).unwrap();
        assert!(path_exists_or_reparse_point(&link));

        remove_path_or_reparse_point(&link).unwrap();

        assert!(!path_exists_or_reparse_point(&link));
        fs::remove_dir_all(root).ok();
    }
}
