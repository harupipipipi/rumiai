//! Python environment bootstrap via **uv**.
//!
//! Flow:
//! 1. Ensure `uv` binary is available  (bundled → downloaded)
//! 2. `uv python install 3.13`         (into a temp dir, then rename)
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
use flate2::read::GzDecoder;
use log::{info, warn};

use crate::config::{platform_triple, AppConfig};
use crate::process_utils;

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

/// Pinned CPython minor version.  `uv python install` resolves the latest
/// patch release automatically, so we never hard-code a patch number.
const PYTHON_MINOR: &str = "3.13";

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/// Ensure that a working Python venv with all dependencies is present.
///
/// Steps (each is idempotent):
/// 1. Ensure uv binary        → bundled or downloaded
/// 2. uv python install 3.13  → `config.python_dir`
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

fn ensure_uv(config: &AppConfig) -> Result<()> {
    let uv = config.resolved_uv_path();
    if uv.exists() {
        info!("uv already present at {}", uv.display());
        return Ok(());
    }

    info!("Downloading uv ...");
    let triple = platform_triple();
    let url = uv_download_url(triple);
    info!("uv URL: {url}");

    let data = download_bytes(&url)?;
    info!("Downloaded {} bytes", data.len());

    // Download destination is always the non-bundled location.
    let dest = &config.uv_path;

    if cfg!(target_os = "windows") {
        extract_uv_from_zip(&data, triple, dest)?;
    } else {
        extract_uv_from_tar_gz(&data, triple, dest)?;
    }

    // Make the binary executable on Unix.
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        let mut perms = fs::metadata(dest)?.permissions();
        perms.set_mode(0o755);
        fs::set_permissions(dest, perms)?;
    }

    info!("uv installed at {}", dest.display());
    Ok(())
}

fn uv_download_url(triple: &str) -> String {
    let ext = if triple.contains("windows") {
        "zip"
    } else {
        "tar.gz"
    };
    format!("https://github.com/astral-sh/uv/releases/latest/download/uv-{triple}.{ext}")
}

/// Extract `uv` binary from a tar.gz archive (Unix).
fn extract_uv_from_tar_gz(data: &[u8], triple: &str, dest: &Path) -> Result<()> {
    let decoder = GzDecoder::new(data);
    let mut archive = tar::Archive::new(decoder);

    let expected_entry = format!("uv-{triple}/uv");

    for entry in archive.entries()? {
        let mut entry = entry?;
        let path = entry.path()?.to_path_buf();
        if path.to_string_lossy() == expected_entry {
            if let Some(parent) = dest.parent() {
                fs::create_dir_all(parent)?;
            }
            let mut out = fs::File::create(dest)?;
            io::copy(&mut entry, &mut out)?;
            return Ok(());
        }
    }

    bail!("could not find `{}` inside the uv archive", expected_entry);
}

/// Extract `uv.exe` from a zip archive (Windows).
#[allow(dead_code)]
fn extract_uv_from_zip(data: &[u8], triple: &str, dest: &Path) -> Result<()> {
    let parent = dest.parent().unwrap_or(Path::new("."));
    let tmp_zip = parent.join("_uv_tmp.zip");
    fs::write(&tmp_zip, data)?;

    let expected = format!("uv-{triple}/uv.exe");

    let status = process_utils::command("tar")
        .args(["-xf", &tmp_zip.to_string_lossy(), &expected])
        .current_dir(parent)
        .status();

    match status {
        Ok(s) if s.success() => {
            let extracted = parent.join(&expected);
            if extracted.exists() {
                fs::rename(&extracted, dest)?;
                let inter_dir = parent.join(format!("uv-{triple}"));
                fs::remove_dir_all(&inter_dir).ok();
            }
        }
        _ => {
            fs::remove_file(&tmp_zip).ok();
            bail!("failed to extract uv.exe from zip archive");
        }
    }

    fs::remove_file(&tmp_zip).ok();
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

    info!("Installing Python {PYTHON_MINOR} via uv ...");
    let uv = config.resolved_uv_path();

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
            PYTHON_MINOR,
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
    let uv = config.resolved_uv_path();
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
    PYTHON_MINOR.hash(&mut hasher);
    let hash = hasher.finish();
    Ok(format!("{:x}", hash))
}

fn install_requirements(config: &AppConfig) -> Result<()> {
    let req_path = config.requirements_txt();
    if !req_path.exists() {
        info!("No requirements.txt found, skipping pip install");
        return Ok(());
    }

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
    let uv = config.resolved_uv_path();
    let status = process_utils::command(&uv)
        .args([
            "pip",
            "install",
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
// HTTP helpers
// ---------------------------------------------------------------------------

fn http_client() -> Result<reqwest::blocking::Client> {
    reqwest::blocking::Client::builder()
        .timeout(std::time::Duration::from_secs(300))
        .build()
        .context("failed to build HTTP client")
}

fn download_bytes(url: &str) -> Result<Vec<u8>> {
    let client = http_client()?;
    let resp = client
        .get(url)
        .send()
        .with_context(|| format!("HTTP GET failed: {url}"))?;
    if !resp.status().is_success() {
        bail!("HTTP {} for {url}", resp.status());
    }
    let bytes = resp
        .bytes()
        .with_context(|| format!("failed to read response body from {url}"))?;
    Ok(bytes.to_vec())
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;
    use std::time::{SystemTime, UNIX_EPOCH};

    #[test]
    fn uv_url_unix() {
        let url = uv_download_url("aarch64-apple-darwin");
        assert!(url.contains("uv-aarch64-apple-darwin.tar.gz"));
    }

    #[test]
    fn uv_url_windows() {
        let url = uv_download_url("x86_64-pc-windows-msvc");
        assert!(url.contains("uv-x86_64-pc-windows-msvc.zip"));
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
