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

use std::fs;
use std::io;
use std::path::Path;
use std::process::Command;

use anyhow::{bail, Context, Result};
use flate2::read::GzDecoder;
use log::info;

use crate::config::{platform_triple, AppConfig};

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

    let status = Command::new("tar")
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

    info!("Installing Python {PYTHON_MINOR} via uv ...");
    let uv = config.resolved_uv_path();

    // Install into a temporary directory under app_data_dir (writable),
    // then move the versioned sub-directory to `config.python_dir`.
    let tmp_dir = config.python_dir.with_file_name("_python_tmp");
    if tmp_dir.exists() {
        fs::remove_dir_all(&tmp_dir)?;
    }
    fs::create_dir_all(&tmp_dir)?;

    let status = Command::new(&uv)
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
        fs::remove_dir_all(&tmp_dir).ok();
        bail!("uv python install exited with {status}");
    }

    // `uv python install --install-dir {tmp}` creates a sub-directory
    // like `cpython-3.13.12-macos-aarch64-none/`.  Find it by prefix.
    let prefix = format!("cpython-{PYTHON_MINOR}");
    let found = fs::read_dir(&tmp_dir)?
        .filter_map(|e| e.ok())
        .find(|e| {
            e.file_name()
                .to_string_lossy()
                .starts_with(&prefix)
        });

    let extracted = match found {
        Some(entry) => entry.path(),
        None => {
            let contents: Vec<String> = fs::read_dir(&tmp_dir)?
                .filter_map(|e| e.ok().map(|e| e.file_name().to_string_lossy().into_owned()))
                .collect();
            fs::remove_dir_all(&tmp_dir).ok();
            bail!(
                "uv python install succeeded but no directory matching \
                 `{prefix}*` was found in the install dir.\n\
                 Contents of {}: {:?}\n\
                 This may indicate a change in uv's directory naming scheme.",
                tmp_dir.display(),
                contents,
            );
        }
    };

    if config.python_dir.exists() {
        fs::remove_dir_all(&config.python_dir)?;
    }
    fs::rename(&extracted, &config.python_dir)?;
    fs::remove_dir_all(&tmp_dir).ok();

    info!("Python installed at {}", config.python_dir.display());
    Ok(())
}

// ---------------------------------------------------------------------------
// Step 3 — venv
// ---------------------------------------------------------------------------

fn ensure_venv(config: &AppConfig) -> Result<()> {
    if config.venv_dir.exists() {
        info!("venv already present at {}", config.venv_dir.display());
        return Ok(());
    }

    info!("Creating venv ...");
    let uv = config.resolved_uv_path();
    let python_bin = config.python_bin();
    let status = Command::new(&uv)
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

fn install_requirements(config: &AppConfig) -> Result<()> {
    let req_path = config.requirements_txt();
    if !req_path.exists() {
        info!("No requirements.txt found, skipping pip install");
        return Ok(());
    }

    info!("Installing requirements ...");
    let uv = config.resolved_uv_path();
    let venv_python = config.venv_python();
    let status = Command::new(&uv)
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
}
