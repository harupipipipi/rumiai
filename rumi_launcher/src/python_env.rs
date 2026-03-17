//! Python environment bootstrap via python-build-standalone (PBS) and uv.
//!
//! Each step is idempotent — if the artefact already exists the step is
//! skipped.  This allows the launcher to be restarted at any point without
//! leaving the environment in an inconsistent state.

use std::fs;
use std::io;
use std::path::Path;
use std::process::Command;

use anyhow::{bail, Context, Result};
use flate2::read::GzDecoder;
use log::info;
use serde::Deserialize;

use crate::config::{platform_triple, AppConfig};

// ---------------------------------------------------------------------------
// PBS latest-release metadata
// ---------------------------------------------------------------------------

const PBS_LATEST_URL: &str =
    "https://raw.githubusercontent.com/indygreg/python-build-standalone/latest-release/latest-release.json";

/// Pinned CPython minor version.
const PYTHON_MINOR: &str = "3.13";

#[derive(Debug, Deserialize)]
struct PbsRelease {
    tag: String,
    asset_url_prefix: String,
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

/// Ensure that a working Python venv with all dependencies is present.
///
/// Steps (each is idempotent):
/// 1. Download + extract PBS → `config.python_dir`
/// 2. Download uv binary     → `config.uv_path`
/// 3. Create venv             → `config.venv_dir`
/// 4. Install requirements    → into the venv
pub fn ensure_python_env(config: &AppConfig) -> Result<()> {
    ensure_python(config).context("PBS Python setup failed")?;
    ensure_uv(config).context("uv setup failed")?;
    ensure_venv(config).context("venv creation failed")?;
    install_requirements(config).context("pip install failed")?;
    Ok(())
}

// ---------------------------------------------------------------------------
// Step 1 — PBS Python
// ---------------------------------------------------------------------------

fn ensure_python(config: &AppConfig) -> Result<()> {
    let python_bin = config.python_bin();
    if python_bin.exists() {
        info!("PBS Python already present at {}", python_bin.display());
        return Ok(());
    }

    info!("Downloading PBS Python …");
    let release = fetch_pbs_release()?;
    let archive_name = pbs_archive_name(&release.tag, platform_triple());
    let url = format!("{}/{}", release.asset_url_prefix, archive_name);
    info!("PBS URL: {url}");

    let data = download_bytes(&url)?;
    info!("Downloaded {} bytes, extracting …", data.len());

    let tmp_dir = config.app_dir.join("_python_tmp");
    if tmp_dir.exists() {
        fs::remove_dir_all(&tmp_dir)?;
    }
    fs::create_dir_all(&tmp_dir)?;

    extract_tar_gz(&data, &tmp_dir)?;

    // The archive extracts to `_python_tmp/python/`.
    let extracted = tmp_dir.join("python");
    if !extracted.exists() {
        bail!(
            "expected `python/` directory inside PBS archive but found: {:?}",
            fs::read_dir(&tmp_dir)?
                .filter_map(|e| e.ok().map(|e| e.file_name()))
                .collect::<Vec<_>>()
        );
    }

    if config.python_dir.exists() {
        fs::remove_dir_all(&config.python_dir)?;
    }
    fs::rename(&extracted, &config.python_dir)?;
    fs::remove_dir_all(&tmp_dir).ok();

    info!("PBS Python installed at {}", config.python_dir.display());
    Ok(())
}

fn fetch_pbs_release() -> Result<PbsRelease> {
    let body = download_string(PBS_LATEST_URL)?;
    let release: PbsRelease =
        serde_json::from_str(&body).context("failed to parse PBS latest-release.json")?;
    Ok(release)
}

/// Build the archive file-name that PBS publishes.
///
/// Example: `cpython-3.13.12+20260310-aarch64-apple-darwin-install_only.tar.gz`
fn pbs_archive_name(tag: &str, triple: &str) -> String {
    let python_version = format!("{}.12", PYTHON_MINOR); // 3.13.12
    format!("cpython-{python_version}+{tag}-{triple}-install_only.tar.gz")
}

// ---------------------------------------------------------------------------
// Step 2 — uv
// ---------------------------------------------------------------------------

fn ensure_uv(config: &AppConfig) -> Result<()> {
    if config.uv_path.exists() {
        info!("uv already present at {}", config.uv_path.display());
        return Ok(());
    }

    info!("Downloading uv …");
    let triple = platform_triple();
    let url = uv_download_url(triple);
    info!("uv URL: {url}");

    let data = download_bytes(&url)?;
    info!("Downloaded {} bytes", data.len());

    if cfg!(target_os = "windows") {
        extract_uv_from_zip(&data, triple, &config.uv_path)?;
    } else {
        extract_uv_from_tar_gz(&data, triple, &config.uv_path)?;
    }

    // Make the binary executable on Unix.
    #[cfg(unix)]
    {
        use std::os::unix::fs::PermissionsExt;
        let mut perms = fs::metadata(&config.uv_path)?.permissions();
        perms.set_mode(0o755);
        fs::set_permissions(&config.uv_path, perms)?;
    }

    info!("uv installed at {}", config.uv_path.display());
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
///
/// Uses bsdtar which ships with Windows 10+.
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
// Step 3 — venv
// ---------------------------------------------------------------------------

fn ensure_venv(config: &AppConfig) -> Result<()> {
    if config.venv_dir.exists() {
        info!("venv already present at {}", config.venv_dir.display());
        return Ok(());
    }

    info!("Creating venv …");
    let python_bin = config.python_bin();
    let status = Command::new(&config.uv_path)
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

    info!("Installing requirements …");
    let venv_python = config.venv_python();
    let status = Command::new(&config.uv_path)
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

fn download_string(url: &str) -> Result<String> {
    let client = http_client()?;
    let resp = client
        .get(url)
        .send()
        .with_context(|| format!("HTTP GET failed: {url}"))?;
    if !resp.status().is_success() {
        bail!("HTTP {} for {url}", resp.status());
    }
    let text = resp
        .text()
        .with_context(|| format!("failed to read response text from {url}"))?;
    Ok(text)
}

// ---------------------------------------------------------------------------
// Archive helpers
// ---------------------------------------------------------------------------

fn extract_tar_gz(data: &[u8], dest: &Path) -> Result<()> {
    let decoder = GzDecoder::new(data);
    let mut archive = tar::Archive::new(decoder);
    archive
        .unpack(dest)
        .context("failed to extract tar.gz archive")?;
    Ok(())
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn pbs_archive_name_format() {
        let name = pbs_archive_name("20260310", "aarch64-apple-darwin");
        assert_eq!(
            name,
            "cpython-3.13.12+20260310-aarch64-apple-darwin-install_only.tar.gz"
        );
    }

    #[test]
    fn pbs_archive_name_linux() {
        let name = pbs_archive_name("20260310", "x86_64-unknown-linux-gnu");
        assert!(name.contains("x86_64-unknown-linux-gnu"));
        assert!(name.starts_with("cpython-"));
        assert!(name.ends_with("-install_only.tar.gz"));
    }

    #[test]
    fn uv_url_unix() {
        let url = uv_download_url("aarch64-apple-darwin");
        assert!(url.contains("uv-aarch64-apple-darwin.tar.gz"));
        assert!(url.starts_with("https://"));
    }

    #[test]
    fn uv_url_windows() {
        let url = uv_download_url("x86_64-pc-windows-msvc");
        assert!(url.contains("uv-x86_64-pc-windows-msvc.zip"));
    }
}
